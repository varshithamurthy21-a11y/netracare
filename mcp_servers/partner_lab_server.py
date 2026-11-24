"""ClearView Diagnostics — NetraCare's (fictional) partner lab, exposed as an MCP server.

Run:  python -m mcp_servers.partner_lab_server
It owns its own database (partner_lab.db) — NetraCare never touches it directly, only through these tools.
"""
import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mcp_servers.base import MCPServer  # noqa: E402

DB = Path(os.getenv("NETRACARE_LAB_DB", Path(__file__).resolve().parent.parent / "partner_lab.db"))
CATALOG = {
    "oct": {"id": "oct", "name": "OCT retina scan", "price_inr": 1500, "duration_min": 20, "prep": "No special preparation. Bring any previous scans."},
    "visual_field": {"id": "visual_field", "name": "Visual field test", "price_inr": 1200, "duration_min": 30, "prep": "Bring your reading glasses if you use them."},
    "fundus": {"id": "fundus", "name": "Fundus photography", "price_inr": 900, "duration_min": 15, "prep": "Dilating drops may be used; arrange someone to accompany you."},
    "topography": {"id": "topography", "name": "Corneal topography", "price_inr": 1400, "duration_min": 20, "prep": "Contact lens wearers: ask the clinic how long to go without lenses."},
    "tonometry": {"id": "tonometry", "name": "Tonometry (eye pressure)", "price_inr": 500, "duration_min": 10, "prep": "No special preparation."},
    "pachymetry": {"id": "pachymetry", "name": "Pachymetry (corneal thickness)", "price_inr": 700, "duration_min": 10, "prep": "No special preparation."},
}
HOURS = ["08:00", "09:00", "10:00", "11:00", "12:00", "14:00", "15:00", "16:00"]
CAPACITY = 2

server = MCPServer("clearview-diagnostics", "1.0.0",
                   instructions="Partner lab for NetraCare. Book only after the patient has approved. Never interpret results.")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS lab_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, test_id TEXT, patient_name TEXT, patient_email TEXT,
        date TEXT, time TEXT, referring_doctor TEXT, status TEXT DEFAULT 'booked', created_at TEXT)""")
    return c


def _order(r) -> dict:
    d = dict(r)
    d["order_id"] = f"CV-{d.pop('id'):05d}"
    d["test"] = CATALOG[d["test_id"]]["name"]
    d["price_inr"] = CATALOG[d["test_id"]]["price_inr"]
    return d


@server.tool("list_lab_tests", "List the diagnostic tests ClearView offers with indicative prices in rupees.")
def list_lab_tests():
    return {"lab": "ClearView Diagnostics", "tests": list(CATALOG.values())}


@server.tool("get_test_details", "Details, price and preparation notes for one test.",
             {"test_id": {"type": "string", "description": "one of: " + ", ".join(CATALOG)}}, ["test_id"])
def get_test_details(test_id: str):
    if test_id not in CATALOG:
        raise ValueError(f"Unknown test '{test_id}'. Options: {', '.join(CATALOG)}")
    return CATALOG[test_id]


@server.tool("check_lab_slots", "Free appointment times at the lab on a date (YYYY-MM-DD). Closed on Sundays.",
             {"date": {"type": "string"}}, ["date"])
def check_lab_slots(date: str):
    day = dt.date.fromisoformat(date)
    if day.weekday() == 6:
        return {"date": date, "slots": [], "note": "The lab is closed on Sundays."}
    with _conn() as c:
        taken = {r["time"]: r["n"] for r in c.execute(
            "SELECT time, COUNT(*) n FROM lab_orders WHERE date=? AND status='booked' GROUP BY time", (date,))}
    now = dt.datetime.now()
    free = [h for h in HOURS if taken.get(h, 0) < CAPACITY and dt.datetime.combine(day, dt.time.fromisoformat(h)) > now]
    return {"date": date, "slots": free}


@server.tool("book_lab_test", "Book a lab test. Call only after the patient approved.",
             {"test_id": {"type": "string"}, "patient_name": {"type": "string"}, "patient_email": {"type": "string"},
              "date": {"type": "string"}, "time": {"type": "string"}, "referring_doctor": {"type": "string"}},
             ["test_id", "patient_name", "patient_email", "date", "time"])
def book_lab_test(test_id: str, patient_name: str, patient_email: str, date: str, time: str, referring_doctor: str = ""):
    if test_id not in CATALOG:
        raise ValueError(f"Unknown test '{test_id}'")
    if time not in check_lab_slots(date)["slots"]:
        raise ValueError(f"{time} on {date} is not available. Free: {check_lab_slots(date)['slots']}")
    with _conn() as c:
        cur = c.execute("INSERT INTO lab_orders(test_id,patient_name,patient_email,date,time,referring_doctor,created_at) VALUES (?,?,?,?,?,?,?)",
                        (test_id, patient_name, patient_email.lower(), date, time, referring_doctor, dt.datetime.now().isoformat(timespec="seconds")))
        row = c.execute("SELECT * FROM lab_orders WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"booked": True, **_order(row), "note": "Results are shared with the referring NetraCare doctor."}


@server.tool("get_order_status", "Status of a lab order, e.g. CV-00012.", {"order_id": {"type": "string"}}, ["order_id"])
def get_order_status(order_id: str):
    num = int(order_id.upper().replace("CV-", ""))
    with _conn() as c:
        row = c.execute("SELECT * FROM lab_orders WHERE id=?", (num,)).fetchone()
    if not row:
        raise ValueError(f"No order {order_id}")
    return _order(row)


@server.tool("cancel_lab_order", "Cancel a booked lab order.", {"order_id": {"type": "string"}}, ["order_id"])
def cancel_lab_order(order_id: str):
    num = int(order_id.upper().replace("CV-", ""))
    with _conn() as c:
        cur = c.execute("UPDATE lab_orders SET status='cancelled' WHERE id=? AND status='booked'", (num,))
        if not cur.rowcount:
            raise ValueError(f"Order {order_id} not found or not cancellable")
        row = c.execute("SELECT * FROM lab_orders WHERE id=?", (num,)).fetchone()
    return _order(row)


@server.resource("lab://catalog", "Lab test catalog", "All tests with prices", "application/json")
def catalog_resource():
    import json
    return json.dumps(list(CATALOG.values()), indent=2)


if __name__ == "__main__":
    server.serve()
