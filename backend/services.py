"""All business rules live here (framework-free, so they are easy to test)."""
import datetime as dt
import sqlite3

from . import config, llm, triage
from .security import hash_password, verify_password


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


# ---------- helpers -------------------------------------------------------
def now() -> dt.datetime:
    return dt.datetime.now(config.TZ).replace(tzinfo=None)


def _stamp() -> str:
    return now().isoformat(timespec="seconds")


def log(conn, actor: dict | None, action: str, detail: str = "") -> None:
    conn.execute("INSERT INTO audit_log(actor_id, actor_name, action, detail, at) VALUES (?,?,?,?,?)",
                 (actor["id"] if actor else None, actor["name"] if actor else "system", action, detail, _stamp()))


def public_user(row) -> dict:
    return {k: row[k] for k in ("id", "name", "email", "phone", "role", "active", "dob", "notes", "created_at")}


def require_role(actor: dict, *roles: str) -> None:
    if actor["role"] not in roles:
        raise ServiceError("You don't have permission to do that.", 403)


# ---------- auth ----------------------------------------------------------
def register_patient(conn, name: str, email: str, password: str, phone: str = "", dob: str = "") -> dict:
    name, email = name.strip(), email.strip().lower()
    if len(name) < 2 or "@" not in email:
        raise ServiceError("Please enter your name and a valid email.")
    if len(password) < 6:
        raise ServiceError("Password must be at least 6 characters.")
    try:
        cur = conn.execute(
            "INSERT INTO users(name,email,phone,password_hash,role,dob,created_at) VALUES (?,?,?,?,?,?,?)",
            (name, email, phone.strip(), hash_password(password), "patient", dob, _stamp()))
    except sqlite3.IntegrityError:
        raise ServiceError("An account with this email already exists.", 409)
    user = public_user(conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())
    log(conn, user, "register", "New patient account")
    return user


def authenticate(conn, email: str, password: str) -> dict:
    row = conn.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        raise ServiceError("Incorrect email or password.", 401)
    if not row["active"]:
        raise ServiceError("This account has been deactivated. Please contact the clinic.", 403)
    return public_user(row)


def get_user(conn, user_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE id=? AND active=1", (user_id,)).fetchone()
    return public_user(row) if row else None


def update_profile(conn, actor: dict, name: str, phone: str, dob: str, notes: str) -> dict:
    conn.execute("UPDATE users SET name=?, phone=?, dob=?, notes=? WHERE id=?",
                 (name.strip() or actor["name"], phone.strip(), dob, notes.strip(), actor["id"]))
    return public_user(conn.execute("SELECT * FROM users WHERE id=?", (actor["id"],)).fetchone())


# ---------- doctors & slots ----------------------------------------------
def list_doctors(conn, include_inactive: bool = False) -> list[dict]:
    q = ("SELECT d.*, u.name, u.email FROM doctors d JOIN users u ON u.id=d.user_id "
         + ("" if include_inactive else "WHERE d.active=1 AND u.active=1 ") + "ORDER BY d.id")
    return [dict(r) for r in conn.execute(q).fetchall()]


def doctor_for_user(conn, user_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM doctors WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def _session_times(date: dt.date) -> list[dt.time]:
    if date.weekday() not in config.OPEN_WEEKDAYS:
        return []
    out = []
    for start, end in config.SESSIONS:
        cur = dt.datetime.combine(date, start)
        stop = dt.datetime.combine(date, end)
        while cur < stop:
            out.append(cur.time())
            cur += dt.timedelta(minutes=config.SLOT_MINUTES)
    return out


def _parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ServiceError("Invalid date.")


def get_slots(conn, doctor_id: int, date_str: str) -> list[dict]:
    date = _parse_date(date_str)
    taken = {r["time"] for r in conn.execute(
        "SELECT time FROM appointments WHERE doctor_id=? AND date=? AND status IN ('booked','checked_in','completed')",
        (doctor_id, date_str))}
    current = now()
    out = []
    for t in _session_times(date):
        label = t.strftime("%H:%M")
        past = dt.datetime.combine(date, t) <= current
        out.append({"time": label, "available": label not in taken and not past})
    return out


# ---------- appointments --------------------------------------------------
_APPT_SELECT = """
SELECT a.*, p.name AS patient_name, p.phone AS patient_phone, du.name AS doctor_name,
       d.specialty, d.room, d.accent
FROM appointments a
JOIN users p ON p.id = a.patient_id
JOIN doctors d ON d.id = a.doctor_id
JOIN users du ON du.id = d.user_id
"""


def _present(row, actor: dict) -> dict:
    a = dict(row)
    if actor["role"] == "patient":
        a.pop("visit_notes", None)  # raw clinical notes stay with staff
        if a["summary_status"] != "published":
            a["summary"] = ""
    return a


def get_appointment(conn, appt_id: int, actor: dict) -> dict:
    row = conn.execute(_APPT_SELECT + " WHERE a.id=?", (appt_id,)).fetchone()
    if not row:
        raise ServiceError("Appointment not found.", 404)
    _check_access(conn, row, actor)
    return _present(row, actor)


def _check_access(conn, row, actor: dict) -> None:
    if actor["role"] in ("frontdesk", "admin"):
        return
    if actor["role"] == "patient" and row["patient_id"] == actor["id"]:
        return
    if actor["role"] == "doctor":
        doc = doctor_for_user(conn, actor["id"])
        if doc and doc["id"] == row["doctor_id"]:
            return
    raise ServiceError("You don't have access to this appointment.", 403)


def list_appointments(conn, actor: dict, date: str | None = None, status: str | None = None,
                      scope: str | None = None) -> list[dict]:
    where, args = [], []
    if actor["role"] == "patient":
        where.append("a.patient_id=?"); args.append(actor["id"])
    elif actor["role"] == "doctor":
        doc = doctor_for_user(conn, actor["id"])
        where.append("a.doctor_id=?"); args.append(doc["id"] if doc else -1)
    if date:
        where.append("a.date=?"); args.append(date)
    if status:
        where.append("a.status=?"); args.append(status)
    today, hhmm = now().date().isoformat(), now().strftime("%H:%M")
    if scope == "upcoming":
        where.append("a.status IN ('booked','checked_in') AND (a.date>? OR (a.date=? AND a.time>=?))")
        args += [today, today, hhmm[:5]]
    elif scope == "past":
        where.append("(a.status IN ('completed','cancelled','no_show') OR a.date<? OR (a.date=? AND a.time<?))")
        args += [today, today, hhmm[:5]]
    order = "DESC" if scope == "past" else "ASC"
    sql = _APPT_SELECT + (" WHERE " + " AND ".join(where) if where else "") + f" ORDER BY a.date {order}, a.time {order}"
    return [_present(r, actor) for r in conn.execute(sql, args).fetchall()]


def book(conn, actor: dict, doctor_id: int, date: str, time: str, reason: str = "",
         patient_id: int | None = None) -> dict:
    require_role(actor, "patient", "frontdesk", "admin")
    if actor["role"] == "patient":
        patient_id = actor["id"]
    elif not patient_id:
        raise ServiceError("Please choose a patient.")
    patient = conn.execute("SELECT * FROM users WHERE id=? AND role='patient' AND active=1", (patient_id,)).fetchone()
    if not patient:
        raise ServiceError("Patient not found.", 404)
    doc = conn.execute("SELECT d.*, u.active AS uactive FROM doctors d JOIN users u ON u.id=d.user_id WHERE d.id=?",
                       (doctor_id,)).fetchone()
    if not doc or not doc["active"] or not doc["uactive"]:
        raise ServiceError("That doctor isn't available for booking.", 404)

    day = _parse_date(date)
    today = now().date()
    if day < today or day > today + dt.timedelta(days=config.BOOKING_WINDOW_DAYS):
        raise ServiceError(f"Bookings open for the next {config.BOOKING_WINDOW_DAYS} days.")
    if time not in {t.strftime("%H:%M") for t in _session_times(day)}:
        raise ServiceError("That time isn't within clinic hours (Mon–Sat, 9:00–13:00 and 14:30–18:00).")
    if dt.datetime.combine(day, dt.time.fromisoformat(time)) <= now():
        raise ServiceError("That time has already passed.")

    if actor["role"] == "patient":
        n = conn.execute("""SELECT COUNT(*) FROM appointments WHERE patient_id=? AND status IN ('booked','checked_in')
                            AND date>=?""", (patient_id, today.isoformat())).fetchone()[0]
        if n >= config.MAX_UPCOMING_PER_PATIENT:
            raise ServiceError(f"You already have {n} upcoming appointments. Please cancel one or call the front desk.")
    dup = conn.execute("""SELECT 1 FROM appointments WHERE patient_id=? AND doctor_id=? AND date=?
                          AND status IN ('booked','checked_in')""", (patient_id, doctor_id, date)).fetchone()
    if dup:
        raise ServiceError("This patient already has an appointment with this doctor that day.", 409)

    flags = triage.detect_red_flags(reason)
    try:
        cur = conn.execute(
            """INSERT INTO appointments(patient_id,doctor_id,date,time,reason,red_flag,red_flag_reason,booked_by,created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (patient_id, doctor_id, date, time, reason.strip(), int(flags["red_flag"]),
             "; ".join(flags["reasons"]), actor["id"], _stamp()))
    except sqlite3.IntegrityError:
        raise ServiceError("Sorry, that slot was just taken. Please pick another time.", 409)
    log(conn, actor, "book", f"appointment #{cur.lastrowid} for {patient['name']} on {date} {time}"
        + (" [RED FLAG]" if flags["red_flag"] else ""))
    result = get_appointment(conn, cur.lastrowid, actor)
    result["red_flag_info"] = flags
    return result


def cancel(conn, actor: dict, appt_id: int) -> dict:
    row = conn.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
    if not row:
        raise ServiceError("Appointment not found.", 404)
    require_role(actor, "patient", "frontdesk", "admin")
    _check_access(conn, row, actor)
    allowed = ("booked",) if actor["role"] == "patient" else ("booked", "checked_in")
    if row["status"] not in allowed:
        raise ServiceError(f"A {row['status'].replace('_', ' ')} appointment can't be cancelled.")
    conn.execute("UPDATE appointments SET status='cancelled' WHERE id=?", (appt_id,))
    log(conn, actor, "cancel", f"appointment #{appt_id} ({row['date']} {row['time']})")
    return get_appointment(conn, appt_id, actor)


def reschedule(conn, actor: dict, appt_id: int, date: str, time: str) -> dict:
    row = conn.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
    if not row:
        raise ServiceError("Appointment not found.", 404)
    require_role(actor, "patient", "frontdesk", "admin")
    _check_access(conn, row, actor)
    if row["status"] != "booked":
        raise ServiceError("Only upcoming booked appointments can be rescheduled.")
    day, today = _parse_date(date), now().date()
    if day < today or day > today + dt.timedelta(days=config.BOOKING_WINDOW_DAYS):
        raise ServiceError(f"Bookings open for the next {config.BOOKING_WINDOW_DAYS} days.")
    if time not in {t.strftime("%H:%M") for t in _session_times(day)}:
        raise ServiceError("That time isn't within clinic hours.")
    if dt.datetime.combine(day, dt.time.fromisoformat(time)) <= now():
        raise ServiceError("That time has already passed.")
    try:
        conn.execute("UPDATE appointments SET date=?, time=? WHERE id=?", (date, time, appt_id))
    except sqlite3.IntegrityError:
        raise ServiceError("Sorry, that slot was just taken. Please pick another time.", 409)
    log(conn, actor, "reschedule", f"appointment #{appt_id}: {row['date']} {row['time']} → {date} {time}")
    return get_appointment(conn, appt_id, actor)


def check_in(conn, actor: dict, appt_id: int) -> dict:
    require_role(actor, "frontdesk", "admin")
    row = conn.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
    if not row:
        raise ServiceError("Appointment not found.", 404)
    if row["status"] != "booked":
        raise ServiceError("Only booked appointments can be checked in.")
    if row["date"] != now().date().isoformat():
        raise ServiceError("Check-in is only available on the day of the appointment.")
    conn.execute("UPDATE appointments SET status='checked_in', checked_in_at=? WHERE id=?", (_stamp(), appt_id))
    log(conn, actor, "check_in", f"appointment #{appt_id}")
    return get_appointment(conn, appt_id, actor)


def mark_no_show(conn, actor: dict, appt_id: int) -> dict:
    require_role(actor, "frontdesk", "admin")
    row = conn.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
    if not row or row["status"] not in ("booked", "checked_in"):
        raise ServiceError("Only booked or checked-in appointments can be marked no-show.")
    conn.execute("UPDATE appointments SET status='no_show' WHERE id=?", (appt_id,))
    log(conn, actor, "no_show", f"appointment #{appt_id}")
    return get_appointment(conn, appt_id, actor)


def dismiss_red_flag(conn, actor: dict, appt_id: int) -> dict:
    require_role(actor, "frontdesk", "admin", "doctor")
    row = conn.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
    if not row:
        raise ServiceError("Appointment not found.", 404)
    _check_access(conn, row, actor)
    conn.execute("UPDATE appointments SET red_flag=0 WHERE id=?", (appt_id,))
    log(conn, actor, "red_flag_reviewed", f"appointment #{appt_id}")
    return get_appointment(conn, appt_id, actor)


# ---------- visit summary (doctor in control) -----------------------------
def _fallback_summary(a: dict) -> str:
    return (f"Thank you for visiting NetraCare on {a['date']} and seeing {a['doctor_name']} "
            f"({a['specialty']}). Here is a plain-language recap of what your doctor recorded:\n\n"
            f"{a['visit_notes'].strip()}\n\n"
            "Please follow the instructions your doctor gave you in the clinic. "
            "If anything is unclear, contact our front desk and we'll help you reach your care team.")


def _make_summary(a: dict) -> str:
    text = llm.generate(
        f"Doctor's visit notes:\n{a['visit_notes']}\n\nPatient: {a['patient_name']}\nDoctor: {a['doctor_name']}\n"
        f"Date: {a['date']}\n\nRewrite these notes as a short, warm, plain-language visit summary for the patient "
        "(max 120 words). Restate ONLY what is in the notes. Do not add any medical advice, diagnosis, medication, "
        "dosage or recommendation that is not in the notes. End by telling them to contact the front desk with questions.",
        system="You turn clinic visit notes into patient-friendly summaries. You never add medical advice.",
        max_tokens=300)
    return text or _fallback_summary(a)


def complete_visit(conn, actor: dict, appt_id: int, visit_notes: str) -> dict:
    require_role(actor, "doctor")
    a = get_appointment(conn, appt_id, actor)
    if a["status"] not in ("booked", "checked_in"):
        raise ServiceError("Only booked or checked-in visits can be completed.")
    if a["date"] > now().date().isoformat():
        raise ServiceError("This visit is in the future.")
    if len(visit_notes.strip()) < 5:
        raise ServiceError("Please add brief visit notes.")
    a["visit_notes"] = visit_notes.strip()
    summary = _make_summary(a)
    conn.execute("UPDATE appointments SET status='completed', visit_notes=?, summary=?, summary_status='draft' WHERE id=?",
                 (a["visit_notes"], summary, appt_id))
    log(conn, actor, "complete_visit", f"appointment #{appt_id}; AI draft summary created, awaiting doctor approval")
    return get_appointment(conn, appt_id, actor)


def save_summary(conn, actor: dict, appt_id: int, summary: str, publish: bool) -> dict:
    require_role(actor, "doctor")
    a = get_appointment(conn, appt_id, actor)
    if a["status"] != "completed":
        raise ServiceError("Complete the visit first.")
    conn.execute("UPDATE appointments SET summary=?, summary_status=? WHERE id=?",
                 (summary.strip(), "published" if publish else "draft", appt_id))
    log(conn, actor, "publish_summary" if publish else "edit_summary", f"appointment #{appt_id}")
    return get_appointment(conn, appt_id, actor)


def regenerate_summary(conn, actor: dict, appt_id: int) -> dict:
    require_role(actor, "doctor")
    a = get_appointment(conn, appt_id, actor)
    if a["status"] != "completed":
        raise ServiceError("Complete the visit first.")
    conn.execute("UPDATE appointments SET summary=?, summary_status='draft' WHERE id=?", (_make_summary(a), appt_id))
    return get_appointment(conn, appt_id, actor)


# ---------- queue & wait --------------------------------------------------
def queue(conn) -> list[dict]:
    today = now().date().isoformat()
    out = []
    for d in list_doctors(conn):
        rows = conn.execute(_APPT_SELECT + " WHERE a.doctor_id=? AND a.date=? AND a.status='checked_in' "
                            "ORDER BY a.checked_in_at, a.time", (d["id"], today)).fetchall()
        waiting = []
        for i, r in enumerate(rows, start=1):
            w = dict(r)
            w.update(position=i, wait_minutes=(i - 1) * config.AVG_CONSULT_MINUTES + 5)
            waiting.append(w)
        expected = conn.execute("SELECT COUNT(*) FROM appointments WHERE doctor_id=? AND date=? AND status='booked'",
                                (d["id"], today)).fetchone()[0]
        done = conn.execute("SELECT COUNT(*) FROM appointments WHERE doctor_id=? AND date=? AND status='completed'",
                            (d["id"], today)).fetchone()[0]
        out.append({"doctor_id": d["id"], "doctor_name": d["name"], "specialty": d["specialty"],
                    "accent": d["accent"], "room": d["room"], "waiting": waiting,
                    "still_expected": expected, "seen_today": done})
    return out


def my_queue_status(conn, actor: dict) -> dict | None:
    for d in queue(conn):
        for w in d["waiting"]:
            if w["patient_id"] == actor["id"]:
                return {"position": w["position"], "wait_minutes": w["wait_minutes"], "doctor_name": d["doctor_name"],
                        "room": d["room"]}
    return None


# ---------- people --------------------------------------------------------
def search_patients(conn, actor: dict, q: str = "") -> list[dict]:
    require_role(actor, "frontdesk", "admin", "doctor")
    like = f"%{q.strip().lower()}%"
    rows = conn.execute("SELECT * FROM users WHERE role='patient' AND active=1 AND "
                        "(lower(name) LIKE ? OR lower(email) LIKE ? OR phone LIKE ?) ORDER BY name LIMIT 50",
                        (like, like, like)).fetchall()
    return [public_user(r) for r in rows]


def create_patient(conn, actor: dict, name: str, phone: str, email: str = "") -> dict:
    """Front desk registers a walk-in. A temporary password is set; the patient can reset via the desk."""
    require_role(actor, "frontdesk", "admin")
    if not email.strip():
        email = f"walkin{int(now().timestamp())}@netracare.local"
    user = register_patient(conn, name, email, "Welcome@123", phone)
    log(conn, actor, "create_patient", f"walk-in {user['name']}")
    return user


# ---------- admin ---------------------------------------------------------
def stats(conn, actor: dict) -> dict:
    require_role(actor, "admin", "frontdesk")
    by_status = {r["status"]: r["n"] for r in conn.execute("SELECT status, COUNT(*) n FROM appointments GROUP BY status")}
    by_doctor = [dict(r) for r in conn.execute(
        """SELECT u.name AS doctor, d.specialty, COUNT(a.id) AS appointments
           FROM doctors d JOIN users u ON u.id=d.user_id
           LEFT JOIN appointments a ON a.doctor_id=d.id AND a.status!='cancelled'
           GROUP BY d.id ORDER BY d.id""")]
    today = now().date()
    upcoming = []
    for i in range(7):
        day = (today + dt.timedelta(days=i)).isoformat()
        n = conn.execute("SELECT COUNT(*) FROM appointments WHERE date=? AND status IN ('booked','checked_in','completed')",
                         (day,)).fetchone()[0]
        upcoming.append({"date": day, "appointments": n})
    return {
        "total": sum(by_status.values()), "by_status": by_status, "by_doctor": by_doctor, "next_7_days": upcoming,
        "patients": conn.execute("SELECT COUNT(*) FROM users WHERE role='patient'").fetchone()[0],
        "red_flags_open": conn.execute("SELECT COUNT(*) FROM appointments WHERE red_flag=1 AND status IN ('booked','checked_in')").fetchone()[0],
    }


def list_users(conn, actor: dict) -> list[dict]:
    require_role(actor, "admin")
    return [public_user(r) for r in conn.execute("SELECT * FROM users ORDER BY role, name")]


def set_user_active(conn, actor: dict, user_id: int, active: bool) -> dict:
    require_role(actor, "admin")
    if user_id == actor["id"]:
        raise ServiceError("You can't deactivate your own account.")
    conn.execute("UPDATE users SET active=? WHERE id=?", (int(active), user_id))
    log(conn, actor, "user_active" if active else "user_deactivated", f"user #{user_id}")
    return public_user(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


def create_staff(conn, actor: dict, role: str, name: str, email: str, password: str) -> dict:
    require_role(actor, "admin")
    if role not in ("frontdesk", "admin"):
        raise ServiceError("Use 'Add doctor' for doctors.")
    try:
        cur = conn.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)",
                           (name.strip(), email.strip().lower(), hash_password(password), role, _stamp()))
    except sqlite3.IntegrityError:
        raise ServiceError("That email is already in use.", 409)
    log(conn, actor, "create_staff", f"{role}: {name}")
    return public_user(conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())


def create_doctor(conn, actor: dict, name: str, email: str, password: str, specialty: str, focus: str = "",
                  bio: str = "", years: int = 5, room: str = "", languages: str = "English",
                  accent: str = "#6C5CE7") -> dict:
    require_role(actor, "admin")
    try:
        cur = conn.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)",
                           (name.strip(), email.strip().lower(), hash_password(password), "doctor", _stamp()))
    except sqlite3.IntegrityError:
        raise ServiceError("That email is already in use.", 409)
    conn.execute("INSERT INTO doctors(user_id,specialty,focus,bio,years,room,languages,accent) VALUES (?,?,?,?,?,?,?,?)",
                 (cur.lastrowid, specialty, focus, bio, years, room, languages, accent))
    log(conn, actor, "create_doctor", f"{name} — {specialty}")
    return [d for d in list_doctors(conn, True) if d["user_id"] == cur.lastrowid][0]


def set_doctor_active(conn, actor: dict, doctor_id: int, active: bool) -> dict:
    require_role(actor, "admin")
    conn.execute("UPDATE doctors SET active=? WHERE id=?", (int(active), doctor_id))
    log(conn, actor, "doctor_active" if active else "doctor_paused", f"doctor #{doctor_id}")
    return [d for d in list_doctors(conn, True) if d["id"] == doctor_id][0]


def audit(conn, actor: dict, limit: int = 100) -> list[dict]:
    require_role(actor, "admin")
    return [dict(r) for r in conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))]
