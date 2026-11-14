import streamlit as st

from .. import ui
from ..api import ApiError, Client
from ..common import md

DEMOS = [("🧑‍⚕️ Patient", "patient@netracare.demo", "Patient@123"),
         ("🩺 Doctor", "rohan@netracare.demo", "Doctor@123"),
         ("🛎️ Front desk", "desk@netracare.demo", "Desk@123"),
         ("🛡️ Admin", "admin@netracare.demo", "Admin@123")]


def _login(email: str, password: str) -> None:
    try:
        res = Client().post("/auth/login", {"email": email, "password": password})
    except ApiError as err:
        st.error(str(err), icon="⚠️")
        return
    st.session_state.update(token=res["token"], user=res["user"], page=None)
    st.rerun()


def landing() -> None:
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        md(ui.h(f"""<div class="nc-hero" style="min-height:560px">
          <span class="nc-kicker">NetraCare · AI front desk</span>
          <h1>See the right doctor,<br>the first time.</h1>
          <p>Book, reschedule and track your visit with a front desk that never gives medical advice
          and always keeps a human in control.</p>
          <div style="position:relative;z-index:1;margin-top:1.6rem;display:grid;gap:.7rem;max-width:460px">
            <div class="nc-user" style="margin:0"><div class="nc-avatar">5</div><div><b>Five specialists</b><span style="text-transform:none">Cataract · Retina · Glaucoma · Cornea · Paediatric</span></div></div>
            <div class="nc-user" style="margin:0"><div class="nc-avatar">⏱</div><div><b>Live queue &amp; wait times</b><span style="text-transform:none">Know your place before you arrive</span></div></div>
            <div class="nc-user" style="margin:0"><div class="nc-avatar">🛡</div><div><b>Staff stay in control</b><span style="text-transform:none">Red flags reviewed by people, summaries approved by doctors</span></div></div>
          </div><div class="nc-eye-big" style="top:12%;right:1.6rem;transform:none">{ui.eye_svg(120)}</div></div>"""))
    with right:
        md('<div style="height:.6rem"></div>')
        md("<h2 style='margin:0'>Welcome back 👋</h2><div class='nc-muted' style='margin-bottom:.8rem'>Sign in or create a patient account.</div>")
        tab_in, tab_up = st.tabs(["Sign in", "Create account"])
        with tab_in:
            with st.form("login"):
                email = st.text_input("Email", placeholder="you@example.com")
                pw = st.text_input("Password", type="password")
                go = st.form_submit_button("Sign in", type="primary")
            if go:
                _login(email, pw)
            md("<div class='nc-demo' style='margin:.8rem 0 .3rem'><b>Try a demo account</b> — one click, no typing:</div>")
            cols = st.columns(2)
            for i, (label, em, pwd) in enumerate(DEMOS):
                with cols[i % 2]:
                    if st.button(label, key=f"demo{i}"):
                        _login(em, pwd)
        with tab_up:
            with st.form("register"):
                name = st.text_input("Full name")
                email = st.text_input("Email", key="reg_email")
                phone = st.text_input("Phone (optional)")
                pw = st.text_input("Choose a password (6+ characters)", type="password", key="reg_pw")
                go = st.form_submit_button("Create my account", type="primary")
            if go:
                try:
                    res = Client().post("/auth/register", {"name": name, "email": email, "password": pw, "phone": phone})
                    st.session_state.update(token=res["token"], user=res["user"], page=None)
                    st.rerun()
                except ApiError as err:
                    st.error(str(err), icon="⚠️")
    md(ui.footer())
