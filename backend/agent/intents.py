"""Intent rules shared by the assistant router and the booking agent."""
import re

TESTS = {"oct": r"\boct\b|retina scan", "visual_field": r"visual field", "fundus": r"fundus|retinal photo",
         "topography": r"topograph", "tonometry": r"tonometr|eye pressure test", "pachymetry": r"pachymetr|corneal thickness"}
_LAB_WORDS = r"\b(lab|oct|scan|visual field|fundus|topograph\w*|tonometr\w*|pachymetr\w*|diagnostic\w*|clearview)\b"
_BOOK_VERB = r"\b(book|schedule|arrange|reserve|make|set up|fix|get|need|want|like|take)\b"


def lab_test_id(text: str) -> str | None:
    t = text.lower()
    return next((k for k, p in TESTS.items() if re.search(p, t)), None)


def intent_of(text: str) -> str | None:
    t = text.lower()
    info_q = re.search(r"\b(policy|policies|allowed|can i|may i|how do i|how to|is it possible|cancellation|fee|charge|refund)\b", t)
    if re.search(r"\b(cancel|call off)\b", t) and not info_q:
        return "cancel_lab" if re.search(r"\bcv-\d+|lab (order|test)\b", t) else "cancel"
    if not info_q and (re.search(r"\b(reschedule|postpone)\b", t) or (
            re.search(r"\b(move|shift|change|push)\b", t) and re.search(r"\b(appointment|booking|visit|slot|it|my)\b", t))):
        return "reschedule"
    if re.search(_LAB_WORDS, t) or re.search(r"\blab tests?\b|\bwhat tests\b", t):
        if re.search(_BOOK_VERB, t) and re.search(r"\b(book|schedule|arrange|reserve)\b", t):
            return "lab_book"
        if re.search(r"\b(price|cost|how much|list|available|offer|which|what|do you|fee|rate)\b", t):
            return "lab_info"
        return "lab_info"
    if re.search(r"\b(my|upcoming|next)\b.{0,25}\b(appointments?|bookings?|visits?)\b", t) and \
            re.search(r"\b(show|list|what|when|do i have|view|check|see|any|status)\b", t) and not re.search(r"\b(book|cancel|move)\b", t):
        return "my_appointments"
    if re.search(r"\b(which|what kind of|what type of|right|best)\b.{0,20}\b(doctor|specialist|dr)\b|\bwho should i (see|consult|visit)\b", t):
        return "route"
    if re.search(_BOOK_VERB, t) and re.search(r"\b(appointment|visit|slot|consultation|check-?up|booking|doctor|dr\.?|session)\b", t) \
            and not re.search(r"\b(how|policy|policies|can i|do i need|what is)\b", t):
        return "book"
    if re.search(r"\bbook (me|us|my|a|an|with|on|for|at)\b", t):
        return "book"
    return None
