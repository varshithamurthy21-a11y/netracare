import datetime as dt

import pytest

from backend import config, services, triage
from backend.db import session
from backend.seed import seed
from backend.security import create_token, decode_token, hash_password, verify_password


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    seed()
    with session() as c:
        yield c


def user(conn, email):
    return services.get_user(conn, conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0])


def free_slot(conn, doctor_id=1, days_ahead=5):
    for i in range(1, 12):
        day = (services.now().date() + dt.timedelta(days=i)).isoformat()
        for s in services.get_slots(conn, doctor_id, day):
            if s["available"]:
                return day, s["time"]
    raise AssertionError("no slot")


def test_password_and_token_roundtrip():
    h = hash_password("secret1")
    assert verify_password("secret1", h) and not verify_password("nope", h)
    tok = create_token(7, "patient")
    assert decode_token(tok)["uid"] == 7
    assert decode_token(tok[:-2] + "xx") is None


def test_five_doctors_seeded(conn):
    assert len(services.list_doctors(conn)) == 5


def test_register_login_and_duplicates(conn):
    u = services.register_patient(conn, "Asha Rao", "asha@x.com", "pass123")
    assert services.authenticate(conn, "ASHA@x.com", "pass123")["id"] == u["id"]
    with pytest.raises(services.ServiceError):
        services.register_patient(conn, "Asha Rao", "asha@x.com", "pass123")
    with pytest.raises(services.ServiceError):
        services.authenticate(conn, "asha@x.com", "wrong")


def test_booking_cancel_and_double_booking(conn):
    p1, p2 = user(conn, "patient@netracare.demo"), user(conn, "imran@netracare.demo")
    day, t = free_slot(conn, 3)
    a = services.book(conn, p1, 3, day, t, "Eye check")
    assert a["status"] == "booked"
    with pytest.raises(services.ServiceError) as e:
        services.book(conn, p2, 3, day, t, "same slot")
    assert e.value.status == 409
    services.cancel(conn, p1, a["id"])
    assert services.book(conn, p2, 3, day, t, "now free")["status"] == "booked"


def test_cannot_book_past_sunday_or_far_future(conn):
    p = user(conn, "patient@netracare.demo")
    yesterday = (services.now().date() - dt.timedelta(days=1)).isoformat()
    with pytest.raises(services.ServiceError):
        services.book(conn, p, 1, yesterday, "10:00")
    d = services.now().date() + dt.timedelta(days=1)
    while d.weekday() != 6:
        d += dt.timedelta(days=1)
    with pytest.raises(services.ServiceError):
        services.book(conn, p, 1, d.isoformat(), "10:00")
    with pytest.raises(services.ServiceError):
        services.book(conn, p, 1, (services.now().date() + dt.timedelta(days=40)).isoformat(), "10:00")


def test_patient_privacy_and_permissions(conn):
    p, other = user(conn, "patient@netracare.demo"), user(conn, "rahul@netracare.demo")
    mine = services.list_appointments(conn, p)
    assert mine and all(a["patient_id"] == p["id"] for a in mine)
    foreign = services.list_appointments(conn, other)[0]
    with pytest.raises(services.ServiceError) as e:
        services.get_appointment(conn, foreign["id"], p)
    assert e.value.status == 403
    with pytest.raises(services.ServiceError):
        services.stats(conn, p)
    with pytest.raises(services.ServiceError):
        services.list_users(conn, p)


def test_reschedule(conn):
    p = user(conn, "patient@netracare.demo")
    appt = services.list_appointments(conn, p, scope="upcoming")[0]
    day, t = free_slot(conn, appt["doctor_id"])
    out = services.reschedule(conn, p, appt["id"], day, t)
    assert (out["date"], out["time"]) == (day, t)


def test_red_flag_on_booking_and_triage():
    assert triage.detect_red_flags("I have sudden vision loss in my right eye")["red_flag"]
    assert triage.detect_red_flags("chemical splashed in my eye")["red_flag"]
    assert not triage.detect_red_flags("I need new glasses")["red_flag"]
    assert triage.route_to_specialty("my son has a squint")["specialty"].startswith("Pediatric")
    assert triage.route_to_specialty("floaters and diabetic review")["specialty"] == "Retina & Vitreous"
    assert triage.route_to_specialty("hello")["confident"] is False


def test_red_flag_stored_on_appointment(conn):
    p = user(conn, "imran@netracare.demo")
    day, t = free_slot(conn, 2)
    a = services.book(conn, p, 2, day, t, "sudden loss of vision and flashes")
    assert a["red_flag"] == 1 and a["red_flag_info"]["patient_message"]


def test_visit_summary_requires_doctor_approval(conn):
    desk = user(conn, "desk@netracare.demo")
    doc = user(conn, "rohan@netracare.demo")  # doctor id 4
    pat = user(conn, "patient@netracare.demo")
    today = services.now().date()
    d = today
    while d.weekday() == 6:
        d += dt.timedelta(days=1)
    # create directly in DB for today (time may have passed), then complete
    conn.execute("INSERT INTO appointments(patient_id,doctor_id,date,time,reason,status,created_at) VALUES (?,?,?,?,?,?,?)",
                 (pat["id"], 4, today.isoformat(), "08:00", "test", "checked_in", "now"))
    aid = conn.execute("SELECT max(id) FROM appointments").fetchone()[0]
    done = services.complete_visit(conn, doc, aid, "Exam normal. Glasses unchanged.")
    assert done["status"] == "completed" and done["summary_status"] == "draft"
    assert services.get_appointment(conn, aid, pat)["summary"] == ""          # hidden from patient
    assert "visit_notes" not in services.get_appointment(conn, aid, pat)       # raw notes never shown
    services.save_summary(conn, doc, aid, "Your exam was normal.", True)
    assert services.get_appointment(conn, aid, pat)["summary"] == "Your exam was normal."
    with pytest.raises(services.ServiceError):
        services.complete_visit(conn, desk, aid, "x" * 10)


def test_check_in_and_queue(conn):
    desk = user(conn, "desk@netracare.demo")
    pat = user(conn, "patient@netracare.demo")
    today = services.now().date().isoformat()
    conn.execute("INSERT INTO appointments(patient_id,doctor_id,date,time,status,created_at) VALUES (?,?,?,?,?,?)",
                 (pat["id"], 2, today, "08:30", "booked", "now"))
    aid = conn.execute("SELECT max(id) FROM appointments").fetchone()[0]
    services.check_in(conn, desk, aid)
    q = {d["doctor_id"]: d for d in services.queue(conn)}
    assert q[2]["waiting"][0]["position"] == 1
    assert services.my_queue_status(conn, pat)["position"] == 1


def test_admin_can_add_doctor_and_audit(conn):
    admin = user(conn, "admin@netracare.demo")
    d = services.create_doctor(conn, admin, "Dr. New", "new@x.com", "pw12345", "Oculoplastics")
    assert d["specialty"] == "Oculoplastics" and len(services.list_doctors(conn)) == 6
    services.set_doctor_active(conn, admin, d["id"], False)
    assert len(services.list_doctors(conn)) == 5
    assert any(r["action"] == "create_doctor" for r in services.audit(conn, admin))
