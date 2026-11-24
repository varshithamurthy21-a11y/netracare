"""NetraCare clinic MCP server: lets MCP clients (Claude Desktop, agents) use the clinic's own tools.

Run:  python -m mcp_servers.clinic_server
Actions run as a front-desk service account (env NETRACARE_MCP_ACTOR, default desk@netracare.demo), so they
obey the same rules and audit log as the web app: no double booking, hours, limits.
"""
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import rag, services, triage  # noqa: E402
from backend.db import session  # noqa: E402
from backend.seed import seed  # noqa: E402
from mcp_servers.base import MCPServer  # noqa: E402

server = MCPServer("netracare-clinic", "1.0.0",
                   instructions="Tools for NetraCare eye clinic scheduling. Confirm with the patient before booking or cancelling. "
                                "Never give medical advice.")
ACTOR_EMAIL = os.getenv("NETRACARE_MCP_ACTOR", "desk@netracare.demo")


def _actor(conn):
    row = conn.execute("SELECT id FROM users WHERE email=? AND role IN ('frontdesk','admin') AND active=1", (ACTOR_EMAIL,)).fetchone()
    if not row:
        raise RuntimeError(f"MCP actor {ACTOR_EMAIL} not found")
    return services.get_user(conn, row["id"])


def _patient(conn, email: str) -> dict:
    row = conn.execute("SELECT id FROM users WHERE email=? AND role='patient' AND active=1", (email.strip().lower(),)).fetchone()
    if not row:
        raise ValueError(f"No patient with email {email}")
    return services.get_user(conn, row["id"])


@server.tool("search_doctors", "List NetraCare doctors, optionally filtered by a specialty keyword (e.g. 'retina').",
             {"specialty": {"type": "string"}})
def search_doctors(specialty: str = ""):
    with session() as c:
        docs = services.list_doctors(c)
    docs = [d for d in docs if specialty.lower() in (d["specialty"] + " " + d["focus"]).lower()]
    return [{k: d[k] for k in ("id", "name", "specialty", "focus", "room", "languages")} for d in docs]


@server.tool("route_to_specialist", "Suggest which specialist's calendar to look at for a patient's description. Scheduling guidance only, not a diagnosis.",
             {"description": {"type": "string"}}, ["description"])
def route_to_specialist(description: str):
    flags = triage.detect_red_flags(description)
    route = triage.route_to_specialty(description)
    return {"specialty": route["specialty"], "confident": route["confident"], "red_flag": flags["red_flag"],
            "staff_note": flags["staff_note"], "disclaimer": "Scheduling guidance only; not medical advice."}


@server.tool("check_availability", "Free slots for a doctor on a date (YYYY-MM-DD).",
             {"doctor_id": {"type": "integer"}, "date": {"type": "string"}}, ["doctor_id", "date"])
def check_availability(doctor_id: int, date: str):
    with session() as c:
        return {"doctor_id": doctor_id, "date": date, "free": [s["time"] for s in services.get_slots(c, doctor_id, date) if s["available"]]}


@server.tool("list_appointments", "A patient's appointments (by email).",
             {"patient_email": {"type": "string"}, "scope": {"type": "string", "enum": ["upcoming", "past"]}}, ["patient_email"])
def list_appointments(patient_email: str, scope: str = "upcoming"):
    with session() as c:
        p = _patient(c, patient_email)
        rows = services.list_appointments(c, p, scope=scope)
    return [{k: a[k] for k in ("id", "date", "time", "doctor_name", "specialty", "status")} for a in rows]


@server.tool("book_appointment", "Book an appointment for a patient. Only call after the patient approved.",
             {"patient_email": {"type": "string"}, "doctor_id": {"type": "integer"}, "date": {"type": "string"},
              "time": {"type": "string"}, "reason": {"type": "string"}}, ["patient_email", "doctor_id", "date", "time"])
def book_appointment(patient_email: str, doctor_id: int, date: str, time: str, reason: str = ""):
    with session() as c:
        a = services.book(c, _actor(c), doctor_id, date, time, reason, _patient(c, patient_email)["id"])
    return {"booked": True, "appointment_id": a["id"], "doctor": a["doctor_name"], "date": a["date"], "time": a["time"],
            "flagged_for_review": bool(a["red_flag"])}


@server.tool("cancel_appointment", "Cancel an appointment by id. Only call after the patient approved.",
             {"appointment_id": {"type": "integer"}}, ["appointment_id"])
def cancel_appointment(appointment_id: int):
    with session() as c:
        a = services.cancel(c, _actor(c), appointment_id)
    return {"cancelled": True, "appointment_id": a["id"], "status": a["status"]}


@server.tool("ask_clinic_kb", "Answer a question about NetraCare (hours, fees, policies, procedures) with citations.",
             {"question": {"type": "string"}}, ["question"])
def ask_clinic_kb(question: str):
    with session() as c:
        r = rag.answer(question, c)
    return {"answer": r["answer"], "grounded": r["grounded"], "citations": [f"{x['title']} — {x['heading']}" for x in r["citations"]]}


@server.resource("clinic://policies", "Booking policies", "NetraCare booking, cancellation and privacy policies", "text/markdown")
def policies():
    return (rag.KB_DIR / "policies.md").read_text(encoding="utf-8")


@server.resource("clinic://doctors", "Doctors", "NetraCare doctors and specialties", "application/json")
def doctors_resource():
    import json
    with session() as c:
        return json.dumps([{k: d[k] for k in ("id", "name", "specialty", "focus", "room")} for d in services.list_doctors(c)], indent=2)


if __name__ == "__main__":
    seed()
    server.serve()
