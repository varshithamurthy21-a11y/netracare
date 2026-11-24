"""NetraCare booking agent: chat that books, cancels and reschedules — with the patient in control.

Flow: understand the message -> fill missing details (doctor / date / time ...) by asking -> PROPOSE the change ->
INTERRUPT and wait for the patient's yes/no -> only then EXECUTE the write tool. State is saved per patient in the
database, so a conversation survives page reloads and server restarts.
"""
import datetime as dt
import json
from dataclasses import dataclass, field

from .. import config, observability, services, triage
from ..mcp_client import MCPError
from . import nlu
from .graph import END, INTERRUPT, Graph
from .intents import intent_of, lab_test_id
from .tools import ApprovalRequired, Toolbox

graph = Graph()
EMPTY = {"flow": None, "slots": {}, "pending": None}


@dataclass
class Ctx:
    conn: object
    actor: dict
    text: str
    tools: Toolbox
    doctors: list
    today: dt.date
    parsed: dict
    intent: str | None
    replies: list = field(default_factory=list)
    quick: list = field(default_factory=list)
    handled: bool = True
    done: bool = False

    def say(self, text: str, quick: list | None = None) -> None:
        self.replies.append(text)
        if quick is not None:
            self.quick = quick

    def doctor(self, did: int) -> dict:
        return next(d for d in self.doctors if d["id"] == did)


def fmt(date: str, time: str | None = None) -> str:
    d = dt.date.fromisoformat(date)
    out = d.strftime("%a %d %b")
    return out + (f", {dt.datetime.strptime(time, '%H:%M').strftime('%I:%M %p').lstrip('0')}" if time else "")


def pt(time: str) -> str:
    return dt.datetime.strptime(time, "%H:%M").strftime("%I:%M %p").lstrip("0")


def next_open_days(today: dt.date, n: int = 3) -> list[str]:
    out, d = [], today + dt.timedelta(days=1)
    while len(out) < n:
        if d.weekday() != 6:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _reset(state: dict) -> None:
    state.update(flow=None, slots={}, pending=None)


# ---------------------------------------------------------------- nodes
@graph.node
def route(ctx: Ctx, state: dict) -> str:
    pending = state.get("pending")
    if pending:
        if nlu.is_yes(ctx.text):
            return "execute"
        if nlu.is_no(ctx.text):
            return "decline"
        if not ctx.intent:  # something else: keep waiting
            ctx.say(f"I'm waiting for your answer on this: {pending['summary']}\n\nShall I go ahead?", ["Yes, go ahead", "No, don't"])
            return INTERRUPT
        state["pending"] = None  # the patient started something new
    if state.get("flow") and not ctx.intent and nlu.is_no(ctx.text):
        return "decline"
    flow = ctx.intent if ctx.intent in ("book", "cancel", "reschedule", "lab_book", "my_appointments", "lab_info", "cancel_lab") else None
    if flow and flow != state.get("flow"):
        state["flow"], state["slots"] = flow, {}
    flow = state.get("flow")
    if not flow:
        ctx.handled = False
        return END
    s = state["slots"]
    for k, v in ctx.parsed.items():
        if k == "specialty" and flow not in ("book",):
            continue
        s[k] = v
    if flow == "book" and triage.detect_red_flags(ctx.text)["red_flag"]:
        # keep the wording that triggered the flag, so the booking itself is flagged for the front desk
        s["reason"] = (s.get("reason", "") + " " + ctx.text).strip()[:300]
    return {"book": "collect_book", "cancel": "collect_cancel", "reschedule": "collect_reschedule", "my_appointments": "list_appts",
            "lab_info": "lab_info", "lab_book": "collect_lab", "cancel_lab": "cancel_lab_unsupported"}[flow]


@graph.node
def list_appts(ctx: Ctx, state: dict) -> str:
    rows = ctx.tools.call("list_my_appointments", {"scope": "upcoming"})
    if not rows:
        ctx.say("You have no upcoming appointments. Would you like me to find a slot?", ["Book an appointment"])
    else:
        lines = [f"• #{a['id']} — {fmt(a['date'], a['time'])} with {a['doctor_name']} ({a['specialty']}){' ⚠ flagged for review' if a['red_flag'] else ''}" for a in rows]
        ctx.say("Here are your upcoming appointments:\n" + "\n".join(lines), ["Cancel an appointment", "Reschedule an appointment"])
    _reset(state)
    return END


@graph.node
def collect_book(ctx: Ctx, state: dict) -> str:
    s = state["slots"]
    if "doctor_id" not in s:
        spec = s.get("specialty")
        match = [d for d in ctx.doctors if d["specialty"] == spec] if spec else []
        if match:
            s["doctor_id"] = match[0]["id"]
            ctx.say(f"For that, {match[0]['name']} ({spec}) is the usual place to start — this is scheduling guidance, not a diagnosis, and the front desk can re-route you.")
        else:
            ctx.say("Which doctor would you like to see? Or tell me what the visit is about and I'll suggest a specialist.",
                    [d["name"] for d in ctx.doctors] + ["General eye check-up"])
            if "general" in ctx.text.lower():
                s["doctor_id"] = next((d["id"] for d in ctx.doctors if d["specialty"] == triage.DEFAULT_SPECIALTY), ctx.doctors[0]["id"])
            else:
                return END
    doc = ctx.doctor(s["doctor_id"])
    if "date" not in s:
        ctx.say(f"Which day suits you for {doc['name']}? (We're open Mon–Sat.)", [fmt(d) + "" for d in next_open_days(ctx.today)])
        s["_date_labels"] = {fmt(d): d for d in next_open_days(ctx.today)}
        return END
    free = ctx.tools.call("get_slots", {"doctor_id": s["doctor_id"], "date": s["date"]})
    if not free:
        ctx.say(f"There are no free times with {doc['name']} on {fmt(s['date'])}. Please pick another day.", [fmt(d) for d in next_open_days(ctx.today)])
        s.pop("date")
        return END
    if "time" in s and s["time"] not in free:
        near = nlu.nearest_slot(s["time"], free)
        ctx.say(f"{pt(s['time'])} isn't available on {fmt(s['date'])}. The closest free time is {pt(near)}.", [pt(f) for f in free[:6]])
        s["time_asked"] = True
        s.pop("time")
        return END
    if "time" not in s:
        if s.get("time_pref"):
            pref = [f for f in free if nlu.match_pref(f, s["time_pref"])] or free
        else:
            pref = free
        ctx.say(f"{doc['name']} has these times free on {fmt(s['date'])}. Which one would you like?", [pt(f) for f in pref[:8]])
        s["_time_labels"] = {pt(f): f for f in pref[:8]}
        return END
    return "propose_book"


@graph.node
def propose_book(ctx: Ctx, state: dict) -> str:
    s = state["slots"]
    doc = ctx.doctor(s["doctor_id"])
    reason = s.get("reason", "")
    flags = triage.detect_red_flags(reason or ctx.text)
    summary = f"Book {doc['name']} ({doc['specialty']}) on {fmt(s['date'], s['time'])}" + (f' — reason: "{reason}"' if reason else "")
    state["pending"] = {"action": "book_appointment", "args": {"doctor_id": s["doctor_id"], "date": s["date"], "time": s["time"], "reason": reason},
                        "summary": summary}
    msg = f"Please confirm: {summary}."
    if flags["red_flag"]:
        msg += "\n\n⚠ Your message mentions something our team would like to review quickly, so the front desk will be alerted and may call you."
    ctx.say(msg + "\n\nShall I book it?", ["Yes, book it", "No, don't"])
    return INTERRUPT


def _my_upcoming(ctx: Ctx) -> list[dict]:
    return [a for a in ctx.tools.call("list_my_appointments", {"scope": "upcoming"}) if a["status"] == "booked"]


def _pick_appointment(ctx: Ctx, state: dict, verb: str):
    appts = _my_upcoming(ctx)
    s = state["slots"]
    if not appts:
        ctx.say(f"You don't have any upcoming appointments to {verb}.", ["Book an appointment"])
        _reset(state)
        return None
    chosen = None
    if s.get("appointment_id"):
        chosen = next((a for a in appts if a["id"] == s["appointment_id"]), None)
        if not chosen:
            ctx.say(f"I can't find an upcoming appointment #{s['appointment_id']} on your account.")
            s.pop("appointment_id")
    if not chosen and len(appts) == 1:
        chosen = appts[0]
    if not chosen:
        lines = [f"• #{a['id']} — {fmt(a['date'], a['time'])} with {a['doctor_name']}" for a in appts]
        ctx.say(f"Which appointment would you like to {verb}?\n" + "\n".join(lines), [f"#{a['id']}" for a in appts])
        return None
    s["appointment_id"] = chosen["id"]
    return chosen


@graph.node
def collect_cancel(ctx: Ctx, state: dict) -> str:
    a = _pick_appointment(ctx, state, "cancel")
    if not a:
        return END
    summary = f"Cancel appointment #{a['id']} — {fmt(a['date'], a['time'])} with {a['doctor_name']}"
    state["pending"] = {"action": "cancel_appointment", "args": {"appointment_id": a["id"]}, "summary": summary}
    ctx.say(f"Please confirm: {summary}.\n\nShall I cancel it? The slot will be released straight away.", ["Yes, cancel it", "No, keep it"])
    return INTERRUPT


@graph.node
def collect_reschedule(ctx: Ctx, state: dict) -> str:
    s = state["slots"]
    keep = {k: s[k] for k in ("date", "time", "time_pref") if k in s}
    a = _pick_appointment(ctx, state, "reschedule")
    if not a:
        return END
    s.update(keep)
    if "date" not in s:
        ctx.say(f"Which new day would you like for your visit with {a['doctor_name']}? (Currently {fmt(a['date'], a['time'])}.)", [fmt(d) for d in next_open_days(ctx.today)])
        return END
    free = ctx.tools.call("get_slots", {"doctor_id": a["doctor_id"], "date": s["date"]})
    if not free:
        ctx.say(f"No free times on {fmt(s['date'])}. Please pick another day.", [fmt(d) for d in next_open_days(ctx.today)])
        s.pop("date")
        return END
    if "time" in s and s["time"] not in free:
        near = nlu.nearest_slot(s["time"], free)
        ctx.say(f"{pt(s['time'])} isn't free on {fmt(s['date'])}. Closest: {pt(near)}.", [pt(f) for f in free[:6]])
        s.pop("time")
        return END
    if "time" not in s:
        pref = [f for f in free if s.get("time_pref") and nlu.match_pref(f, s["time_pref"])] or free
        ctx.say(f"Free times on {fmt(s['date'])}:", [pt(f) for f in pref[:8]])
        return END
    summary = f"Move appointment #{a['id']} with {a['doctor_name']} from {fmt(a['date'], a['time'])} to {fmt(s['date'], s['time'])}"
    state["pending"] = {"action": "reschedule_appointment", "args": {"appointment_id": a["id"], "date": s["date"], "time": s["time"]}, "summary": summary}
    ctx.say(f"Please confirm: {summary}.\n\nShall I move it?", ["Yes, move it", "No, keep it"])
    return INTERRUPT


@graph.node
def lab_info(ctx: Ctx, state: dict) -> str:
    try:
        tests = ctx.tools.call("list_lab_tests")
    except (MCPError, OSError) as exc:
        ctx.handled = False  # let the RAG answer from the knowledge base instead
        ctx.say("")
        ctx.replies.clear()
        _reset(state)
        return END
    wanted = lab_test_id(ctx.text)
    shown = [t for t in tests if t["id"] == wanted] or tests
    lines = [f"• {t['name']} — ₹{t['price_inr']} (about {t['duration_min']} min). {t['prep']}" for t in shown]
    ctx.say("Our partner lab, ClearView Diagnostics, offers (indicative prices):\n" + "\n".join(lines)
            + "\n\nI can book one for you if you'd like. I can't interpret results or advise on which test you need — your doctor does that.",
            ["Book an OCT scan"] if not wanted else [f"Book {shown[0]['name']}"])
    _reset(state)
    return END


@graph.node
def cancel_lab_unsupported(ctx: Ctx, state: dict) -> str:
    ctx.say("To change a lab booking, please call the front desk on +91 80 4000 1234 with your order number (it starts with CV-).")
    _reset(state)
    return END


@graph.node
def collect_lab(ctx: Ctx, state: dict) -> str:
    s = state["slots"]
    if "test_id" not in s:
        t = lab_test_id(ctx.text)
        if t:
            s["test_id"] = t
        else:
            try:
                tests = ctx.tools.call("list_lab_tests")
            except (MCPError, OSError):
                ctx.say("The partner lab system isn't reachable right now. Please try again shortly or call the front desk.")
                _reset(state)
                return END
            ctx.say("Which test would you like to book?", [t["name"] for t in tests])
            return END
    if "date" not in s:
        ctx.say("Which day would you like the test? (The lab is open Mon–Sat.)", [fmt(d) for d in next_open_days(ctx.today)])
        return END
    try:
        free = ctx.tools.call("check_lab_slots", {"date": s["date"]})
    except (MCPError, OSError):
        ctx.say("The partner lab system isn't reachable right now. Please try again shortly.")
        _reset(state)
        return END
    if not free:
        ctx.say(f"The lab has no free times on {fmt(s['date'])}. Please pick another day.", [fmt(d) for d in next_open_days(ctx.today)])
        s.pop("date")
        return END
    if "time" in s and s["time"] not in free:
        ctx.say(f"{pt(s['time'])} isn't free. Available: " + ", ".join(pt(f) for f in free), [pt(f) for f in free])
        s.pop("time")
        return END
    if "time" not in s:
        ctx.say(f"Free lab times on {fmt(s['date'])}:", [pt(f) for f in free])
        return END
    tests = {t["id"]: t for t in ctx.tools.call("list_lab_tests")}
    t = tests[s["test_id"]]
    summary = f"Book {t['name']} (₹{t['price_inr']}) at ClearView Diagnostics on {fmt(s['date'], s['time'])}"
    state["pending"] = {"action": "book_lab_test", "args": {"test_id": s["test_id"], "date": s["date"], "time": s["time"]}, "summary": summary}
    ctx.say(f"Please confirm: {summary}.\n\nShall I book it?", ["Yes, book it", "No, don't"])
    return INTERRUPT


@graph.node
def execute(ctx: Ctx, state: dict) -> str:
    p = state["pending"]
    try:
        res = ctx.tools.call(p["action"], p["args"], approved=True)  # the ONLY place a write is approved
    except services.ServiceError as exc:
        ctx.say(f"I couldn't do that: {exc.message}", ["Show my appointments"])
        state["pending"] = None
        return END
    except (MCPError, OSError) as exc:
        ctx.say(f"The lab system couldn't complete that: {exc}")
        state["pending"] = None
        return END
    if p["action"] == "book_appointment":
        extra = "\n\n⚠ Your message was flagged for front-desk review; they may call you." if res.get("red_flag") else ""
        ctx.say(f"✅ Booked! Appointment #{res['id']} with {res['doctor_name']} on {fmt(res['date'], res['time'])} ({res['room']}). "
                f"Please arrive 10 minutes early.{extra}", ["Show my appointments"])
    elif p["action"] == "cancel_appointment":
        ctx.say(f"✅ Appointment #{res['id']} is cancelled and the slot has been released.", ["Book an appointment"])
    elif p["action"] == "reschedule_appointment":
        ctx.say(f"✅ Moved! Appointment #{res['id']} is now on {fmt(res['date'], res['time'])} with {res['doctor_name']}.", ["Show my appointments"])
    elif p["action"] == "book_lab_test":
        ctx.say(f"✅ Lab test booked: order {res['order_id']} — {res['test']} on {fmt(res['date'], res['time'])}. Results are shared with your NetraCare doctor.")
    ctx.done = True
    _reset(state)
    return END


@graph.node
def decline(ctx: Ctx, state: dict) -> str:
    ctx.say("No problem — I haven't changed anything. Is there anything else I can help with?")
    _reset(state)
    return END


# ---------------------------------------------------------------- public API
def load_state(conn, user_id: int) -> dict:
    row = conn.execute("SELECT state FROM agent_sessions WHERE user_id=?", (user_id,)).fetchone()
    return json.loads(row["state"]) if row else json.loads(json.dumps(EMPTY))


def save_state(conn, user_id: int, state: dict) -> None:
    conn.execute("INSERT OR REPLACE INTO agent_sessions(user_id,state,updated_at) VALUES (?,?,?)",
                 (user_id, json.dumps(state), services._stamp()))


def _resolve_labels(text: str, state: dict) -> str:
    """Quick-reply buttons send labels like 'Thu 26 Nov' or '10:30 AM'; map them back to ISO values."""
    s = state.get("slots", {})
    for key in ("_date_labels", "_time_labels"):
        for label, value in (s.get(key) or {}).items():
            if text.strip() == label:
                return value
    return text


def is_active(state: dict) -> bool:
    return bool(state.get("flow") or state.get("pending"))


def handle(conn, actor: dict, text: str) -> dict:
    """Process one patient message. Returns {handled, reply, quick_replies, pending, flow}."""
    if actor["role"] != "patient":
        return {"handled": True, "reply": "The booking assistant is for patients. Staff can use the Appointments pages.", "quick_replies": [], "pending": None, "flow": None}
    state = load_state(conn, actor["id"])
    doctors = services.list_doctors(conn)
    today = services.now().date()
    text = _resolve_labels(text, state)
    # quick-reply labels like "Thu 26 Nov" / "Dr. X" / "#12" are parsed like normal text
    parsed = nlu.extract(text, doctors, today)
    if state.get("flow") == "book" and re_label_date(text, today) and "date" not in parsed:
        parsed["date"] = re_label_date(text, today)
    intent = intent_of(text)
    ctx = Ctx(conn, actor, text, Toolbox(conn, actor), doctors, today, parsed, intent)
    with observability.span("agent", intent=intent, flow=state.get("flow")):
        outcome = graph.run("route", ctx, state)
    save_state(conn, actor["id"], state)
    return {"handled": ctx.handled, "reply": "\n\n".join(r for r in ctx.replies if r), "quick_replies": ctx.quick if outcome != END or ctx.replies else [],
            "pending": state.get("pending"), "flow": state.get("flow"), "done": ctx.done}


def re_label_date(text: str, today: dt.date) -> str | None:
    """'Thu 26 Nov' style labels from quick-reply buttons."""
    import re
    m = re.fullmatch(r"\s*(?:mon|tue|wed|thu|fri|sat|sun)\w*\s+(\d{1,2})\s+([A-Za-z]{3})\w*\s*", text)
    return nlu.parse_date(f"{m[1]} {m[2]}", today) if m else None


def confirm(conn, actor: dict, approve: bool) -> dict:
    """Button handler for the approval card (same path as typing yes / no)."""
    return handle(conn, actor, "yes" if approve else "no")


def reset(conn, actor: dict) -> None:
    conn.execute("DELETE FROM agent_sessions WHERE user_id=?", (actor["id"],))
