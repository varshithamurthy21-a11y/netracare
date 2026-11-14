"""NetraCare look and feel: CSS, SVG art and small HTML builders.

Palette: deep navy + teal "aqua" on a soft aurora background, glass-style cards, Poppins/Inter.
Every piece of user-supplied text goes through esc() before it is placed in HTML.
"""
from __future__ import annotations

import html as _html
from datetime import date, datetime, timedelta

import streamlit as st


# --------------------------------------------------------------------------- tiny helpers
def esc(value) -> str:
    """HTML-escape user text. '$' is escaped too so Streamlit never treats it as LaTeX."""
    return _html.escape("" if value is None else str(value)).replace("$", "&#36;")


def H(markup: str) -> str:
    """Collapse indentation + newlines so Markdown can't mistake our HTML for a code block."""
    return "".join(line.strip() for line in markup.strip().splitlines())


DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
STATUS_STYLE = {
    "booked": ("Booked", "#1d4ed8", "#dbeafe"),
    "checked_in": ("Checked in", "#0f766e", "#ccfbf1"),
    "completed": ("Completed", "#475569", "#e2e8f0"),
    "cancelled": ("Cancelled", "#b91c1c", "#fee2e2"),
    "no_show": ("No-show", "#b45309", "#fef3c7"),
}


def d_obj(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def fmt_time(value: str) -> str:
    return datetime.strptime(value, "%H:%M").strftime("%I:%M %p").lstrip("0")


def fmt_date(value: str) -> str:
    d = d_obj(value)
    text = f"{d.strftime('%a')}, {d.day} {d.strftime('%b')}"
    return text if d.year == date.today().year else f"{text} {d.year}"


def day_label(value: str) -> str:
    d = d_obj(value)
    if d == date.today():
        return "Today"
    if d == date.today() + timedelta(days=1):
        return "Tomorrow"
    return fmt_date(value)


def long_date(d: date) -> str:
    return f"{d.strftime('%A')}, {d.day} {d.strftime('%B %Y')}"


def short_day(value: str) -> str:
    d = d_obj(value)
    return f"{d.strftime('%a')} {d.day}"


def days_text(days) -> str:
    runs: list[list[int]] = []
    for d in sorted(days):
        if runs and d == runs[-1][1] + 1:
            runs[-1][1] = d
        else:
            runs.append([d, d])
    parts = []
    for a, b in runs:
        if a == b:
            parts.append(DAY_ABBR[a])
        elif b == a + 1:
            parts.append(f"{DAY_ABBR[a]}, {DAY_ABBR[b]}")
        else:
            parts.append(f"{DAY_ABBR[a]}–{DAY_ABBR[b]}")
    return ", ".join(parts)


def friendly(name: str) -> str:
    """'Dr. Ananya Rao' -> 'Dr. Rao'; 'Asha Verma' -> 'Asha'."""
    parts = name.split()
    if parts and parts[0].lower().rstrip(".") == "dr" and len(parts) > 1:
        return f"Dr. {parts[-1]}"
    return parts[0] if parts else name


def initials(name: str) -> str:
    parts = [p for p in name.split() if p.lower().rstrip(".") != "dr"]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


# --------------------------------------------------------------------------- SVG art
EYE_MINI = (
    '<svg viewBox="0 0 64 64" width="46" height="46" xmlns="http://www.w3.org/2000/svg">'
    '<defs><linearGradient id="ncg1" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#7be0d8"/><stop offset="1" stop-color="#0fb5ae"/></linearGradient></defs>'
    '<path d="M4 32 C14 14 50 14 60 32 C50 50 14 50 4 32Z" fill="none" stroke="url(#ncg1)" stroke-width="4"/>'
    '<circle cx="32" cy="32" r="10" fill="url(#ncg1)"/><circle cx="32" cy="32" r="4" fill="#0b1f3a"/>'
    '<circle cx="36" cy="28" r="2.4" fill="#fff"/></svg>'
)

EYE_ART = (
    '<svg viewBox="0 0 320 220" xmlns="http://www.w3.org/2000/svg">'
    '<defs><linearGradient id="ncg2" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#7be0d8"/><stop offset="1" stop-color="#0a8f8a"/></linearGradient>'
    '<radialGradient id="ncg3" cx="50%" cy="50%" r="50%">'
    '<stop offset="0" stop-color="#7be0d8" stop-opacity=".55"/>'
    '<stop offset="1" stop-color="#7be0d8" stop-opacity="0"/></radialGradient></defs>'
    '<ellipse cx="160" cy="110" rx="155" ry="104" fill="url(#ncg3)"/>'
    '<path d="M12 110 C60 30 260 30 308 110 C260 190 60 190 12 110Z" fill="#ffffff" fill-opacity=".96" '
    'stroke="#cdeeee" stroke-width="3"/>'
    '<circle cx="160" cy="110" r="54" fill="url(#ncg2)"/>'
    '<circle cx="160" cy="110" r="40" fill="none" stroke="#fff" stroke-opacity=".28" stroke-width="2"/>'
    '<circle cx="160" cy="110" r="24" fill="#0b1f3a"/>'
    '<circle cx="177" cy="93" r="9" fill="#fff"/><circle cx="146" cy="126" r="4" fill="#fff" fill-opacity=".7"/>'
    '</svg>'
)


# --------------------------------------------------------------------------- HTML builders
def pill(status: str) -> str:
    label, fg, bg = STATUS_STYLE.get(status, (status.title(), "#334155", "#e2e8f0"))
    return f'<span class="nc-pill" style="color:{fg};background:{bg}">{label}</span>'


def hero() -> str:
    return H(f"""
    <div class="nc-hero">
      <div class="nc-hero-text">
        <div class="nc-badge">NETRACARE EYE CLINIC</div>
        <h1>See the world <span>clearly.</span><br/>We'll find you the right doctor.</h1>
        <p>Book a visit with one of our five specialists, change plans in two clicks and follow the
        waiting room live &mdash; no phone queues, no guesswork.</p>
        <div class="nc-chips"><span>5 specialists</span><span>Live waiting-room updates</span>
        <span>Easy rescheduling</span><span>Your data stays private</span></div>
      </div>
      <div class="nc-hero-art">{EYE_ART}</div>
    </div>""")


def brand() -> str:
    return H(f'<div class="nc-brand">{EYE_MINI}<div><div class="nc-brand-name">NetraCare</div>'
             '<div class="nc-brand-sub">Eye clinic</div></div></div>')


def user_chip(name: str, role_label: str) -> str:
    return H(f'<div class="nc-user"><div class="nc-user-av">{esc(initials(name))}</div>'
             f'<div><div class="nc-user-name">{esc(name)}</div><div class="nc-user-role">{esc(role_label)}</div></div></div>')


def page_header(title: str, subtitle: str = "") -> str:
    sub = f"<p>{esc(subtitle)}</p>" if subtitle else ""
    return H(f'<div class="nc-pagehead"><h2>{esc(title)}</h2>{sub}</div>')


def step_header(n: int, text: str) -> str:
    return H(f'<div class="nc-step"><b>{n}</b><span>{esc(text)}</span></div>')


def stat(label: str, value, icon: str = "", hint: str = "") -> str:
    hint_html = f'<div class="h">{esc(hint)}</div>' if hint else ""
    return H(f'<div class="nc-stat"><div class="ic">{icon}</div><div class="v">{esc(value)}</div>'
             f'<div class="l">{esc(label)}</div>{hint_html}</div>')


def empty(icon: str, title: str, text: str = "") -> str:
    """`text` may contain simple HTML (e.g. <code>); never pass user data here."""
    return H(f'<div class="nc-empty"><div class="ic">{icon}</div><div class="t">{esc(title)}</div>'
             f'<div class="s">{text}</div></div>')


def doctor_card(d: dict, compact: bool = False) -> str:
    bio = "" if compact else f'<p class="nc-bio">{esc(d["bio"])}</p>'
    quals = "" if compact else f'<div class="nc-sub">{esc(d["qualifications"])}</div>'
    return H(f"""
    <div class="nc-doc" style="--accent:{esc(d['color'])}">
      <div class="nc-avatar">{esc(initials(d['name']))}</div>
      <div class="nc-doc-body">
        <div class="nc-title">{esc(d['name'])}</div>
        <div class="nc-spec">{esc(d['specialty'])}</div>
        {quals}
        <div class="nc-tags"><span>{d['years_exp']} yrs experience</span><span>{esc(d['room'])}</span>
        <span>{days_text(d['work_days'])}</span></div>
        {bio}
      </div>
    </div>""")


def appt_card(a: dict, who: str = "doctor", show_doctor: bool = False) -> str:
    """who='doctor': headline is the doctor (patient view). who='patient': headline is the patient."""
    d = d_obj(a["date"])
    if who == "doctor":
        title, sub = a["doctor_name"], f'{a["specialty"]} · {a["room"]}'
    else:
        title = a["patient_name"]
        bits = [a.get("patient_phone") or ""]
        if show_doctor:
            bits.append(f'with {a["doctor_name"]} · {a["room"]}')
        sub = " · ".join(b for b in bits if b)
    reason = f'<div class="nc-reason">“{esc(a["reason"])}”</div>' if a.get("reason") else ""
    note = ""
    if who == "patient" and a.get("doctor_notes"):
        note = f'<div class="nc-note">\U0001F4DD {esc(a["doctor_notes"])}</div>'
    queue = ""
    if a.get("queue"):
        q = a["queue"]
        if who == "doctor":
            text = "You're next" if q["position"] == 1 else f'#{q["position"]} in line · about {q["est_wait_min"]} min'
        else:
            text = f'#{q["position"]} in line · about {q["est_wait_min"]} min'
        queue = f'<div class="nc-queue">\U0001FA91 In the waiting room · {text}</div>'
    return H(f"""
    <div class="nc-appt" style="--accent:{esc(a['doctor_color'])}">
      <div class="nc-when"><div class="d">{d.day}</div><div class="m">{d.strftime('%b')}</div>
      <div class="t">{fmt_time(a['time'])}</div></div>
      <div class="nc-appt-body"><div class="nc-title">{esc(title)}</div>
      <div class="nc-sub">{esc(sub)}</div>{reason}{note}{queue}</div>
      <div>{pill(a['status'])}</div>
    </div>""")


def waiting_room(waiting: list) -> str:
    if not waiting:
        return empty("\U0001FA91", "Waiting room is clear", "Checked-in patients appear here in arrival order.")
    by_doctor: dict[str, list] = {}
    for a in waiting:
        by_doctor.setdefault(a["doctor_name"], []).append(a)
    rows = ""
    for name, items in by_doctor.items():
        rows += f'<div class="nc-wait-doc">{esc(name)}</div>'
        for a in items:
            q = a.get("queue") or {}
            rows += (f'<div class="nc-wait-row"><b>#{q.get("position", "-")}</b><span>{esc(a["patient_name"])}</span>'
                     f'<em>~{q.get("est_wait_min", 0)} min</em></div>')
    return H(f'<div class="nc-card"><div class="nc-title">\U0001FA91 Waiting room</div>{rows}</div>')


def bars(labels: list, values: list, highlight: int | None = None) -> str:
    peak = max(values) if values and max(values) else 1
    cols = ""
    for i, (label, value) in enumerate(zip(labels, values)):
        height = max(4, round(150 * value / peak)) if value else 4
        cls = "nc-bar hl" if i == highlight else "nc-bar"
        cols += (f'<div class="nc-barcol"><div class="nc-val">{value}</div>'
                 f'<div class="{cls}" style="height:{height}px"></div><div class="nc-lab">{esc(label)}</div></div>')
    return H(f'<div class="nc-card"><div class="nc-chart">{cols}</div></div>')


def hbars(items: list[tuple[str, int, str]]) -> str:
    total = sum(v for _, v, _ in items) or 1
    rows = ""
    for label, value, color in items:
        pct = round(100 * value / total)
        rows += (f'<div class="nc-hrow"><span class="nc-hl">{esc(label)}</span>'
                 f'<div class="nc-htrack"><div class="nc-hfill" style="width:{pct}%;background:{color}"></div></div>'
                 f'<span class="nc-hv">{value}</span></div>')
    return H(f'<div class="nc-card">{rows}</div>')


def footer() -> str:
    return H('<div class="nc-foot">NetraCare is a demo clinic for learning purposes. This system never gives medical '
             'advice. In an emergency, contact your local emergency services.</div>')


# --------------------------------------------------------------------------- CSS
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Poppins:wght@500;600;700&display=swap');
:root{--navy:#0b1f3a;--navy2:#12407a;--teal:#0fb5ae;--teal2:#0a8f8a;--aqua:#7be0d8;--ink:#12263f;--muted:#5b7088;--coral:#ff7a59;--line:rgba(15,181,174,.22);--card:rgba(255,255,255,.88);--shadow:0 10px 30px rgba(11,31,58,.07);}
html,body,.stApp,[data-testid="stAppViewContainer"]{font-family:'Inter',system-ui,sans-serif;color:var(--ink);}
.stApp{background:radial-gradient(1100px 520px at 6% -8%,#d6f4f1 0%,rgba(214,244,241,0) 60%),radial-gradient(900px 480px at 100% 0%,#dbe7ff 0%,rgba(219,231,255,0) 58%),linear-gradient(180deg,#f6fcfc 0%,#eef5fb 100%);background-attachment:fixed;}
header[data-testid="stHeader"]{background:transparent;}
#MainMenu,footer,.stDeployButton{visibility:hidden;}
.block-container{padding-top:1.6rem;padding-bottom:3rem;max-width:1180px;}
h1,h2,h3,h4,h5{font-family:'Poppins',system-ui,sans-serif!important;color:var(--navy);letter-spacing:-.01em;}

/* ---------- hero (landing) ---------- */
.nc-hero{position:relative;overflow:hidden;border-radius:28px;padding:2.6rem 2.8rem;margin-bottom:1.6rem;background:linear-gradient(135deg,#0b1f3a 0%,#12407a 58%,#0fb5ae 135%);display:flex;align-items:center;justify-content:space-between;gap:1.5rem;box-shadow:0 30px 80px rgba(11,31,58,.28);}
.nc-hero:before{content:"";position:absolute;width:460px;height:460px;right:-130px;top:-170px;border-radius:50%;background:radial-gradient(circle,rgba(123,224,216,.45),rgba(123,224,216,0) 65%);}
.nc-hero:after{content:"";position:absolute;width:300px;height:300px;left:-90px;bottom:-150px;border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.10),rgba(255,255,255,0) 70%);}
.nc-hero-text{position:relative;z-index:1;}
.nc-hero h1{color:#fff!important;font-size:2.5rem;line-height:1.14;margin:.8rem 0 .9rem;font-weight:700;padding:0;}
.nc-hero h1 span{background:linear-gradient(90deg,#7be0d8,#d8fff8);-webkit-background-clip:text;background-clip:text;color:transparent;}
.nc-hero p{color:#d5e6f2;font-size:1.02rem;max-width:36rem;margin:0 0 1.1rem;line-height:1.6;}
.nc-badge{display:inline-block;padding:.35rem .85rem;border-radius:999px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.26);color:#e9fffb;font-size:.74rem;font-weight:700;letter-spacing:.12em;}
.nc-chips span{display:inline-block;margin:0 .45rem .45rem 0;padding:.35rem .85rem;border-radius:999px;background:rgba(123,224,216,.16);border:1px solid rgba(123,224,216,.42);color:#e9fffb;font-size:.82rem;font-weight:500;}
.nc-hero-art{flex:0 0 290px;position:relative;z-index:1;animation:floaty 6s ease-in-out infinite;filter:drop-shadow(0 20px 30px rgba(0,0,0,.25));}
@keyframes floaty{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
@media (max-width:900px){.nc-hero{flex-direction:column;padding:2rem 1.5rem}.nc-hero h1{font-size:1.9rem}.nc-hero-art{flex-basis:auto;width:220px}}

/* ---------- logged-in banner + page headers ---------- */
.nc-banner{display:flex;justify-content:space-between;align-items:center;border-radius:24px;padding:1.5rem 2rem;margin-bottom:1.3rem;background:linear-gradient(120deg,#0b1f3a,#12407a 62%,#0fb5ae 160%);box-shadow:0 22px 50px rgba(11,31,58,.22);}
.nc-banner h2{color:#fff!important;margin:.15rem 0;padding:0;font-size:1.8rem;}
.nc-banner p{color:#cfe3f0;margin:0;}
.nc-kicker{color:var(--aqua);font-weight:700;font-size:.78rem;letter-spacing:.12em;text-transform:uppercase;}
.nc-banner-art{opacity:.95;transform:scale(1.5);margin-right:1.2rem;}
.nc-pagehead{margin-bottom:1rem;}
.nc-pagehead h2{margin:0;padding:0;font-size:1.9rem;}
.nc-pagehead p{color:var(--muted);margin:.25rem 0 0;}

/* ---------- cards ---------- */
.nc-card{background:var(--card);backdrop-filter:blur(10px);border:1px solid var(--line);border-radius:20px;padding:1.1rem 1.3rem;box-shadow:var(--shadow);margin-bottom:.8rem;}
.nc-title{font-family:'Poppins',sans-serif;font-weight:600;font-size:1.02rem;color:var(--navy);}
.nc-sub{color:var(--muted);font-size:.86rem;}
.nc-doc{display:flex;gap:1rem;align-items:flex-start;background:var(--card);border:1px solid var(--line);border-left:5px solid var(--accent);border-radius:20px;padding:1.1rem 1.2rem;margin-bottom:.55rem;box-shadow:var(--shadow);transition:transform .2s ease,box-shadow .2s ease;}
.nc-doc:hover{transform:translateY(-3px);box-shadow:0 18px 40px rgba(11,31,58,.12);}
.nc-avatar{flex:0 0 54px;height:54px;border-radius:17px;background:linear-gradient(135deg,var(--accent),#0b1f3a);color:#fff;display:flex;align-items:center;justify-content:center;font-family:'Poppins',sans-serif;font-weight:700;font-size:1.1rem;box-shadow:0 8px 18px rgba(11,31,58,.22);}
.nc-doc-body{min-width:0;}
.nc-spec{color:var(--teal2);font-weight:600;font-size:.88rem;margin:.05rem 0 .25rem;}
.nc-tags{margin-top:.45rem;}
.nc-tags span{display:inline-block;margin:0 .35rem .3rem 0;padding:.18rem .6rem;border-radius:999px;background:#eaf7f6;color:#0b5f5b;font-size:.73rem;font-weight:600;}
.nc-bio{color:#3b536b;font-size:.88rem;line-height:1.5;margin:.5rem 0 0;}

.nc-appt{display:flex;align-items:center;gap:1rem;background:var(--card);border:1px solid var(--line);border-left:5px solid var(--accent,#0fb5ae);border-radius:18px;padding:.85rem 1.1rem;margin:.55rem 0 .4rem;box-shadow:var(--shadow);}
.nc-when{flex:0 0 78px;text-align:center;border-radius:14px;padding:.45rem .3rem;background:linear-gradient(160deg,#eefbfa,#e2f1ff);}
.nc-when .d{font-family:'Poppins',sans-serif;font-weight:700;font-size:1.5rem;line-height:1;color:var(--navy);}
.nc-when .m{font-size:.7rem;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:700;}
.nc-when .t{font-size:.76rem;font-weight:700;color:var(--teal2);margin-top:.25rem;}
.nc-appt-body{flex:1;min-width:0;}
.nc-reason{margin-top:.25rem;font-size:.85rem;color:#33506b;font-style:italic;}
.nc-note{margin-top:.35rem;padding:.35rem .6rem;border-radius:10px;background:#fff8e6;color:#8a5a00;font-size:.82rem;}
.nc-queue{margin-top:.45rem;display:inline-block;padding:.25rem .75rem;border-radius:999px;background:#ccfbf1;color:#0f766e;font-weight:700;font-size:.8rem;}
.nc-pill{display:inline-block;padding:.25rem .75rem;border-radius:999px;font-size:.75rem;font-weight:700;white-space:nowrap;}

.nc-stat{position:relative;overflow:hidden;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:1rem 1.2rem;margin-bottom:.8rem;box-shadow:var(--shadow);}
.nc-stat:after{content:"";position:absolute;right:-34px;top:-34px;width:100px;height:100px;border-radius:50%;background:radial-gradient(circle,rgba(15,181,174,.26),transparent 70%);}
.nc-stat .ic{font-size:1.35rem;}
.nc-stat .v{font-family:'Poppins',sans-serif;font-weight:700;font-size:1.9rem;line-height:1.1;color:var(--navy);margin-top:.15rem;}
.nc-stat .l{color:var(--muted);font-size:.76rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;}
.nc-stat .h{color:var(--muted);font-size:.78rem;}

.nc-empty{text-align:center;padding:2rem 1rem;background:var(--card);border:1px dashed rgba(15,181,174,.45);border-radius:20px;margin-bottom:.8rem;}
.nc-empty .ic{font-size:2.2rem;}
.nc-empty .t{font-family:'Poppins',sans-serif;font-weight:600;font-size:1.1rem;color:var(--navy);margin-top:.3rem;}
.nc-empty .s{color:var(--muted);margin-top:.25rem;font-size:.92rem;line-height:1.6;}
.nc-empty code{background:#e6f6f5;padding:.1rem .4rem;border-radius:6px;color:#0a6f6b;}

.nc-step{display:flex;align-items:center;gap:.7rem;margin:1.4rem 0 .6rem;}
.nc-step b{width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,var(--teal),var(--navy2));color:#fff;display:flex;align-items:center;justify-content:center;font-family:'Poppins',sans-serif;font-size:.95rem;box-shadow:0 6px 14px rgba(15,181,174,.35);}
.nc-step span{font-family:'Poppins',sans-serif;font-weight:600;font-size:1.12rem;color:var(--navy);}
.nc-fact{display:flex;gap:.9rem;align-items:center;margin-top:1rem;padding:1rem 1.3rem;border-radius:20px;background:linear-gradient(120deg,#e7fbf8,#e6efff);border:1px solid var(--line);color:#173553;}
.nc-fact b{font-family:'Poppins',sans-serif;color:var(--teal2);white-space:nowrap;}
.nc-steps{margin:.5rem 0 0;padding:0;list-style:none;}
.nc-steps li{display:flex;gap:.7rem;align-items:flex-start;margin:.55rem 0;color:#27435d;font-size:.9rem;}
.nc-steps li i{flex:0 0 26px;height:26px;border-radius:50%;background:#dff5f3;color:var(--teal2);font-style:normal;font-weight:700;display:flex;align-items:center;justify-content:center;font-size:.8rem;}
.nc-panel-title{font-family:'Poppins',sans-serif;font-weight:600;color:var(--navy);margin:.3rem 0 .2rem;}
.nc-divider{display:flex;align-items:center;gap:.7rem;color:var(--muted);font-size:.8rem;margin:.9rem 0 .6rem;}
.nc-divider:before,.nc-divider:after{content:"";flex:1;height:1px;background:var(--line);}
.nc-wait-doc{margin:.7rem 0 .25rem;font-weight:700;font-size:.8rem;color:var(--teal2);text-transform:uppercase;letter-spacing:.06em;}
.nc-wait-row{display:flex;align-items:center;gap:.6rem;padding:.4rem .6rem;margin:.2rem 0;border-radius:12px;background:#f1fbfa;font-size:.88rem;}
.nc-wait-row b{color:var(--navy);min-width:1.8rem;}
.nc-wait-row span{flex:1;}
.nc-wait-row em{color:var(--muted);font-style:normal;font-size:.8rem;}
.nc-foot{margin-top:2.5rem;text-align:center;color:var(--muted);font-size:.78rem;}
.nc-cred{padding:1rem 1.2rem;border-radius:18px;background:#fff8e6;border:1px solid #f5d98a;color:#6b4a00;margin-bottom:.8rem;line-height:1.7;}
.nc-cred code{background:#fff;padding:.1rem .45rem;border-radius:6px;font-size:.95rem;}

/* ---------- charts (pure HTML/CSS, so they always match the theme) ---------- */
.nc-chart{display:flex;align-items:flex-end;gap:.45rem;height:215px;padding:.3rem .2rem 0;}
.nc-barcol{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;min-width:0;}
.nc-bar{width:100%;max-width:34px;border-radius:9px 9px 3px 3px;background:linear-gradient(180deg,#7be0d8,#0fb5ae);}
.nc-bar.hl{background:linear-gradient(180deg,#12407a,#0b1f3a);}
.nc-val{font-size:.72rem;font-weight:700;color:var(--navy);margin-bottom:.2rem;}
.nc-lab{font-size:.66rem;color:var(--muted);margin-top:.35rem;white-space:nowrap;}
.nc-hrow{display:flex;align-items:center;gap:.7rem;margin:.55rem 0;}
.nc-hl{flex:0 0 90px;font-size:.84rem;font-weight:600;color:#27435d;}
.nc-htrack{flex:1;height:12px;border-radius:999px;background:#e5f1f4;overflow:hidden;}
.nc-hfill{height:100%;border-radius:999px;}
.nc-hv{flex:0 0 34px;text-align:right;font-weight:700;color:var(--navy);font-size:.88rem;}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0b1f3a 0%,#0e2e55 62%,#0a6f73 135%);}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] span,[data-testid="stSidebar"] label,[data-testid="stSidebar"] div{color:#e8f4f8;}
[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,.16);}
.nc-brand{display:flex;align-items:center;gap:.7rem;padding:.4rem .2rem 1rem;}
.nc-brand-name{font-family:'Poppins',sans-serif;font-weight:700;font-size:1.35rem;color:#fff;line-height:1.1;}
.nc-brand-sub{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--aqua);}
.nc-user{display:flex;align-items:center;gap:.7rem;padding:.7rem .8rem;margin-bottom:1rem;border-radius:16px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);}
.nc-user-av{width:38px;height:38px;border-radius:12px;background:linear-gradient(135deg,var(--aqua),var(--teal));color:#0b1f3a!important;font-weight:700;display:flex;align-items:center;justify-content:center;}
.nc-user-name{font-weight:600;font-size:.92rem;color:#fff;}
.nc-user-role{font-size:.74rem;color:var(--aqua);}
[data-testid="stSidebar"] [role="radiogroup"]{gap:.25rem;}
[data-testid="stSidebar"] label[data-baseweb="radio"]{padding:.6rem .8rem;border-radius:12px;width:100%;margin:0;transition:background .15s ease;}
[data-testid="stSidebar"] label[data-baseweb="radio"]:hover{background:rgba(255,255,255,.10);}
[data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child{display:none;}
[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked){background:linear-gradient(90deg,rgba(15,181,174,.42),rgba(15,181,174,.08));box-shadow:inset 3px 0 0 #7be0d8;}
[data-testid="stSidebar"] .stButton>button{background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.28);}
[data-testid="stSidebar"] .stButton>button:hover{background:rgba(255,255,255,.18);color:#fff;border-color:var(--aqua);}

/* ---------- controls ---------- */
.stButton>button,.stFormSubmitButton>button{width:100%;border-radius:12px;border:1.5px solid rgba(15,181,174,.5);background:#fff;color:var(--navy);font-weight:600;padding:.5rem 1rem;transition:all .18s ease;}
.stButton>button:hover,.stFormSubmitButton>button:hover{border-color:var(--teal);color:var(--teal2);transform:translateY(-1px);box-shadow:0 8px 20px rgba(15,181,174,.2);}
.stButton>button:disabled{background:#eef3f6;color:#9db0bf;border-color:#dbe5eb;transform:none;box-shadow:none;}
button[kind="primary"],button[kind="primaryFormSubmit"],button[data-testid="stBaseButton-primary"],button[data-testid="stBaseButton-primaryFormSubmit"]{background:linear-gradient(135deg,#0fb5ae,#12407a)!important;border:none!important;color:#fff!important;box-shadow:0 10px 24px rgba(15,181,174,.32);}
button[kind="primary"] p,button[kind="primaryFormSubmit"] p,button[data-testid="stBaseButton-primary"] p,button[data-testid="stBaseButton-primaryFormSubmit"] p{color:#fff!important;}
button[kind="primary"]:hover,button[kind="primaryFormSubmit"]:hover,button[data-testid="stBaseButton-primary"]:hover,button[data-testid="stBaseButton-primaryFormSubmit"]:hover{filter:brightness(1.07);color:#fff!important;}
[data-testid="stForm"]{border:1px solid var(--line);border-radius:22px;background:rgba(255,255,255,.82);backdrop-filter:blur(8px);padding:1.3rem 1.3rem .6rem;box-shadow:0 18px 50px rgba(11,31,58,.08);}
.stTextInput input,.stTextArea textarea,.stDateInput input,.stNumberInput input{border-radius:12px!important;}
.stSelectbox div[data-baseweb="select"]>div{border-radius:12px!important;}
button[data-baseweb="tab"]{font-weight:600;}
[data-testid="stAlert"]{border-radius:14px;}
[data-testid="stExpander"]{border-radius:16px;border:1px solid var(--line);background:rgba(255,255,255,.7);}
[data-testid="stDataFrame"]{border-radius:16px;overflow:hidden;border:1px solid var(--line);}
"""


def inject() -> None:
    st.markdown("<style>\n" + CSS + "\n</style>", unsafe_allow_html=True)
