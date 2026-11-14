"""Reusable booking flow (patients book for themselves, front desk books for a patient)."""
import datetime as dt

import streamlit as st

from . import ui
from .common import client, do, md, safe_get


def _next_open(d: dt.date) -> dt.date:
    while d.weekday() == 6:
        d += dt.timedelta(days=1)
    return d


def booking_flow(key: str, patient_id: int | None = None, after_page: str | None = None) -> None:
    base = key
    key = f"{base}{st.session_state.get(base + '_n', 0)}"  # fresh widgets after each booking
    c = client()
    doctors = safe_get(c.get, "/doctors", default=[])
    if not doctors:
        md(ui.empty("🩺", "No doctors are available right now."))
        return
    sel_key, slot_key = f"{key}_doc", f"{key}_slot"

    with st.expander("🧭 Not sure which doctor to see? Describe what's bothering you"):
        text = st.text_area("In your own words", key=f"{key}_helper", height=90,
                            placeholder="e.g. my child squints when watching TV / I need new glasses / floaters in my eye")
        if st.button("Suggest a specialist", key=f"{key}_route") and text.strip():
            res = safe_get(c.post, "/triage/route", {"text": text})
            if res:
                if res.get("doctor_id"):
                    st.session_state[sel_key] = res["doctor_id"]
                st.session_state[f"{key}_why"] = res
        res = st.session_state.get(f"{key}_why")
        if res:
            md(ui.alert(f"Suggested: {res['specialty']}", res["why"] + " " + res["disclaimer"], "info"))
        flags = safe_get(c.post, "/triage/red-flags", {"text": text}) if text.strip() else None
        if flags and flags["red_flag"]:
            md(ui.alert("Please read", flags["patient_message"], "danger"))

    md(ui.section("1 · Choose your doctor", "🩺"))
    cols = st.columns(3)
    for i, d in enumerate(doctors):
        with cols[i % 3]:
            md(ui.doctor_card(d, selected=st.session_state.get(sel_key) == d["id"]))
            chosen = st.session_state.get(sel_key) == d["id"]
            if st.button("✓ Selected" if chosen else "Choose", key=f"{key}_pick{d['id']}",
                         type="primary" if chosen else "secondary"):
                st.session_state[sel_key] = d["id"]
                st.session_state.pop(slot_key, None)
                st.rerun()
    doc_id = st.session_state.get(sel_key)
    if not doc_id:
        md(ui.alert("Next step", "Pick a doctor above to see their available times.", "info"))
        return
    doctor = next(d for d in doctors if d["id"] == doc_id)

    md(ui.section("2 · Pick a date & time", "🗓️"))
    today = dt.date.today()
    date = st.date_input("Date", value=_next_open(today), min_value=today,
                         max_value=today + dt.timedelta(days=14), key=f"{key}_date")
    slots = safe_get(c.get, f"/doctors/{doc_id}/slots", date=date.isoformat(), default=[])
    if not slots:
        md(ui.alert("Clinic closed", "NetraCare is closed on Sundays. Please choose another day.", "info"))
        return
    free = [s for s in slots if s["available"]]
    st.caption(f"{len(free)} of {len(slots)} slots free with {doctor['name']} on {date.strftime('%A, %d %b')}")
    cols = st.columns(6)
    for i, s in enumerate(slots):
        with cols[i % 6]:
            picked = st.session_state.get(slot_key) == (date.isoformat(), s["time"])
            if st.button(ui.pretty_time(s["time"]), key=f"{key}_s{date}{s['time']}", disabled=not s["available"],
                         type="primary" if picked else "secondary"):
                st.session_state[slot_key] = (date.isoformat(), s["time"])
                st.rerun()
    picked = st.session_state.get(slot_key)
    if not picked or picked[0] != date.isoformat():
        return

    md(ui.section("3 · Tell us why you're coming", "📝"))
    reason = st.text_area("Reason for visit (optional)", key=f"{key}_reason", height=90,
                          placeholder="A few words help us prepare. Please don't include anything you want urgent medical advice on — call us instead.")
    if reason.strip():
        flags = safe_get(c.post, "/triage/red-flags", {"text": reason})
        if flags and flags["red_flag"]:
            md(ui.alert("We'd like to review this quickly", flags["patient_message"], "danger"))
    md(ui.alert("Your booking", f"{doctor['name']} · {date.strftime('%A, %d %b %Y')} at {ui.pretty_time(picked[1])} · {doctor['room']}", "ok"))
    if st.button("Confirm appointment", type="primary", key=f"{key}_confirm"):
        body = {"doctor_id": doc_id, "date": picked[0], "time": picked[1], "reason": reason}
        if patient_id:
            body["patient_id"] = patient_id
        res = do(c.post, "/appointments", body, rerun=False)
        if res and res is not True:
            st.session_state[base + "_n"] = st.session_state.get(base + "_n", 0) + 1
            st.session_state["flash"] = "Appointment booked! 🎉"
            if res.get("red_flag"):
                st.session_state["flag_msg"] = res["red_flag_info"]["patient_message"]
            if after_page:
                st.session_state["page"] = after_page
            st.rerun()
