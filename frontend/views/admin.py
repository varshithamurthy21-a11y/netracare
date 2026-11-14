import pandas as pd
import streamlit as st

from .. import ui
from ..common import client, do, md, safe_get

PAGES = ["📊 Overview", "🩺 Doctors", "👥 People", "🧾 Audit log"]


def render(page: str, user: dict) -> None:
    {"📊 Overview": overview, "🩺 Doctors": doctors, "👥 People": people, "🧾 Audit log": audit}[page](user)


def overview(user: dict) -> None:
    c = client()
    md(ui.hero("Clinic overview", "A live look at bookings, workload and safety flags.", "Admin", compact=True, eye=True))
    s = safe_get(c.get, "/admin/stats")
    if not s:
        return
    bs = s["by_status"]
    cols = st.columns(5)
    tiles = [(s["total"], "Total bookings", "rgba(108,92,231,.14)"), (bs.get("booked", 0), "Upcoming", "rgba(108,92,231,.14)"),
             (bs.get("completed", 0), "Completed", "rgba(18,184,134,.16)"), (s["patients"], "Patients", "rgba(0,184,169,.16)"),
             (s["red_flags_open"], "Open red flags", "rgba(255,107,129,.2)")]
    for col, (v, l, g) in zip(cols, tiles):
        with col: md(ui.stat(v, l, g))
    a, b = st.columns(2)
    with a:
        md(ui.section("Bookings per doctor", "🩺"))
        df = pd.DataFrame(s["by_doctor"]).set_index("doctor")[["appointments"]]
        st.bar_chart(df, color="#6C5CE7")
    with b:
        md(ui.section("Next 7 days", "📈"))
        df = pd.DataFrame(s["next_7_days"]).set_index("date")
        st.area_chart(df, color="#00B8A9")
    md(ui.section("Status mix", "🥧"))
    if bs:
        st.bar_chart(pd.DataFrame({"count": bs}), color="#FF6B81", horizontal=True)


def doctors(user: dict) -> None:
    c = client()
    md(ui.hero("Doctors", "Add specialists or pause a doctor's calendar. Paused doctors disappear from patient booking.", "Admin", compact=True))
    docs = safe_get(c.get, "/admin/doctors", default=[])
    cols = st.columns(3)
    for i, d in enumerate(docs):
        with cols[i % 3]:
            md(ui.doctor_card(d))
            if d["active"]:
                if st.button("Pause bookings", key=f"p{d['id']}"):
                    do(c.post, f"/admin/doctors/{d['id']}/active", {"active": False}, ok=f"{d['name']} paused")
            else:
                md(ui.pill("cancelled", "Paused"))
                if st.button("Resume", type="primary", key=f"r{d['id']}"):
                    do(c.post, f"/admin/doctors/{d['id']}/active", {"active": True}, ok=f"{d['name']} is back")
    with st.expander("➕ Add a doctor"):
        with st.form("adddoc"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Name (e.g. Dr. Asha Verma)")
            email = c2.text_input("Login email")
            specialty = c1.text_input("Specialty")
            pw = c2.text_input("Temporary password", type="password")
            focus = st.text_input("Areas of focus (shown to patients)")
            room = c1.text_input("Room", "Room 106")
            years = c2.number_input("Years of experience", 0, 60, 5)
            langs = st.text_input("Languages", "English")
            accent = st.color_picker("Accent colour", "#6C5CE7")
            if st.form_submit_button("Create doctor", type="primary"):
                do(c.post, "/admin/doctors", {"name": name, "email": email, "password": pw, "specialty": specialty, "focus": focus,
                                              "room": room, "years": int(years), "languages": langs, "accent": accent}, ok="Doctor added")


def people(user: dict) -> None:
    c = client()
    md(ui.hero("People & access", "Every account in the clinic. Deactivate anyone instantly.", "Admin", compact=True))
    users = safe_get(c.get, "/admin/users", default=[])
    role = st.selectbox("Show", ["all", "patient", "doctor", "frontdesk", "admin"])
    shown = [u for u in users if role == "all" or u["role"] == role]
    if shown:
        st.dataframe(pd.DataFrame(shown)[["name", "email", "role", "phone", "active", "created_at"]], hide_index=True)
    st.markdown("**Change access**")
    options = {f"{u['name']} ({u['role']})": u for u in shown if u["id"] != user["id"]}
    if options:
        pick = st.selectbox("Account", list(options))
        u = options[pick]
        if u["active"]:
            if st.button("Deactivate account", key="deact"):
                do(c.post, f"/admin/users/{u['id']}/active", {"active": False}, ok="Account deactivated")
        elif st.button("Reactivate account", type="primary", key="react"):
            do(c.post, f"/admin/users/{u['id']}/active", {"active": True}, ok="Account reactivated")
    with st.expander("➕ Add front desk / admin staff"):
        with st.form("addstaff"):
            r = st.selectbox("Role", ["frontdesk", "admin"])
            n = st.text_input("Name")
            e_ = st.text_input("Email")
            p = st.text_input("Temporary password", type="password")
            if st.form_submit_button("Create account", type="primary"):
                do(c.post, "/admin/staff", {"role": r, "name": n, "email": e_, "password": p}, ok="Staff account created")


def audit(user: dict) -> None:
    c = client()
    md(ui.hero("Audit log", "Every booking, cancellation, approval and access change — who did what, when.", "Accountability", compact=True))
    rows = safe_get(c.get, "/admin/audit", default=[])
    if rows:
        st.dataframe(pd.DataFrame(rows)[["at", "actor_name", "action", "detail"]], hide_index=True)
    else:
        md(ui.empty("🧾", "Nothing logged yet."))
