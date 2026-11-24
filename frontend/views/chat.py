"""Patient chat: grounded answers with citations, guardrails, and approval-gated booking."""
import streamlit as st

from .. import ui
from ..api import ApiError
from ..common import client, md

GREETING = {"role": "assistant", "content": "Hi! I'm NetraCare's front-desk assistant. Ask me about hours, fees, doctors and policies, "
            "or ask me to book, cancel or reschedule. I can't give medical advice — for that, you'll see a doctor.",
            "quick": ["Book an appointment", "What are your opening hours?", "Which doctor should I see?", "Show my appointments"]}


def _send(text: str) -> None:
    st.session_state["chat"].append({"role": "user", "content": text})
    try:
        r = client().post("/assistant/message", {"message": text})
    except ApiError as err:
        st.session_state["chat"].append({"role": "assistant", "content": f"⚠️ {err}"})
        return
    _add(r)


def _add(r: dict) -> None:
    st.session_state["chat"].append({"role": "assistant", "content": r["reply"], "cites": r.get("citations") or [],
                                     "quick": r.get("quick_replies") or [], "flagged": r.get("flagged"), "intent": r.get("intent"),
                                     "grounded": r.get("grounded")})
    st.session_state["pending"] = r.get("pending")


def _approve(ok: bool) -> None:
    try:
        r = client().post("/assistant/confirm", {"approve": ok})
    except ApiError as err:
        st.session_state["chat"].append({"role": "assistant", "content": f"⚠️ {err}"})
        return
    _add(r)


def render(user: dict) -> None:
    md(ui.hero("Ask NetraCare", "Questions about the clinic, or let me handle a booking — you always approve changes first.", "AI front desk", compact=True))
    st.session_state.setdefault("chat", [GREETING])
    st.session_state.setdefault("pending", None)

    for i, m in enumerate(st.session_state["chat"]):
        with st.chat_message(m["role"], avatar="🧑" if m["role"] == "user" else "👁️"):
            if m.get("flagged"):
                md(ui.alert("Flagged for the care team", "A staff member will review this message.", "danger"))
            st.markdown(m["content"])
            if m.get("cites"):
                with st.expander(f"Sources ({len(m['cites'])})"):
                    for c in m["cites"]:
                        st.markdown(f"**[{c['n']}] {c['title']} — {c['heading']}**  \n{c['snippet']}")
            if m.get("grounded") is False:
                st.caption("Not found in the clinic's information, so I won't guess.")

    clicked = None
    pending = st.session_state.get("pending")
    if pending:
        md(ui.alert("Waiting for your approval", pending["summary"], "info"))
        a, b = st.columns(2)
        if a.button("✅ Yes, go ahead", use_container_width=True, key="yes"):
            _approve(True); st.rerun()
        if b.button("✋ No, don't", use_container_width=True, key="no"):
            _approve(False); st.rerun()
    else:
        quick = st.session_state["chat"][-1].get("quick") or []
        if quick:
            cols = st.columns(len(quick))
            for j, q in enumerate(quick):
                if cols[j].button(q, key=f"q{len(st.session_state['chat'])}_{j}", use_container_width=True):
                    clicked = q

    text = st.chat_input("Ask a question or say what you'd like to book…") or clicked
    if text:
        _send(text)
        st.rerun()
    if st.button("Start over", key="chat_reset"):
        try:
            client().post("/assistant/reset")
        except ApiError:
            pass
        st.session_state["chat"], st.session_state["pending"] = [GREETING], None
        st.rerun()
