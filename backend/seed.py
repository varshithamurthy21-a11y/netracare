"""Demo data: 5 doctors, staff, a demo patient and a realistic week of appointments."""
import datetime as dt

from . import services
from .db import init_db, session
from .security import hash_password

DOCTORS = [
    ("Dr. Ananya Rao", "ananya@netracare.demo", "Cataract & Lens Surgery",
     "Cataract surgery, lens implants, blurred or cloudy vision", 14, "Room 101", "English, Kannada, Hindi", "#6C5CE7",
     "Dr. Rao has performed thousands of cataract procedures and loves helping people see colour again."),
    ("Dr. Karthik Menon", "karthik@netracare.demo", "Retina & Vitreous",
     "Retina care, diabetic eye checks, floaters and flashes", 11, "Room 102", "English, Malayalam, Tamil", "#00B8A9",
     "Dr. Menon focuses on the back of the eye, with a special interest in diabetic eye screening."),
    ("Dr. Meera Iyer", "meera@netracare.demo", "Glaucoma",
     "Eye pressure checks, optic nerve care, long-term monitoring", 16, "Room 103", "English, Tamil, Kannada", "#FF7675",
     "Dr. Iyer follows patients over many years, helping them keep a steady eye on their eye health."),
    ("Dr. Rohan Shetty", "rohan@netracare.demo", "Cornea & Refractive",
     "Eye exams, glasses, contact lenses, dry eyes, LASIK consultations", 9, "Room 104", "English, Kannada, Tulu", "#0984E3",
     "Dr. Shetty is the go-to for general check-ups, spectacles and refractive consultations."),
    ("Dr. Sneha Kulkarni", "sneha@netracare.demo", "Pediatric Ophthalmology & Squint",
     "Children's eye care, squint and lazy-eye assessments", 12, "Room 105", "English, Hindi, Marathi", "#FDCB6E",
     "Dr. Kulkarni makes eye visits fun and calm for children and worried parents."),
]

STAFF = [
    ("Admin Aarav", "admin@netracare.demo", "Admin@123", "admin"),
    ("Front Desk Divya", "desk@netracare.demo", "Desk@123", "frontdesk"),
]
DEMO_PATIENTS = [
    ("Priya Sharma", "patient@netracare.demo", "Patient@123", "+91 98450 11223"),
    ("Rahul Nair", "rahul@netracare.demo", "Patient@123", "+91 99001 44556"),
    ("Kavya Reddy", "kavya@netracare.demo", "Patient@123", "+91 98860 77889"),
    ("Imran Khan", "imran@netracare.demo", "Patient@123", "+91 97420 33441"),
]


def _next_open_day(start: dt.date, offset: int) -> dt.date:
    d, n = start, 0
    while True:
        if d.weekday() != 6:
            if n >= offset:
                return d
            n += 1
        d += dt.timedelta(days=1)


def seed(force: bool = False) -> None:
    init_db()
    with session() as conn:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] and not force:
            return
        stamp = services._stamp()
        for name, email, pw, role in STAFF:
            conn.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)",
                         (name, email, hash_password(pw), role, stamp))
        for name, email, specialty, focus, years, room, langs, accent, bio in DOCTORS:
            cur = conn.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)",
                               (name, email, hash_password("Doctor@123"), "doctor", stamp))
            conn.execute("INSERT INTO doctors(user_id,specialty,focus,bio,years,room,languages,accent) VALUES (?,?,?,?,?,?,?,?)",
                         (cur.lastrowid, specialty, focus, bio, years, room, langs, accent))
        for name, email, pw, phone in DEMO_PATIENTS:
            conn.execute("INSERT INTO users(name,email,phone,password_hash,role,created_at) VALUES (?,?,?,?,?,?)",
                         (name, email, phone, hash_password(pw), "patient", stamp))

        desk = services.public_user(conn.execute("SELECT * FROM users WHERE email='desk@netracare.demo'").fetchone())
        pid = {r["email"]: r["id"] for r in conn.execute("SELECT id,email FROM users WHERE role='patient'")}
        today = services.now().date()
        # (patient email, doctor id, day offset among open days, time, reason)
        plan = [
            ("patient@netracare.demo", 4, 1, "10:00", "Routine eye check-up and new glasses"),
            ("patient@netracare.demo", 1, 3, "15:00", "Blurry vision at night, glare from headlights"),
            ("rahul@netracare.demo", 2, 0, "17:00", "Floaters in my left eye, diabetic review"),
            ("kavya@netracare.demo", 5, 1, "11:30", "My son seems to have a squint"),
            ("imran@netracare.demo", 3, 2, "09:30", "Eye pressure follow-up"),
            ("rahul@netracare.demo", 4, 2, "14:30", "Dry, itchy eyes from screen work"),
            ("kavya@netracare.demo", 2, 4, "10:30", "Sudden flashes of light and a shadow in my vision"),
        ]
        for email, doc_id, off, t, reason in plan:
            day = _next_open_day(today, off)
            try:
                services.book(conn, desk, doc_id, day.isoformat(), t, reason, pid[email])
            except services.ServiceError:
                pass  # e.g. a time already in the past today — skip silently

        # Past completed visit for the demo patient (with a published summary)
        past = _next_open_day(today - dt.timedelta(days=21), 0)
        conn.execute(
            """INSERT INTO appointments(patient_id,doctor_id,date,time,reason,status,visit_notes,summary,summary_status,booked_by,created_at)
               VALUES (?,?,?,?,?,'completed',?,?,'published',?,?)""",
            (pid["patient@netracare.demo"], 4, past.isoformat(), "10:30", "Headaches when reading",
             "Routine exam done. Mild change in glasses power. New prescription issued. Review in 6 months.",
             "Thank you for visiting NetraCare. Your doctor recorded that your routine eye exam was completed and "
             "that a small change to your glasses prescription was made, with a new prescription issued. "
             "A review is planned in about 6 months. If anything is unclear, please contact our front desk.",
             desk["id"], stamp))
        services.log(conn, None, "seed", "Demo data created")


if __name__ == "__main__":
    seed()
    print("Seeded demo data.")
