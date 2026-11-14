"""NetraCare — Streamlit front end.  Run:  streamlit run frontend/app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from frontend import ui
from frontend.common import md
from frontend.views import admin, auth, doctor, frontdesk, patient

st.set_page_config(page_title="NetraCare · Eye Clinic", page_icon="👁️", layout="wide", initial_sidebar_state="expanded")
st.markdown(f"<style>{ui.CSS}</style>", unsafe_allow_html=True)

ROLES = {"patient": patient, "doctor": doctor, "frontdesk": frontdesk, "admin": admin}


def main() -> None:
    if flash := st.session_state.pop("flash", None):
        st.toast(flash, icon="✅")
    user = st.session_state.get("user")
    if not user or not st.session_state.get("token"):
        auth.landing()
        return

    module = ROLES[user["role"]]
    pages = module.PAGES
    if st.session_state.get("page") not in pages:
        st.session_state["page"] = pages[0]

    with st.sidebar:
        md(ui.logo())
        md(ui.user_chip(user))
        for p in pages:
            if st.button(p, key=f"nav_{p}", type="primary" if p == st.session_state["page"] else "secondary"):
                st.session_state["page"] = p
                st.rerun()
        st.divider()
        if st.button("↩ Sign out", key="logout"):
            for k in list(st.session_state):
                del st.session_state[k]
            st.rerun()
        md('<div class="nc-demo" style="color:#BDB9F7;margin-top:1rem">No medical advice is ever given by this assistant.</div>')

    module.render(st.session_state["page"], user)
    md(ui.footer())


main()
