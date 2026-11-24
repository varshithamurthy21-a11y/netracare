"""Turns a patient's message into structured slots (doctor, date, time, reason, appointment id...).

Rule-based so it is fast, free and testable. When an LLM key is configured, `extract` first asks the LLM for
JSON and then falls back to / merges with the rules, so a model outage never breaks booking.
"""
import datetime as dt
import json
import re

from .. import llm, triage

DAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thur": 3,
        "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
YES = re.compile(r"^\s*(yes|yep|yeah|yup|ok|okay|sure|confirm|confirmed|approve|go ahead|do it|please do|correct|that'?s right|looks good)\b", re.I)
NO = re.compile(r"^\s*(no|nope|nah|don'?t|do not|decline|stop|never ?mind|not now|cancel that|wrong)\b", re.I)


def is_yes(text: str) -> bool:
    return bool(YES.match(text))


def is_no(text: str) -> bool:
    return bool(NO.match(text))


def parse_date(text: str, today: dt.date) -> str | None:
    t = text.lower()
    if "day after tomorrow" in t:
        return (today + dt.timedelta(days=2)).isoformat()
    if re.search(r"\btomorrow\b", t):
        return (today + dt.timedelta(days=1)).isoformat()
    if re.search(r"\btoday\b", t):
        return today.isoformat()
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t)
    if m:
        try:
            return dt.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        except ValueError:
            return None
    m = re.search(r"\bin (\d{1,2}) days?\b", t)
    if m:
        return (today + dt.timedelta(days=int(m[1]))).isoformat()
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", t) or \
        re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b", t)
    if m:
        a, b = m.groups()
        day, mon = (int(a), MONTHS[b]) if a.isdigit() else (int(b), MONTHS[a])
        try:
            d = dt.date(today.year, mon, day)
            if d < today:
                d = dt.date(today.year + 1, mon, day)
            return d.isoformat()
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)  # dd/mm (India)
    if m:
        try:
            y = int(m[3]) if m[3] else today.year
            y += 2000 if y < 100 else 0
            d = dt.date(y, int(m[2]), int(m[1]))
            if d < today and not m[3]:
                d = d.replace(year=today.year + 1)
            return d.isoformat()
        except ValueError:
            return None
    m = re.search(r"\b(?:(next|this|coming)\s+)?(monday|mon|tuesday|tues|tue|wednesday|wed|thursday|thurs|thur|thu|friday|fri|saturday|sat|sunday|sun)\b", t)
    if m:
        wd = DAYS[m[2]]
        delta = (wd - today.weekday()) % 7
        if delta == 0:
            delta = 7
        if m[1] == "next" and delta <= 7 - today.weekday() - 1 and today.weekday() < wd:
            delta += 7 if today.weekday() != 0 or wd == 0 else 0
        return (today + dt.timedelta(days=delta)).isoformat()
    return None


def parse_time(text: str) -> tuple[str | None, str | None]:
    """Returns (HH:MM or None, part-of-day preference or None)."""
    t = text.lower()
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", t)
    if m:
        h, mi = int(m[1]), int(m[2] or 0)
        pm = m[3].startswith("p")
        h = (h % 12) + (12 if pm else 0)
        return f"{h:02d}:{mi:02d}", None
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
    if m:
        return f"{int(m[1]):02d}:{m[2]}", None
    if re.search(r"\bnoon\b", t):
        return "12:00", None
    m = re.search(r"\bat (\d{1,2})\b(?!\s*(?:th|st|nd|rd|/|-))", t)
    if m and 1 <= int(m[1]) <= 12:
        h = int(m[1])
        return f"{(h + 12 if h < 7 else h):02d}:00", None  # clinic days: 1-6 means afternoon
    for word in ("morning", "afternoon", "evening"):
        if word in t:
            return None, word
    return None, None


def match_pref(time_str: str, pref: str) -> bool:
    h = int(time_str[:2]) + int(time_str[3:]) / 60
    return {"morning": h < 13, "afternoon": h >= 14, "evening": h >= 16}[pref]


def nearest_slot(time_str: str, free: list[str]) -> str | None:
    if not free:
        return None
    h = lambda s: int(s[:2]) * 60 + int(s[3:])
    return min(free, key=lambda s: abs(h(s) - h(time_str)))


def parse_doctor(text: str, doctors: list[dict]) -> int | None:
    t = text.lower()
    for d in doctors:
        parts = [p for p in re.sub(r"^dr\.?\s+", "", d["name"].lower()).split() if len(p) > 2]
        last = parts[-1]
        if re.search(rf"\b{re.escape(last)}\b", t) or (len(parts) > 1 and re.search(rf"\b{re.escape(parts[0])}\b", t)):
            return d["id"]
    return None


def parse_ref(text: str) -> int | None:
    m = re.search(r"(?:#|appointment\s*(?:number|no\.?|id)?\s*|number\s*|booking\s*)(\d+)\b", text.lower())
    return int(m[1]) if m else None


def parse_reason(text: str) -> str:
    m = re.search(r"\b(?:for|because of|because|about|regarding|as)\s+(?:a\s+|an\s+|my\s+)?(.+)$", text, re.I)
    if not m:
        return ""
    reason = re.split(r"\b(?:on|at|with|tomorrow|today|next|this coming)\b", m[1], flags=re.I)[0].strip(" ,.")
    if re.fullmatch(r"(an?\s+)?(appointment|visit|slot|booking|doctor|consultation)", reason, re.I) or len(reason) < 4:
        return ""
    return reason


def rule_extract(text: str, doctors: list[dict], today: dt.date) -> dict:
    time_s, pref = parse_time(text)
    out = {"doctor_id": parse_doctor(text, doctors), "date": parse_date(text, today), "time": time_s, "time_pref": pref,
           "appointment_id": parse_ref(text), "reason": parse_reason(text)}
    if not out["doctor_id"]:
        route = triage.route_to_specialty(text)
        if route["confident"] or (route["specialty"] != triage.DEFAULT_SPECIALTY):
            out["specialty"] = route["specialty"]
    return {k: v for k, v in out.items() if v not in (None, "")}


def extract(text: str, doctors: list[dict], today: dt.date) -> dict:
    """LLM-assisted when a key is configured (merged under the rules, which win on conflicts)."""
    slots = rule_extract(text, doctors, today)
    if llm.available():
        out = llm.generate(
            f"Today is {today.isoformat()} ({today.strftime('%A')}). Doctors: " + "; ".join(f"{d['id']}={d['name']} ({d['specialty']})" for d in doctors)
            + f'\nPatient message: "{text}"\nReturn ONLY JSON with any of these keys that the message states: doctor_id (int), date (YYYY-MM-DD), '
              'time (HH:MM 24h), reason (short phrase), appointment_id (int). Omit unknown keys.',
            system="You extract appointment details. Output JSON only.", max_tokens=120)
        try:
            data = json.loads(re.search(r"\{.*\}", out or "", re.S).group(0))
            for k in ("doctor_id", "date", "time", "reason", "appointment_id"):
                if k in data and k not in slots:
                    slots[k] = data[k]
        except Exception:
            pass
    return slots
