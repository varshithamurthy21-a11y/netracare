"""HTML building blocks for the NetraCare theme (pure Python, no Streamlit import)."""
import datetime as dt
import html
import re
from pathlib import Path

CSS = (Path(__file__).parent / "theme.css").read_text()
STATUS_LABEL = {"booked": "Booked", "checked_in": "Checked in", "completed": "Completed",
                "cancelled": "Cancelled", "no_show": "No-show"}


def h(markup: str) -> str:
    """Strip indentation/blank lines so Markdown never turns HTML into a code block."""
    return "\n".join(line.strip() for line in markup.strip().splitlines() if line.strip())


def e(value) -> str:
    return html.escape(str(value or ""))


def eye_svg(size: int = 40, ring: str = "#fff") -> str:
    return h(f"""<svg class="nc-eye" width="{size}" height="{size}" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
    <defs><radialGradient id="iris{size}" cx="50%" cy="45%" r="60%"><stop offset="0" stop-color="#7CF3E4"/><stop offset=".55" stop-color="#6C5CE7"/><stop offset="1" stop-color="#2B2572"/></radialGradient></defs>
    <g class="lid"><path d="M4 32C13 17 24 10 32 10s19 7 28 22c-9 15-20 22-28 22S13 47 4 32Z" fill="#fff" stroke="{ring}" stroke-width="2.5"/>
    <circle cx="32" cy="32" r="14" fill="url(#iris{size})"/><g class="pupil"><circle cx="32" cy="32" r="6.2" fill="#10102E"/></g>
    <circle cx="27.5" cy="27" r="3" fill="#fff" opacity=".9"/></g></svg>""")


def logo() -> str:
    return h(f"""<div class="nc-logo">{eye_svg(44)}<div class="word">NetraCare<small>Eye clinic</small></div></div>""")


def hero(title: str, subtitle: str, kicker: str = "", compact: bool = False, eye: bool = False) -> str:
    return h(f"""<div class="nc-hero{' compact' if compact else ''}">
      {f'<span class="nc-kicker">{e(kicker)}</span>' if kicker else ''}
      <h1>{title}</h1><p>{e(subtitle)}</p>
      {f'<div class="nc-eye-big">{eye_svg(150)}</div>' if eye else ''}</div>""")


def section(text: str, icon: str = "") -> str:
    return f'<div class="nc-section">{icon} {e(text)}</div>'


def pill(status: str, label: str | None = None) -> str:
    return f'<span class="nc-pill {e(status)}">{e(label or STATUS_LABEL.get(status, status))}</span>'


def initials(name: str) -> str:
    parts = [p for p in re.sub(r"^(Dr\.?)\s+", "", name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def fmt_date(date_str: str) -> tuple[str, str, str]:
    d = dt.date.fromisoformat(date_str)
    return d.strftime("%b"), str(d.day), d.strftime("%A")


def pretty_time(t: str) -> str:
    return dt.datetime.strptime(t, "%H:%M").strftime("%I:%M %p").lstrip("0")


def user_chip(user: dict) -> str:
    return h(f"""<div class="nc-user"><div class="nc-avatar">{e(initials(user['name']))}</div>
      <div><b>{e(user['name'])}</b><span>{e(user['role'])}</span></div></div>""")


def stat(value, label: str, glow: str = "rgba(108,92,231,.14)") -> str:
    return f'<div class="nc-stat" style="--glow:{glow}"><div class="n">{e(value)}</div><div class="l">{e(label)}</div></div>'


def fact_banner(fact: dict) -> str:
    tag = "AI-written" if fact.get("source") == "ai" else "Did you know?"
    return h(f"""<div class="nc-fact"><div class="ico">👁️</div><div><div class="k">Eye fact of the day · {e(tag)}</div>
      <div class="t">{e(fact['fact'])}</div></div></div>""")


def alert(title: str, body: str, kind: str = "info") -> str:
    return f'<div class="nc-alert {kind}"><b>{e(title)}</b>{e(body)}</div>'


def empty(icon: str, text: str) -> str:
    return f'<div class="nc-empty"><div class="big">{icon}</div>{e(text)}</div>'


def doctor_card(d: dict, selected: bool = False) -> str:
    chips = "".join(f'<span class="nc-chip">{e(x.strip())}</span>' for x in d.get("languages", "").split(","))
    ring = "outline:3px solid var(--violet);outline-offset:3px;" if selected else ""
    return h(f"""<div class="nc-card" style="{ring}"><div class="nc-doc">
      <div class="ring" style="background:{e(d['accent'])}">{e(initials(d['name']))}</div>
      <div class="meta"><b>{e(d['name'])}</b><span>{e(d['specialty'])} · {e(d['years'])} yrs · {e(d['room'])}</span></div></div>
      <div class="nc-muted" style="margin-top:.7rem">{e(d['focus'])}</div>{chips}</div>""")


def appointment_card(a: dict, show_patient: bool = False, show_notes: bool = False) -> str:
    m, d, wd = fmt_date(a["date"])
    flag = '<span class="nc-pill flag">⚠ Needs review</span>' if a.get("red_flag") else ""
    who = (f"<b>{e(a['patient_name'])}</b> with {e(a['doctor_name'])}" if show_patient
           else f"<b>{e(a['doctor_name'])}</b> · {e(a['specialty'])}")
    reason = f'<div class="reason">💬 {e(a["reason"])}</div>' if a.get("reason") else ""
    flag_detail = (f'<div class="nc-alert danger" style="margin:.5rem 0 0"><b>Red-flag keywords</b>{e(a["red_flag_reason"])}</div>'
                   if a.get("red_flag") and show_patient else "")
    notes = (f'<div class="summary"><b>Visit notes (staff only)</b>\n{e(a["visit_notes"])}</div>'
             if show_notes and a.get("visit_notes") else "")
    summary = ""
    if a.get("summary") and (show_notes or a.get("summary_status") == "published"):
        badge = pill(a["summary_status"], "Draft — not yet shared" if a["summary_status"] == "draft" else "Shared with patient")
        summary = f'<div class="summary"><b>Visit summary</b> {badge}\n{e(a["summary"])}</div>'
    return h(f"""<div class="nc-card"><div class="nc-appt">
      <div class="nc-date"><div class="m">{m}</div><div class="d">{d}</div><div class="t">{e(pretty_time(a['time']))}</div></div>
      <div class="body"><div class="top"><div>{who}<div class="nc-muted">{wd} · {e(a['room'])} · #{a['id']}</div></div>
      <div>{flag} {pill(a['status'])}</div></div>{reason}{flag_detail}{notes}{summary}</div></div></div>""")


def queue_ticket(q: dict) -> str:
    return h(f"""<div class="nc-ticket"><div><small>Your place in line</small><div class="pos">#{q['position']}</div></div>
      <div><small>Estimated wait</small><b style="font-size:1.4rem">~{q['wait_minutes']} min</b>
      <div style="opacity:.85;font-size:.9rem">{e(q['doctor_name'])} · {e(q['room'])}</div></div></div>""")


def queue_column(d: dict) -> str:
    items = "".join(
        f'<div class="nc-qitem"><span><span class="n">{w["position"]}</span>{e(w["patient_name"])}</span>'
        f'<span class="nc-muted">~{w["wait_minutes"]} min {"⚠" if w["red_flag"] else ""}</span></div>' for w in d["waiting"]
    ) or '<div class="nc-muted">No one waiting 🎉</div>'
    return h(f"""<div class="nc-qcol"><div class="nc-qhead"><span class="dot" style="background:{e(d['accent'])}"></span>
      <div><b>{e(d['doctor_name'])}</b><div class="nc-muted">{e(d['specialty'])} · {e(d['room'])}</div></div></div>
      {items}<div class="nc-muted" style="margin-top:.5rem">Seen today: <b>{d['seen_today']}</b> · Still expected: <b>{d['still_expected']}</b></div></div>""")


def footer() -> str:
    return ('<div class="nc-note">NetraCare is a fictional clinic created for a learning project. The assistant helps with '
            'scheduling only — it never gives medical advice, diagnosis or treatment guidance. '
            'In an emergency, contact local emergency services.</div>')
