import datetime as dt

import streamlit as st

from .. import ui
from ..booking import booking_flow
from ..common import client, do, goto, md, safe_get

PAGES = ["🏠 Home", "📅 Book a visit", "🗂️ My appointments", "👤 My profile"]


def render(page: str, user: dict) -> None:
    {"🏠 Home": home, "📅 Book a visit": book, "🗂️ My appointments": mine, "👤 My profile": profile}[page](user)


def home(user: dict) -> None:
    c = client()
    first = user["name"].split()[0]
    md(ui.hero(f"Hello, {ui.e(first)} 👋", "Here's everything about your eye care in one place.", "Patient home", compact=True, eye=True))
    md('<div style="height:.9rem"></div>')
    fact = safe_get(c.get, "/fact")
    if fact:
        md(ui.fact_banner(fact))

    upcoming = safe_get(c.get, "/appointments", scope="upcoming", default=[])
    past = safe_get(c.get, "/appointments", scope="past", default=[])
    done = [a for a in past if a["status"] == "completed"]

    queue = safe_get(c.get, "/queue/me", default={})
    if queue:
        md(ui.section("You're checked in", "🎟️"))
        md(ui.queue_ticket(queue))

    cols = st.columns(3)
    with cols[0]: md(ui.stat(len(upcoming), "Upcoming visits"))
    with cols[1]: md(ui.stat(len(done), "Visits completed", "rgba(0,184,169,.16)"))
    with cols[2]: md(ui.stat(len([a for a in done if a["summary"]]), "Summaries ready", "rgba(255,107,129,.14)"))

    md(ui.section("Next appointment", "🗓️"))
    if upcoming:
        nxt = upcoming[0]
        when = dt.datetime.fromisoformat(f"{nxt['date']}T{nxt['time']}")
        if 0 < (when - dt.datetime.now()).total_seconds() < 86400 * 1.5 and nxt["date"] <= (dt.date.today() + dt.timedelta(days=1)).isoformat():
            md(ui.alert("Friendly reminder", f"Your visit with {nxt['doctor_name']} is {'today' if nxt['date'] == dt.date.today().isoformat() else 'tomorrow'} "
                        f"at {ui.pretty_time(nxt['time'])}. Please arrive 10 minutes early and bring your previous prescriptions.", "info"))
        md(ui.appointment_card(nxt))
        a, b, _ = st.columns([1, 1, 3])
        with a:
            if st.button("Manage appointments", type="primary", key="home_manage"):
                goto("🗂️ My appointments")
        with b:
            if st.button("Book another", key="home_book"):
                goto("📅 Book a visit")
    else:
        md(ui.empty("🗓️", "No upcoming visits. Let's find you a time that suits you."))
        if st.button("Book a visit", type="primary", key="home_book2"):
            goto("📅 Book a visit")

    latest = next((a for a in done if a["summary"]), None)
    if latest:
        md(ui.section("Latest visit summary", "📝"))
        md(ui.appointment_card(latest))


def book(user: dict) -> None:
    md(ui.hero("Book a visit", "Pick a doctor, choose a time that works, and you're done in under a minute.", "Appointments", compact=True))
    md('<div style="height:.6rem"></div>')
    booking_flow("pbook", after_page="🗂️ My appointments")


def _reschedule_box(a: dict) -> None:
    c = client()
    today = dt.date.today()
    with st.expander("Reschedule"):
        date = st.date_input("New date", value=max(today, dt.date.fromisoformat(a["date"])), min_value=today,
                             max_value=today + dt.timedelta(days=14), key=f"rd{a['id']}")
        slots = safe_get(c.get, f"/doctors/{a['doctor_id']}/slots", date=date.isoformat(), default=[])
        free = [s["time"] for s in slots if s["available"]]
        if not free:
            st.caption("No free times that day.")
            return
        t = st.selectbox("New time", free, format_func=ui.pretty_time, key=f"rt{a['id']}")
        if st.button("Move my appointment", type="primary", key=f"rb{a['id']}"):
            do(c.post, f"/appointments/{a['id']}/reschedule", {"date": date.isoformat(), "time": t}, ok="Appointment rescheduled ✅")


def mine(user: dict) -> None:
    c = client()
    md(ui.hero("My appointments", "Upcoming visits, past visits and summaries your doctor has shared.", "Your care", compact=True))
    if st.session_state.get("flag_msg"):
        md(ui.alert("Flagged for our team", st.session_state.pop("flag_msg"), "danger"))
    tab_up, tab_past = st.tabs(["Upcoming", "History & summaries"])
    with tab_up:
        rows = safe_get(c.get, "/appointments", scope="upcoming", default=[])
        if not rows:
            md(ui.empty("📭", "Nothing booked yet."))
        for a in rows:
            md(ui.appointment_card(a))
            if a["status"] == "booked":
                col1, _ = st.columns([1, 4])
                with col1:
                    if st.button("Cancel appointment", key=f"c{a['id']}"):
                        do(c.post, f"/appointments/{a['id']}/cancel", ok="Appointment cancelled. Your slot was released.")
                _reschedule_box(a)
    with tab_past:
        rows = safe_get(c.get, "/appointments", scope="past", default=[])
        if not rows:
            md(ui.empty("🗃️", "Your visit history will appear here."))
        for a in rows:
            md(ui.appointment_card(a))


def profile(user: dict) -> None:
    c = client()
    md(ui.hero("My profile", "Keep your details up to date so the front desk can reach you.", "Account", compact=True))
    md('<div style="height:.6rem"></div>')
    me = safe_get(c.get, "/auth/me", default=user)
    with st.form("profile"):
        name = st.text_input("Full name", me["name"])
        st.text_input("Email (can't be changed)", me["email"], disabled=True)
        phone = st.text_input("Phone", me.get("phone", ""))
        dob = st.text_input("Date of birth (YYYY-MM-DD)", me.get("dob", ""))
        notes = st.text_area("Preferences for the front desk (e.g. language, wheelchair access)", me.get("notes", ""))
        if st.form_submit_button("Save changes", type="primary"):
            res = do(c.put, "/auth/me", {"name": name, "phone": phone, "dob": dob, "notes": notes}, rerun=False)
            if res and res is not True:
                st.session_state["user"] = {**st.session_state["user"], **res}
                st.session_state["flash"] = "Profile saved"
                st.rerun()
