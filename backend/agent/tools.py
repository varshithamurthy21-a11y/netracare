"""Tools the booking agent can call. Write tools are *physically unable* to run without approval.

Read tools (search, slots, list) run freely. Write tools (book/cancel/reschedule appointments, book a lab test)
raise ApprovalRequired unless `approved=True`, which only the human-approval node sets.
"""
from .. import mcp_client, observability, services


class ApprovalRequired(Exception):
    pass


WRITE_TOOLS = {"book_appointment", "cancel_appointment", "reschedule_appointment", "book_lab_test"}

TOOL_SPECS = [
    {"name": "search_doctors", "write": False, "description": "List doctors, optionally by specialty keyword."},
    {"name": "get_slots", "write": False, "description": "Free appointment times for a doctor on a date."},
    {"name": "list_my_appointments", "write": False, "description": "The signed-in patient's appointments."},
    {"name": "book_appointment", "write": True, "description": "Book an appointment (needs patient approval)."},
    {"name": "cancel_appointment", "write": True, "description": "Cancel an appointment (needs patient approval)."},
    {"name": "reschedule_appointment", "write": True, "description": "Move an appointment (needs patient approval)."},
    {"name": "list_lab_tests", "write": False, "description": "Partner-lab tests and prices (via MCP)."},
    {"name": "check_lab_slots", "write": False, "description": "Partner-lab free times on a date (via MCP)."},
    {"name": "book_lab_test", "write": True, "description": "Book a partner-lab test via MCP (needs patient approval)."},
]


class Toolbox:
    def __init__(self, conn, actor: dict):
        self.conn, self.actor = conn, actor

    def call(self, name: str, args: dict | None = None, approved: bool = False):
        args = args or {}
        if name in WRITE_TOOLS and not approved:
            raise ApprovalRequired(f"'{name}' changes data and needs the patient's approval first.")
        if not hasattr(self, f"_{name}"):
            raise ValueError(f"Unknown tool {name}")
        with observability.span(f"tool:{name}", args={k: v for k, v in args.items() if k != "reason"}, write=name in WRITE_TOOLS):
            return getattr(self, f"_{name}")(**args)

    # ---- appointment tools (call the same service layer as the website) ----
    def _search_doctors(self, specialty: str = ""):
        docs = services.list_doctors(self.conn)
        return [d for d in docs if specialty.lower() in (d["specialty"] + " " + d["focus"]).lower()]

    def _get_slots(self, doctor_id: int, date: str):
        return [s["time"] for s in services.get_slots(self.conn, doctor_id, date) if s["available"]]

    def _list_my_appointments(self, scope: str = "upcoming"):
        return services.list_appointments(self.conn, self.actor, scope=scope)

    def _book_appointment(self, doctor_id: int, date: str, time: str, reason: str = ""):
        return services.book(self.conn, self.actor, doctor_id, date, time, reason)

    def _cancel_appointment(self, appointment_id: int):
        return services.cancel(self.conn, self.actor, appointment_id)

    def _reschedule_appointment(self, appointment_id: int, date: str, time: str):
        return services.reschedule(self.conn, self.actor, appointment_id, date, time)

    # ---- partner lab tools (reached through the MCP client) ----
    def _list_lab_tests(self):
        return mcp_client.call_lab("list_lab_tests")["tests"]

    def _check_lab_slots(self, date: str):
        return mcp_client.call_lab("check_lab_slots", {"date": date})["slots"]

    def _book_lab_test(self, test_id: str, date: str, time: str, referring_doctor: str = ""):
        return mcp_client.call_lab("book_lab_test", {
            "test_id": test_id, "patient_name": self.actor["name"], "patient_email": self.actor["email"],
            "date": date, "time": time, "referring_doctor": referring_doctor})
