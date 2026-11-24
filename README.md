# 👁️ NetraCare — AI front desk for a fictional eye clinic

Five doctors, busy front desks, patients routed to the wrong specialist. NetraCare books, routes and coordinates
**without ever giving medical advice**, and keeps staff in control.

## Run it (2 minutes)

```bash
pip install -r requirements.txt
python run.py          # starts API on :8000 and app on :8501 (or ./run.sh; or run the two commands below in two terminals)
# uvicorn backend.main:app --reload
# streamlit run frontend/app.py
```
Open http://localhost:8501 and use the one-click **demo accounts** on the login page.
API docs: http://localhost:8000/docs · Tests: `python -m pytest`

Optional AI text (eye fact, visit-summary drafts): copy `.env.example` to `.env` and add a `GOOGLE_API_KEY`
(Gemini) or `ANTHROPIC_API_KEY`. With no key everything still works using built-in fallbacks.

| Role | Email | Password |
|---|---|---|
| Patient | patient@netracare.demo | Patient@123 |
| Doctor (5) | ananya / karthik / meera / rohan / sneha @netracare.demo | Doctor@123 |
| Front desk | desk@netracare.demo | Desk@123 |
| Admin | admin@netracare.demo | Admin@123 |

## What's built

**Iteration 1 — clinic website**
- Sign up / sign in (signed expiring tokens, PBKDF2 passwords), four roles with their own dashboards
- Patient: book (doctor cards → date → slot grid → reason), cancel, **one-click reschedule**, history, profile, reminders
- Doctor: today's schedule, complete visits, upcoming days
- Front desk: **live queue with wait estimates**, check-in, no-show, book for any patient, register walk-ins
- Admin: stats & charts, add/pause doctors, manage accounts, **audit log** of every action
- Rules: Mon–Sat hours, 14-day window, max 3 upcoming per patient, **double-booking impossible** (DB unique index)

**Iteration 2 — first LLM features (with safe fallbacks)**
- **Eye fact banner** (curated, or AI-written once a day)
- **Visit summary**: doctor's notes → patient-friendly draft → *doctor edits & approves* → only then visible to the patient
- **Red flags**: risky wording ("sudden vision loss", "chemical splash"…) flags the booking for the front desk; the patient
  sees an emergency pointer. Rule-based now — Iteration 2's LangChain classifier plugs into `backend/triage.py`
- **"Which doctor?" helper** routes free text to a specialty (preview of Iteration 3 routing)

**Iteration 3 — patient chat with RAG** (`backend/rag.py`, `backend/assistant.py`)
- Knowledge base in `backend/knowledge/*.md` plus live doctor profiles, split into chunks with ids like `costs#test-prices`
- **Hybrid search**: BM25 + character-n-gram similarity, merged by Reciprocal Rank Fusion, with synonyms
- Answers carry **numbered citations**; if nothing relevant is found the bot says so instead of guessing
- Guardrails: prompt-injection filter, medical-advice refusal (offers a specialist instead), red-flag emergency message, routing to the right doctor
- Set `GOOGLE_API_KEY` or `ANTHROPIC_API_KEY` for LLM-written answers; without a key it quotes the best sentences (extractive)

**Iteration 4 — booking agent with human approval** (`backend/agent/`)
- Slot-filling conversation: book, cancel, reschedule, list appointments, book partner-lab tests
- A small state graph (nodes + an `INTERRUPT` pause, same shape as LangGraph). **Write tools raise `ApprovalRequired`** unless the
  patient said yes; only the `execute` node sets `approved=True`. State is stored per patient in `agent_sessions`
- Asking a question while a request is pending answers it and keeps the request alive

**Iteration 5 — evals & observability** (`backend/evals/`, `backend/observability.py`)
- Datasets in `backend/evals/datasets/*.jsonl`: RAG Q&A (incl. unanswerable), safety, specialist routing, agent NLU + approval gate
- Metrics: recall@3, top-1, abstain-on-unanswerable, judge relevance/safety, unsafe leaks (must be 0)
- Judge: LLM-as-judge when a key is set, otherwise a heuristic judge. Run: `python -m backend.evals.runner` or Admin → Evals & Traces
- Every chat request is a trace with spans, latency and **estimated** tokens/cost. Optional Opik mirroring (`pip install opik`, set `OPIK_API_KEY`)

**Iteration 6 — MCP & Agent Skills** (`mcp_servers/`, `backend/mcp_client.py`, `skills/`)
- Two stdio MCP servers: the clinic (`mcp_servers/clinic_server.py`) and a separate **partner lab** (ClearView Diagnostics, own database)
- The assistant calls the lab through an MCP client; Admin → MCP & Skills lists the servers' tools
- Five Agent Skills (`skills/*/SKILL.md`), loaded progressively: descriptions always, full text only when relevant

**Built-in safety rules:** no medical advice anywhere · raw clinical notes never reach patients · AI drafts need a doctor's approval ·
red flags are reviewed by humans · every change is audit-logged.

## Layout
```
backend/   config · db · security · services (business rules) · triage · facts · llm · seed · main (FastAPI)
           rag · assistant · observability · skills · mcp_client · agent/ · evals/ · knowledge/
mcp_servers/  base · clinic_server · partner_lab_server
skills/    one folder per Agent Skill (SKILL.md)
frontend/  app.py · theme.css · ui.py · booking.py · views/{auth,patient,chat,doctor,frontdesk,admin,admin_ops}.py
tests/     services, assistant/RAG/agent/evals, MCP
```

## Tests
`pytest -q` (the MCP SDK test is skipped unless `pip install mcp`). CI: `.github/workflows/tests.yml`.

## Honest notes
- The eval sets are small (about 90 cases) and written by the project author, so a 100% score means "no known regressions", not "perfect".
- Token and cost figures are estimates. The agent uses its own small graph engine rather than the `langgraph` package.
- Free hosting sleeps when idle; the first request after a nap can take about a minute.
