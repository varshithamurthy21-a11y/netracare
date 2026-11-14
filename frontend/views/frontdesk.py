import datetime as dt

import streamlit as st

from .. import ui
from ..booking import booking_flow
from ..common import client, do, md, safe_get

PAGES = ["📡 Live queue", "📋 Appointments", "➕ Book for patient", "🚩 Alerts"]


def render(page: str, user: dict) -> None:
    {"📡 Live queue": live, "📋 Appointments": appointments, "➕ Book for patient": book_for, "🚩 Alerts": alerts}[page](user)


def live(user: dict) -> None:
    c = client()
    md(ui.hero("Live queue", "Who is waiting, for whom, and for how long — updated whenever you refresh.", "Front desk", compact=True, eye=True))
    if st.button("🔄 Refresh", key="refresh"):
        st.rerun()
    qs = safe_get(c.get, "/queue", default=[])
    for start in range(0, len(qs), 3):
        cols = st.columns(3)
        for col, d in zip(cols, qs[start:start + 3]):
            with col:
                md(ui.queue_column(d))
    md(ui.section("Today's arrivals", "🛎️"))
    rows = safe_get(c.get, "/appointments", date=dt.date.today().isoformat(), default=[])
    todo = [a for a in rows if a["status"] == "booked"]
    if not todo:
        md(ui.empty("🎉", "No one left to check in."))
    for a in todo:
        md(ui.appointment_card(a, show_patient=True))
        c1, c2, c3, _ = st.columns([1, 1, 1, 3])
        with c1:
            if st.button("Check in", type="primary", key=f"ci{a['id']}"):
                do(c.post, f"/appointments/{a['id']}/check-in", ok=f"{a['patient_name']} checked in")
        with c2:
            if st.button("No-show", key=f"ns{a['id']}"):
                do(c.post, f"/appointments/{a['id']}/no-show", ok="Marked as no-show")
        with c3:
            if st.button("Cancel", key=f"cx{a['id']}"):
                do(c.post, f"/appointments/{a['id']}/cancel", ok="Appointment cancelled")


def appointments(user: dict) -> None:
    c = client()
    md(ui.hero("All appointments", "Filter, check in, cancel or move any booking.", "Front desk", compact=True))
    f1, f2, f3 = st.columns([1, 1, 1])
    with f1:
        use_date = st.checkbox("Filter by date", value=False)
        date = st.date_input("Date", dt.date.today(), disabled=not use_date)
    with f2:
        status = st.selectbox("Status", ["any", "booked", "checked_in", "completed", "cancelled", "no_show"])
    with f3:
        search = st.text_input("Search patient or doctor")
    params = {}
    if use_date: params["date"] = date.isoformat()
    if status != "any": params["status"] = status
    rows = safe_get(c.get, "/appointments", default=[], **params)
    if search:
        rows = [a for a in rows if search.lower() in (a["patient_name"] + a["doctor_name"]).lower()]
    st.caption(f"{len(rows)} appointment(s)")
    if not rows:
        md(ui.empty("🔍", "No appointments match these filters."))
    for a in rows[:60]:
        md(ui.appointment_card(a, show_patient=True))
        if a["status"] in ("booked", "checked_in"):
            c1, c2, _ = st.columns([1, 1, 4])
            with c1:
                if a["status"] == "booked" and a["date"] == dt.date.today().isoformat():
                    if st.button("Check in", type="primary", key=f"aci{a['id']}"):
                        do(c.post, f"/appointments/{a['id']}/check-in", ok="Checked in")
            with c2:
                if st.button("Cancel", key=f"acx{a['id']}"):
                    do(c.post, f"/appointments/{a['id']}/cancel", ok="Appointment cancelled")


def book_for(user: dict) -> None:
    c = client()
    md(ui.hero("Book for a patient", "Find an existing patient or register a walk-in, then book them in.", "Front desk", compact=True))
    q = st.text_input("Search patients by name, email or phone", key="pq")
    pts = safe_get(c.get, "/patients", q=q, default=[])
    options = {f"{p['name']} · {p['phone'] or p['email']}": p["id"] for p in pts}
    label = st.selectbox("Patient", list(options) or ["— no match —"])
    with st.expander("New walk-in patient"):
        with st.form("walkin"):
            name = st.text_input("Full name")
            phone = st.text_input("Phone")
            email = st.text_input("Email (optional)")
            if st.form_submit_button("Register walk-in", type="primary"):
                do(c.post, "/patients", {"name": name, "phone": phone, "email": email}, ok="Walk-in patient registered — search for them above")
    if label in options:
        md(ui.alert("Booking for", label, "info"))
        booking_flow("fdbook", patient_id=options[label], after_page="📋 Appointments")


def alerts(user: dict) -> None:
    c = client()
    md(ui.hero("Red-flag alerts", "Requests whose wording may need a quick call. A person decides — the system only highlights.", "Safety net", compact=True))
    rows = [a for a in safe_get(c.get, "/appointments", scope="upcoming", default=[]) if a["red_flag"]]
    if not rows:
        md(ui.empty("💚", "No open alerts."))
    for a in rows:
        md(ui.appointment_card(a, show_patient=True))
        md(ui.alert("Suggested action", f"Call {a['patient_name']} on {a['patient_phone'] or 'file'} to understand urgency and offer the earliest suitable slot.", "danger"))
        if st.button("Mark reviewed", type="primary", key=f"mr{a['id']}"):
            do(c.post, f"/appointments/{a['id']}/review-flag", ok="Alert reviewed and logged")
