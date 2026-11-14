import datetime as dt

import streamlit as st

from .. import ui
from ..common import client, do, md, safe_get

PAGES = ["🩺 Today", "🗓️ Upcoming", "📝 Visit summaries"]


def render(page: str, user: dict) -> None:
    {"🩺 Today": today, "🗓️ Upcoming": upcoming, "📝 Visit summaries": summaries}[page](user)


def today(user: dict) -> None:
    c = client()
    d = dt.date.today().isoformat()
    md(ui.hero(f"Good day, {ui.e(user['name'])}", "Your schedule for today, with anything staff have flagged.", "Doctor workspace", compact=True, eye=True))
    rows = safe_get(c.get, "/appointments", date=d, default=[])
    live = [a for a in rows if a["status"] in ("booked", "checked_in")]
    cols = st.columns(4)
    with cols[0]: md(ui.stat(len(rows), "Today's visits"))
    with cols[1]: md(ui.stat(len([a for a in rows if a["status"] == "checked_in"]), "Waiting now", "rgba(0,184,169,.16)"))
    with cols[2]: md(ui.stat(len([a for a in rows if a["status"] == "completed"]), "Seen", "rgba(18,184,134,.16)"))
    with cols[3]: md(ui.stat(len([a for a in rows if a["red_flag"]]), "Flagged", "rgba(255,107,129,.2)"))
    md(ui.section("Schedule", "🕘"))
    if not rows:
        md(ui.empty("☕", "No appointments today."))
    for a in rows:
        md(ui.appointment_card(a, show_patient=True, show_notes=True))
        if a["status"] in ("booked", "checked_in"):
            with st.expander(f"Complete visit — {a['patient_name']}"):
                notes = st.text_area("Visit notes (what you found and what was agreed)", key=f"n{a['id']}", height=110,
                                     placeholder="These notes stay private to staff. A patient-friendly summary is drafted for your approval.")
                if st.button("Mark complete & draft summary", type="primary", key=f"done{a['id']}"):
                    do(c.post, f"/appointments/{a['id']}/complete", {"visit_notes": notes},
                       ok="Visit completed. Draft summary is waiting for your approval.")
        if a["red_flag"]:
            if st.button("I've reviewed this flag", key=f"rf{a['id']}"):
                do(c.post, f"/appointments/{a['id']}/review-flag", ok="Flag cleared")


def upcoming(user: dict) -> None:
    c = client()
    md(ui.hero("Upcoming", "The next days on your calendar.", "Doctor workspace", compact=True))
    rows = [a for a in safe_get(c.get, "/appointments", scope="upcoming", default=[]) if a["date"] > dt.date.today().isoformat()]
    if not rows:
        md(ui.empty("🌤️", "Nothing booked beyond today yet."))
    for a in rows:
        md(ui.appointment_card(a, show_patient=True))


def summaries(user: dict) -> None:
    c = client()
    md(ui.hero("Visit summaries", "AI drafts a plain-language recap from your notes. Nothing reaches the patient until you approve it.", "Human in control", compact=True))
    rows = [a for a in safe_get(c.get, "/appointments", scope="past", default=[]) if a["status"] == "completed"]
    drafts = [a for a in rows if a["summary_status"] == "draft"]
    md(ui.section(f"Awaiting your approval ({len(drafts)})", "✍️"))
    if not drafts:
        md(ui.empty("✅", "All caught up."))
    for a in drafts:
        md(ui.appointment_card(a, show_patient=True, show_notes=True))
        text = st.text_area("Edit the patient summary", a["summary"], key=f"s{a['id']}", height=170)
        c1, c2, c3 = st.columns([1.2, 1, 1])
        with c1:
            if st.button("Approve & share with patient", type="primary", key=f"pub{a['id']}"):
                do(c.put, f"/appointments/{a['id']}/summary", {"summary": text, "publish": True}, ok="Summary shared with the patient ✅")
        with c2:
            if st.button("Save draft", key=f"sv{a['id']}"):
                do(c.put, f"/appointments/{a['id']}/summary", {"summary": text, "publish": False}, ok="Draft saved")
        with c3:
            if st.button("Re-draft with AI", key=f"rg{a['id']}"):
                do(c.post, f"/appointments/{a['id']}/summary/regenerate", ok="New draft generated")
    md(ui.section("Already shared", "📤"))
    for a in [x for x in rows if x["summary_status"] == "published"][:10]:
        md(ui.appointment_card(a, show_patient=True, show_notes=True))
