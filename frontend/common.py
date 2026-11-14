import streamlit as st

from . import ui
from .api import ApiError, Client


def client() -> Client:
    return Client(st.session_state.get("token"))


def md(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def do(fn, *args, ok: str | None = None, rerun: bool = True, **kw):
    """Run an API call; show errors nicely; toast + rerun on success."""
    try:
        result = fn(*args, **kw)
    except ApiError as err:
        st.error(str(err), icon="⚠️")
        return None
    if ok:
        st.session_state["flash"] = ok
    if rerun:
        st.rerun()
    return result if result is not None else True


def safe_get(fn, *args, default=None, **kw):
    try:
        return fn(*args, **kw)
    except ApiError as err:
        st.error(str(err), icon="⚠️")
        return default


def goto(page: str) -> None:
    st.session_state["page"] = page
    st.rerun()
