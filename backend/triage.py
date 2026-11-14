"""Red-flag detection and doctor routing.

Both are deliberately rule-based and conservative. They never diagnose or advise:
they only (a) alert staff that a request may be urgent and (b) suggest which
specialist's calendar to look at. Iteration 2 upgrades the classifier to an LLM
(LangChain) with these rules kept as a safety net.
"""
import re

RED_FLAGS = {
    "sudden vision loss": r"sudden(ly)?\W+(loss of vision|vision loss|lost (my )?vision|blind|can'?t see|cannot see)|lost (my )?vision|went blind",
    "flashes or curtain/shadow": r"flashes?|curtain|shadow (over|in)|veil",
    "eye injury or trauma": r"injur|hit (in|on) (the |my )?eye|poked|scratched|trauma|accident|struck",
    "chemical exposure": r"chemical|acid|bleach|splash|pepper spray",
    "severe eye pain": r"severe(ly)? (eye )?pain|unbearable|excruciating|intense pain",
    "pain with nausea/halos": r"(halo|rainbow).*(nausea|vomit|pain)|(nausea|vomit).*(eye|vision)",
    "sudden double vision": r"sudden(ly)?\W+double vision|suddenly seeing double",
    "bleeding in the eye": r"bleed|blood in (my |the )?eye",
}

SPECIALTY_KEYWORDS = {
    "Cataract & Lens Surgery": r"cataract|cloudy|foggy|glare|lens implant|iol|blurr?y at night|faded colou?rs",
    "Retina & Vitreous": r"retina|floaters?|diabet|flashes|curtain|macula|vitre|detach",
    "Glaucoma": r"glaucoma|eye pressure|tunnel vision|optic nerve|iop|halo",
    "Cornea & Refractive": r"cornea|lasik|contact lens|dry eyes?|itch|red eye|glasses|spectacle|power|refractive|ulcer|burning|watering|check-?up",
    "Pediatric Ophthalmology & Squint": r"child|kid|son\b|daughter|baby|toddler|squint|lazy eye|crossed eye|school",
}
DEFAULT_SPECIALTY = "Cornea & Refractive"  # general eye exams and glasses


def detect_red_flags(text: str) -> dict:
    text = (text or "").lower()
    hits = [name for name, pattern in RED_FLAGS.items() if re.search(pattern, text)]
    return {
        "red_flag": bool(hits),
        "reasons": hits,
        "staff_note": (
            "Possible urgent request: " + ", ".join(hits) + ". Front desk to review and call the patient."
            if hits else ""
        ),
        "patient_message": (
            "Your message mentions something that our team would like to review quickly. "
            "We've flagged it for the front desk, who will contact you. If you have sudden "
            "vision loss or a serious eye injury, please go to the nearest emergency "
            "department or call local emergency services now."
            if hits else ""
        ),
    }


def route_to_specialty(text: str) -> dict:
    text = (text or "").lower()
    scores = {s: len(re.findall(p, text)) for s, p in SPECIALTY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return {"specialty": DEFAULT_SPECIALTY, "confident": False,
                "why": "No specific keywords found, so a general eye examination is the usual starting point. The front desk can re-route you."}
    return {"specialty": best, "confident": scores[best] >= 2,
            "why": "Matched against the doctors' areas of focus (this is scheduling guidance, not a diagnosis)."}
