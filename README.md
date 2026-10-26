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
| **Today** | **Plan my week**: the Career strategist ranks your open actions after consulting both specialists, with *why now*, *first step* and the records it relied on. **Add what's new**: paste or upload text, or paste a careers-page link; the specialists file opportunities, people and dated facts, each with the exact quote it came from. New accounts get a three-step guide. |
| **Opportunities** | Pipeline board (Not started → Offer / Rejected) with deadlines, MBA eligibility, fit and the page check. On each card, **Who can open the door**: Network intelligence finds up to 3 ways in from people you know, with what to ask and a first message you send yourself. |
| **Networking** | People pipeline (To contact → Keep warm) with sources, next steps and follow-up timing. |
| **Action plan** | Every to-do worked out from your records in code (deadlines, nudges, follow-ups, calls): zero tokens. |
| **Ask your coach** | Chat with the Career strategist; "Prepare my call with …" goes to Network intelligence's call-prep expert. |
| **Connect** | Which channels update on their own and which need an export, then step-by-step setup, all free. **Updates on its own:** the Coach Connector, a small script on your own Mac, reads Gmail (plus school mail forwarded to it), Messages (iMessage / SMS) and WhatsApp Desktop read-only, filters on your computer and, with auto-sync on, checks every 30 minutes and sends only what's new. **Export or paste:** LinkedIn's data download (Connections.csv, messages.csv), Slack, Android texts, calendar invites (.ics), WhatsApp's Export chat without a Mac, job postings. Live status per channel (on, needs Full Disk Access, not connected). |
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

- **Opportunity scout** turns postings, emails and linked careers pages into opportunities (deadline, MBA eligibility,
  whether applications are open, fit with your profile). Its one internet tool reads a page you link (`backend/web.py`:
  public addresses only, every redirect re-checked, size and time limits, robots.txt respected, no bot-bypassing).
- **Network intelligence** turns conversations and exports into people, stages and dated, quoted facts; finds who can
  open the door at each target; prepares calls.
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

## Connecting channels (Connect tab)

All free and read-only; nothing is ever sent from a student's accounts.

- **Coach Connector** (`connector/coach_connector.py`, Python standard library only, works with macOS's built-in
  `python3`). The student creates a connector key on the Connect tab (shown once, stored hashed, revocable), then:
  `curl -fsSL <site>/connector/coach_connector.py -o ~/coach_connector.py`, `python3 ~/coach_connector.py setup`,
  `python3 ~/coach_connector.py run --dry-run` (shows counts, sends nothing), `python3 ~/coach_connector.py run`.
  - **Gmail:** an app password kept in the macOS Keychain (IMAP, read-only, emails stay unread).
  - **Messages:** opens `~/Library/Messages/chat.db` read-only; needs Full Disk Access.
  - **WhatsApp:** opens WhatsApp Desktop's own database on the Mac read-only and never connects to WhatsApp. It is not a
    WhatsApp feature, so setup asks first, and Export chat stays available.
  - **What is sent:** email matching the student's organisations, people or recruiting words. Chats only if one of their
    people is in it, a target organisation comes up with a recruiting word or an introduction, or a clear recruiting
    phrase appears. Phone numbers are masked (also when saved as a name), groups of more than 8 members are skipped, and
    only new messages that matter are sent, with 10 messages of context. Progress is tracked by database row id (late
    messages still count) and saved per upload, so a failure never re-sends what the coach already has. Everything goes
    through the same shield and specialists as a paste.
- **Auto-sync:** `python3 ~/coach_connector.py schedule` installs a per-user macOS LaunchAgent that runs every 30
  minutes while the Mac is awake (`--every N` to change, `status`, `unschedule`). Each run reports counts and a fixed
  reason code only to `POST /api/connector/checked` (zero tokens; the full error stays in the Mac's log), so the Connect
  tab shows "Auto-sync on", "Needs Full Disk Access", "Synced by hand" or "hasn't checked since …". One channel failing
  never stops the others. macOS asks once more for Full Disk Access for the scheduled Python; the command prints
  the exact path and opens the settings page. That grant covers that Python for every script, which the tab says;
  without it Gmail still syncs on its own and Messages / WhatsApp can be synced by hand.
- **Uploads** go to `POST /api/intake/file`: `.zip` (WhatsApp export, zip-bomb limits), `.pdf`, `.eml` (sender name
  only, hidden HTML removed), `.ics`, `.csv`, `.txt`, `.html`; 5 MB max. LinkedIn `messages.csv` is filtered in code
  to conversations with the student's people, about their targets or about recruiting.
- **Why not automatic everywhere:** LinkedIn has no API to read messages, school Slack workspaces only allow
  admin-approved apps, Android keeps texts on the phone, and Handshake / LinkedIn Jobs forbid scraping. iMessage
  and WhatsApp have no API either: they are automatic only because the connector reads the Mac apps' own data. Official sources: `docs/research/channels.md`.

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
backend/.venv/bin/python -m pytest tests -v     # 39 tests, no API key needed, no tokens spent
```

They cover prompt injection in pasted text, hidden text in web pages and linked pages, links to private or local
addresses (also after a redirect), bot protection, invented quotes and people, a 600-row LinkedIn export filtered in code, connector keys (hashed, revocable, one
student only), file uploads (WhatsApp zip, email, zip bombs, unsupported types refused at 0 tokens), LinkedIn
messages filtered to the student's people and targets, auto-sync (the LaunchAgent, WhatsApp Desktop read and
masked, unchanged chats never re-sent, one failing channel not stopping the others, counts-only reports), one student
reading another's data, runaway delegation and tool loops, invented actions, model substitution, oversized input
and the daily token budget. Limits live in `backend/config.py` (`AGENT_REQUEST_LIMIT`, `MAX_DELEGATIONS_PER_RUN`,
`AGENT_TOTAL_TOKENS_LIMIT`, `MAX_INPUT_CHARS`, `DAILY_TOKEN_BUDGET`, …).

## Project structure

```
backend/   FastAPI app (main.py), agents/ (strategist, scout, network, runtime), prompts/, safety.py, merge.py,
           intake.py, web.py (link reader), retrieval.py (BM25), db.py + store.py (SQLite / Postgres), auth.py,
           files.py (uploads), signals.py (what to keep), demo.py, check_setup.py
connector/ coach_connector.py, the free local Gmail + Messages + WhatsApp Desktop reader (with auto-sync)
frontend/  React + Vite + TypeScript (Today, boards, action plan, Connect, chat, usage)
data/demo/ the fictional test dataset and paste samples
tests/     safety tests (pytest)
docs/      evidence (token runs, test output, screenshots) used in the report
```

Built from the author's personal internship tracker (boards, action plan, merge rules, call prep), rebuilt as a
separate multi-user product with in-app agents, token accounting and safety defenses.
