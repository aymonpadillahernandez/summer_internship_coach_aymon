# Summer Internship Coach

**Live app: https://summer-internship-coach.onrender.com** · click **Try the demo** (no account needed; a private sandbox with a fictional student)

> The free hosting plan sleeps when idle. A scheduled GitHub Action keeps it awake from 8 AM to 1 AM US Eastern;
> outside those hours the first visit can take up to a minute.

From scattered opportunities and conversations to the next best career action. An AI career operating system for MBA
students recruiting for summer internships: paste what's new (emails, chat exports, job postings, your LinkedIn CSV),
and three agents keep one evidence-backed picture of your search and tell you where to spend this week.

## What it does

| Screen | What you get |
|---|---|
| **Today** | **Plan my week**: the Career strategist ranks your open actions after consulting both specialists, with *why now*, *first step* and the records it relied on. **Add what's new**: paste or upload text; the specialists file opportunities, people and dated facts, each with the exact quote it came from. |
| **Opportunities** | Pipeline board (Not started → Offer / Rejected) with deadlines, MBA eligibility, fit, people who can help. |
| **Networking** | People pipeline (To contact → Keep warm) with sources, next steps and follow-up timing. |
| **Action plan** | Every to-do worked out from your records in code (deadlines, nudges, follow-ups, calls): zero tokens. |
| **Ask your coach** | Chat with the Career strategist; "Prepare my call with …" goes to Network intelligence's call-prep expert. |
| **Usage** | Every AI run with the real input, cached input and output tokens the model reported, per agent. |

It never sends anything on your behalf: drafts are for you to send.

## The agents (all on `gpt-6-luna` through the course Portkey key)

```
                    ┌──────────────────────────────┐
  Plan / chat  ───▶ │  Career strategist (boss)    │  ranks only the actions the app derived; output validated
                    └──────┬────────────────┬──────┘
          ask_opportunity_scout()      ask_network_intel()        (max 4 questions per request)
                    ┌──────▼──────┐   ┌─────▼──────────────┐
                    │ Opportunity │   │ Network            │  each reads only the 10 records BM25 finds
                    │ scout       │   │ intelligence       │  for the question, and cites OPP-/CON- ids
                    └──────▲──────┘   └─────▲──────────────┘
  Paste / upload ─▶ Shield ─▶ Router ───────┘   (code, zero tokens: hidden text removed, injected
                    (code)    (code)              instructions quarantined, then routed by content)
```

- **Opportunity scout** turns postings and emails into opportunities (deadline, MBA eligibility, fit with your profile).
- **Network intelligence** turns conversations and exports into people, stages and dated, quoted facts; prepares calls.
- **Career strategist** decides where your week goes, delegating questions to the two specialists.
- After every model answer, code checks it: quotes must appear in your text, people must be named in it, ids must
  be yours, invented actions are refused, and email addresses / phone numbers are never stored.

## Run it locally (about 5 minutes)

Needs **Python 3.12+** and **Node 20+**.

1. Put a `.env` with `PORTKEY_API_KEY=…` in this folder **or one folder above it** (see `.env.example`).
2. Install and start the backend:
   ```bash
   cd backend
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```
3. Build the website (once):
   ```bash
   cd ../frontend
   npm ci
   npm run build
   ```
4. Start the app (it serves the API and the website):
   ```bash
   cd ../backend
   .venv/bin/python -m uvicorn main:app --port 8020
   ```
5. Open **http://127.0.0.1:8020** and click **Try the demo**.

Check the key and model on their own: `cd backend && .venv/bin/python check_setup.py` (prints which `.env` was
used, the model that answered and the tokens of one call).

Developing the frontend with hot reload: run step 4, then `cd frontend && npm run dev` and open http://127.0.0.1:5190.

## Data: demo vs real

- **Demo (test dataset, in the repo):** `data/demo/demo_seed.json`, a fictional student with 12 opportunities, 12
  people and 4 leads, plus `data/demo/samples/` (texts to paste, including two prompt-injection attacks). Every
  name and organisation in it is invented. Dates are relative to today, so the demo never goes stale.
- **Real data:** create an account and paste your own texts. Locally it is stored in `data/coach.db` (SQLite,
  created on first start, git-ignored). Set `DATABASE_URL` to a Postgres URL to use Postgres instead (the live app
  uses Supabase). The pasted texts themselves are never stored, only the facts and the quotes that back them.

## Environment variables

| Variable | Needed | What for |
|---|---|---|
| `PORTKEY_API_KEY` | yes | The course key; the app calls `gpt-6-luna` only. |
| `DATABASE_URL` | no | Postgres connection string. Without it: local SQLite. |
| `DAILY_TOKEN_BUDGET` | no | Tokens per student per UTC day (default 300,000). Over it, AI routes return 429. |
| `GLOBAL_DAILY_TOKEN_BUDGET` | no | Tokens for the whole site per UTC day (default 3,000,000). |
| `SIGNUP_CODE` | no | If set, creating an account asks for it. |

`.env` lookup order: the repo folder, then one folder above it (a third, workspace-only fallback two folders up is
documented in `backend/config.py`). Variables already set by the host (e.g. Render) win.

## Safety and limits (tested)

```bash
backend/.venv/bin/python -m pytest tests -v     # 10 tests, no API key needed, no tokens spent
```

They cover prompt injection in pasted text, hidden text in web pages, invented quotes and people, a 600-row LinkedIn export filtered in code, one student
reading another's data, runaway delegation and tool loops, invented actions, model substitution, oversized input
and the daily token budget. Limits live in `backend/config.py` (`AGENT_REQUEST_LIMIT`, `MAX_DELEGATIONS_PER_RUN`,
`AGENT_TOTAL_TOKENS_LIMIT`, `MAX_INPUT_CHARS`, `DAILY_TOKEN_BUDGET`, …).

## Project structure

```
backend/   FastAPI app (main.py), agents/ (strategist, scout, network, runtime), prompts/, safety.py, merge.py,
           intake.py, retrieval.py (BM25), db.py + store.py (SQLite / Postgres), auth.py, demo.py, check_setup.py
frontend/  React + Vite + TypeScript (Today, boards, action plan, chat, usage)
data/demo/ the fictional test dataset and paste samples
tests/     safety tests (pytest)
docs/      evidence (token runs, test output, screenshots) used in the report
```

Built from the author's personal internship tracker (boards, action plan, merge rules, call prep), rebuilt as a
separate multi-user product with in-app agents, token accounting and safety defenses.
