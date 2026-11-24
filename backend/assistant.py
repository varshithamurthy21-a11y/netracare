"""The NetraCare assistant: one chat entry point that decides what each message needs.

   message ─► guardrails ─► router ─┬─► red-flag notice (human review, emergency pointer)
                                     ├─► medical-advice refusal (+ offer to book / route)
                                     ├─► specialist routing
                                     ├─► booking agent (book / cancel / reschedule / lab, with approval)
                                     └─► RAG answer with citations

Every request is traced (spans, latency, token + cost estimates) for the Evals & Traces page.
"""
import re

from . import config, observability, rag, services, skills, triage
from .agent import agent, nlu
from .agent.intents import intent_of

INJECTION = re.compile(
    r"ignore (all |any |the |your )?(previous|prior|above|earlier)?\s*(instructions|rules|prompt)|system prompt|reveal your (prompt|instructions)|"
    r"you are now|pretend (to be|you are)|jailbreak|developer mode|act as (an? )?(doctor|ophthalmologist|physician)|disregard (your|the) (rules|guidelines)", re.I)
MEDICAL = [
    r"\b(diagnose|prescribe|home remed(y|ies)|how (do i|to|can i) (treat|cure|heal|fix my))\b",
    r"\b(which|what)\b.{0,30}\b(drops?|medicine|medication|tablets?|antibiotics?|ointment|cream)\b.{0,30}\b(should|can|for|to (use|take|put))\b",
    r"\b(should i|can i|is it (ok|okay|safe) to)\b.{0,40}\b(take|use|put|apply|stop|continue)\b.{0,30}\b(drops?|medicine|medication|tablets?|antibiotics?|steroids?|ointment|paracetamol|ibuprofen|lenses|contacts)\b",
    r"\b(do i have|could (it|this) be|is (it|this) (a |an )?|am i (getting|developing))\b.{0,30}\b(cataract|glaucoma|infection|conjunctivitis|pink eye|detach\w*|cancer|tumou?r|diabet\w*|retinopathy|stye|ulcer|something wrong)\b",
    r"\bis (it|this|that) (serious|dangerous|normal|safe|contagious|an infection)\b",
    r"\b(will i|am i going to) (go blind|lose (my )?(sight|vision))\b",
    r"\bwhy (is|are|does|do) my (eyes?|vision)\b",
    r"\b(dosage|dose|how many drops|how often (should|do) i)\b",
    r"\bwhat (is|are) (causing|the cause of)\b.{0,30}\b(eye|vision|pain|redness)\b",
]
GREETING = re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|namaste|thanks?|thank you|ok thanks|bye)\b[\s!.,]*$", re.I)
QUESTION = re.compile(r"\?\s*$|^\s*(what|when|where|who|why|how|do you|does|is|are|can|could|will|which|tell me)\b", re.I)

EMERGENCY_QUICK = ["Book an urgent appointment", "What are your opening hours?"]
OPTIONS = ["Book an appointment", "Which doctor should I see?", "What are your fees?", "Show my appointments"]


def is_medical_advice(text: str) -> bool:
    return any(re.search(p, text, re.I) for p in MEDICAL)


def is_injection(text: str) -> bool:
    return bool(INJECTION.search(text))


def classify(text: str, agent_state: dict | None = None) -> str:
    """Cheap, explainable routing label (also used by the evals)."""
    if is_injection(text):
        return "injection"
    if triage.detect_red_flags(text)["red_flag"] and not intent_of(text):
        return "emergency"
    if is_medical_advice(text):
        return "medical_advice"
    if GREETING.match(text):
        return "smalltalk"
    it = intent_of(text)
    if it:
        return {"book": "booking", "cancel": "cancel", "reschedule": "reschedule", "my_appointments": "my_appointments",
                "lab_info": "lab_info", "lab_book": "lab_booking", "route": "route", "cancel_lab": "lab_info"}.get(it, it)
    if agent_state and agent.is_active(agent_state) and not QUESTION.search(text):
        return "agent_continue"
    return "faq"


def _result(reply: str, intent: str, **extra) -> dict:
    return {"reply": reply, "intent": intent, "citations": [], "quick_replies": [], "pending": None, "grounded": None,
            "flagged": False, **extra}


def _route_reply(conn, text: str) -> dict:
    route = triage.route_to_specialty(text)
    docs = [d for d in services.list_doctors(conn) if d["specialty"] == route["specialty"]]
    doc = docs[0] if docs else None
    if not doc:
        return _result("I'm not sure which doctor suits that — the front desk can help you choose: +91 80 4000 1234.", "route")
    note = "" if route["confident"] else " I couldn't match specific keywords, so a general eye check-up is the usual starting point."
    reply = (f"Based on what you've described, {doc['name']} ({doc['specialty']}) is the usual place to start. {doc['focus']}.{note}\n\n"
             f"This is scheduling guidance, not a diagnosis — the front desk can re-route you if needed.")
    return _result(reply, "route", quick_replies=[f"Book with {doc['name']}", "Show me all doctors"],
                   citations=[{"n": 1, "title": "NetraCare Doctors", "heading": doc["name"], "id": f"doctor#{doc['id']}", "snippet": doc["focus"]}])


def _medical_refusal(conn, text: str) -> dict:
    route = triage.route_to_specialty(text)
    doc = next((d for d in services.list_doctors(conn) if d["specialty"] == route["specialty"]), None)
    reply = ("I can't give medical advice, diagnosis or treatment guidance — that needs an eye doctor who can examine you. "
             "What I can do is help you see the right specialist")
    quick = ["Book an appointment"]
    if doc:
        reply += f": {doc['name']} ({doc['specialty']}) is the usual place to start"
        quick = [f"Book with {doc['name']}"]
    reply += ". Would you like me to find a time? If anything feels urgent, please call the front desk (+91 80 4000 1234) or go to an emergency department."
    return _result(reply, "medical_advice", quick_replies=quick)


def handle_message(conn, actor: dict, text: str) -> dict:
    text = (text or "").strip()[:800]
    with observability.trace("assistant", actor["id"], text, conn=conn) as tr:
        out = _handle(conn, actor, text)
        tr.output, tr.intent = out["reply"], out["intent"]
    return out


def _handle(conn, actor: dict, text: str) -> dict:
    if not text:
        return _result("Hi! I can answer questions about NetraCare and help you book, cancel or reschedule. What would you like to do?", "smalltalk", quick_replies=OPTIONS)
    state = agent.load_state(conn, actor["id"]) if actor["role"] == "patient" else {}
    with observability.span("guard") as sp:
        label = classify(text, state)
        flags = triage.detect_red_flags(text)
        sp["label"], sp["red_flag"] = label, flags["red_flag"]

    if label == "injection":
        return _result("I can only help with NetraCare questions and appointments, and I follow the clinic's safety rules. How can I help with your visit?", "injection", quick_replies=OPTIONS)
    if label == "smalltalk":
        return _result("Hello! I'm NetraCare's front-desk assistant. I can answer questions and help with appointments. I can't give medical advice.", "smalltalk", quick_replies=OPTIONS)
    if label == "emergency":
        services.log(conn, actor, "assistant_red_flag", f"{flags['reasons']} :: {text[:200]}")
        return _result(flags["patient_message"], "emergency", flagged=True, quick_replies=EMERGENCY_QUICK)
    if label == "medical_advice":
        return _medical_refusal(conn, text)

    prefix = ""
    if flags["red_flag"]:  # a booking request that mentions a possible red flag: help book, and escalate to humans
        services.log(conn, actor, "assistant_red_flag", f"{flags['reasons']} :: {text[:200]}")
        prefix = flags["patient_message"] + "\n\n"

    # an informational question while an approval is pending: answer it, keep the pending request alive
    if state and agent.is_active(state) and label == "faq":
        ans = rag.answer(text, conn, system_extra=skills.system_prompt(text))
        reply = ans["answer"]
        if state.get("pending"):
            reply += f"\n\n(Your request is still waiting for your answer: {state['pending']['summary']}. Say yes or no.)"
        return _result(reply, "faq", citations=ans["citations"], grounded=ans["grounded"],
                       quick_replies=["Yes, go ahead", "No, don't"] if state.get("pending") else [])

    if label == "route":
        return _result(prefix + _route_reply(conn, text)["reply"], "route", **{k: v for k, v in _route_reply(conn, text).items() if k in ("quick_replies", "citations")}, flagged=bool(prefix))

    if label in ("booking", "cancel", "reschedule", "my_appointments", "lab_info", "lab_booking", "agent_continue") or (state and agent.is_active(state)):
        if actor["role"] != "patient":
            return _result("Booking through chat is available to patients. Staff can use the Appointments pages.", label)
        res = agent.handle(conn, actor, text)
        if res["handled"] and res["reply"]:
            return _result(prefix + res["reply"], label if label != "agent_continue" else (res["flow"] or "agent"), quick_replies=res["quick_replies"],
                           pending=res["pending"], flagged=bool(prefix))
        # agent could not help (e.g. lab server down): fall through to the knowledge base

    ans = rag.answer(text, conn, system_extra=skills.system_prompt(text))
    quick = [] if ans["grounded"] else ["Book an appointment", "What are your opening hours?"]
    return _result(prefix + ans["answer"], "faq", citations=ans["citations"], grounded=ans["grounded"], quick_replies=quick, flagged=bool(prefix))


def confirm(conn, actor: dict, approve: bool) -> dict:
    with observability.trace("assistant.confirm", actor["id"], "approve" if approve else "decline", conn=conn) as tr:
        res = agent.confirm(conn, actor, approve)
        tr.output, tr.intent = res["reply"], "approval_yes" if approve else "approval_no"
    return _result(res["reply"], "approval", quick_replies=res["quick_replies"], pending=res["pending"])


def reset(conn, actor: dict) -> None:
    agent.reset(conn, actor)
