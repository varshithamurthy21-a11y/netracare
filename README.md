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

**Built-in safety rules:** no medical advice anywhere · raw clinical notes never reach patients · AI drafts need a doctor's approval ·
red flags are reviewed by humans · every change is audit-logged.

## Layout
```
backend/   config · db · security · services (all business rules) · triage · facts · llm · seed · main (FastAPI)
frontend/  app.py · theme.css · ui.py (HTML components) · booking.py · views/{auth,patient,doctor,frontdesk,admin}.py
tests/     service-level tests
```
## Next iterations
3 · RAG chat over doctor/procedure/cost docs (`backend/` gets a `rag/` package) · 4 · LangGraph booking agent calling the
same `services.book/cancel/reschedule` as tools, with human approval · 5 · evals + Opik traces · 6 · clinic MCP server wrapping `services`.
