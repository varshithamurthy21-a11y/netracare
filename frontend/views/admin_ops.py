"""Admin pages for iterations 5-6: evals, traces, MCP servers and Agent Skills."""
import pandas as pd
import streamlit as st

from .. import ui
from ..common import client, do, md, safe_get


def evals(user: dict) -> None:
    c = client()
    md(ui.hero("Evals & Traces", "Is the assistant still safe and correct? Run the test sets, then inspect real conversations.", "Quality", compact=True))
    if st.button("▶ Run all evals", type="primary"):
        with st.spinner("Running test sets on a throwaway database…"):
            rep = do(c.post, "/admin/evals/run", rerun=False)
        if rep:
            st.rerun()
    rep = safe_get(c.get, "/admin/evals/latest", default={})
    if rep:
        a, b, d, e = st.columns(4)
        a.metric("Overall", f"{rep['pass_rate']*100:.0f}%"); b.metric("Cases", f"{rep['passed']}/{rep['total']}")
        d.metric("Judge", rep["judge"]); e.metric("Seconds", rep["seconds"])
        for s in rep["suites"]:
            with st.expander(f"{s['suite'].upper()} — {s['pass_rate']*100:.0f}% of {s['n']}", expanded=bool(s["failures"])):
                st.json(s["metrics"])
                if s["failures"]:
                    st.dataframe(pd.DataFrame(s["failures"]).astype(str), hide_index=True)
                else:
                    st.success("All cases passed.")
    else:
        md(ui.empty("🧪", "No eval run yet — click “Run all evals”."))

    md(ui.section("Recent traces", "🔍"))
    data = safe_get(c.get, "/admin/traces", default={"summary": {}, "traces": []})
    sm = data["summary"]
    if sm:
        a, b, d = st.columns(3)
        a.metric("Traces", sm["traces"]); b.metric("Avg latency (ms)", sm["avg_latency_ms"]); d.metric("Est. cost (USD)", sm["total_cost_usd"])
    if data["traces"]:
        df = pd.DataFrame(data["traces"])
        st.dataframe(df[["created_at", "name", "intent", "input", "latency_ms", "llm_calls", "cost_usd"]], hide_index=True)
        pick = st.selectbox("Inspect a trace", [t["trace_id"] for t in data["traces"]])
        t = next(x for x in data["traces"] if x["trace_id"] == pick)
        st.code(t["spans"] or "[]", language="json")
        st.caption("Token and cost numbers are estimates (about 4 characters per token).")


def mcp_skills(user: dict) -> None:
    c = client()
    md(ui.hero("MCP & Skills", "Tools the assistant can call through MCP servers, and the Agent Skills that guide it.", "Integrations", compact=True))
    md(ui.section("MCP servers", "🔌"))
    for s in safe_get(c.get, "/admin/mcp/tools", default=[]):
        with st.expander(f"{'🟢' if s['ok'] else '🔴'} {s['server']}", expanded=True):
            if not s["ok"]:
                st.error(s.get("error", "unreachable"))
                continue
            st.caption(f"{s['info'].get('name')} v{s['info'].get('version')}")
            st.dataframe(pd.DataFrame(s["tools"]), hide_index=True)
    md(ui.section("Agent Skills", "🧠"))
    sk = safe_get(c.get, "/admin/skills", default=[])
    st.dataframe(pd.DataFrame(sk), hide_index=True) if sk else md(ui.empty("🧠", "No skills found."))
