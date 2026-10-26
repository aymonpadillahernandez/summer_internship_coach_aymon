# Summer Internship Coach

**Live app: https://summer-internship-coach.onrender.com** · click **Try the demo** (no account needed; a private sandbox with a fictional student)

> The free hosting plan sleeps after 15 idle minutes: the first visit can take up to a minute while it wakes. A
> scheduled GitHub Action pings it, but GitHub runs schedules only sporadically, so open the URL a minute ahead.

From scattered opportunities and conversations to the next best career action. An AI career operating system for MBA
students recruiting for summer internships. Connect or export your channels (Gmail, Messages, WhatsApp, LinkedIn,
Slack, calendar, postings): five agents keep one evidence-backed picture of your search, find openings on public job
boards, and tell you where to spend this week. Nothing is ever sent for you.

## What it does

| Screen | What you get |
|---|---|
| **Today** | **Plan my week**: the Career coach ranks your open actions after consulting both specialists, with *why now*, *first step* and the records it relied on. **Add what's new**: paste or upload text, or paste a careers-page link; the Inbox organizer files opportunities, people and dated facts, each with the exact quote it came from. New accounts get a three-step guide. **Find openings**: the Opportunity scout searches the public job boards of your organisations. **Outbox**: drafts the coach wrote, never sent by the app. |
| **Opportunities** | Pipeline board (Not started → Offer / Rejected) with deadlines, MBA eligibility, fit and the page check. On each card, **Who can open the door**: Network intelligence finds up to 3 ways in from people you know, with what to ask and a first message you send yourself. |
| **Networking** | People pipeline (To contact → Keep warm) with sources, next steps and follow-up timing. |
| **Action plan** | Every to-do worked out from your records in code (deadlines, nudges, follow-ups, calls): zero tokens. |
| **Ask your coach** | Chat with the Career coach; "Prepare my call with …" goes to Network intelligence's call-prep expert. |
| **Setup** (step 1 for new accounts) | The **Setup guide** agent walks you through it next to a checklist. Which channels update on their own and which need an export, then step-by-step setup, all free. **Updates on its own:** the Coach Connector, a small script on your own Mac, reads Gmail (plus school mail forwarded to it), Messages (iMessage / SMS) and WhatsApp Desktop read-only, filters on your computer and, with auto-sync on, checks every 30 minutes and sends only what's new. **Export or paste:** LinkedIn's data download (Connections.csv, messages.csv), Slack, Android texts, calendar invites (.ics), WhatsApp's Export chat without a Mac, job postings. Live status per channel (on, needs Full Disk Access, not connected). |
| **Usage** | Every AI run with the real input, cached input and output tokens the model reported, per agent. |

It never sends anything on your behalf: drafts are for you to send.

## The agents (all on `gpt-6-luna` through the course Portkey key)

Five AI agents, each with its own tools and skills, and one component in code that writes every card:

```
 New account ─▶ Setup guide ............ walks you through connecting or exporting every channel (step 1)
                tools: connection_status, next_setup_step, load_skill (11 channel playbooks)

 Any channel ─▶ Shield ─▶ Router ─▶ Inbox organizer ─▶ Records keeper ─▶ cards (Opportunities, Networking,
 (paste, file,  (code)    (code)    one call per text:   (code, 0 tokens:   Action plan)
  connector)                        roles, people, dates  checks every quote, name, link, id;
                                                          merge rules; data checks)
 Find openings ─▶ Opportunity scout ─▶ Records keeper
                  tools: search_job_boards (Greenhouse, Lever, Ashby, SmartRecruiters public APIs), read_careers_page

 Plan / chat ─▶ Career coach (boss) ── ask_opportunity_scout ─▶ Opportunity scout   (BM25: 10 records per question)
                tools: load_skill,    ── ask_network_intel ────▶ Network intelligence (doors, call prep)
                save_draft (Outbox), get_data_checks             max 4 questions per request; specialists cannot delegate
```

| Agent | What it does | Tools | Skills (`backend/skills/`) |
|---|---|---|---|
| **Setup guide** | Step 1 of a new account: one step at a time through Gmail, school mail, Messages, WhatsApp, LinkedIn, Slack, Android texts, calendar, postings | `connection_status`, `next_setup_step`, `load_skill` | 11 channel playbooks + troubleshooting |
| **Inbox organizer** | Reads one text from any channel into opportunities, leads and people with exact quotes (one call per text) | none (reads only the text) | reading email, chats, LinkedIn exports, postings, invites; stage definitions |
| **Opportunity scout** | Finds summer internships on public job boards and careers pages, judges fit; answers the coach about opportunities | `search_job_boards`, `read_careers_page` | source policy, MBA eligibility, reading a posting, fit rubric |
| **Career coach** | The boss: plans the week, answers questions, prepares coffee chats, drafts notes into the Outbox | `ask_opportunity_scout`, `ask_network_intel`, `get_data_checks`, `load_skill`, `save_draft` | coffee-chat prep, prioritization, follow-ups, outreach drafts, interview prep, recruiting timeline |
| **Network intelligence** | Relationships, who can open the door, call prep | none (reads retrieved records or a dossier) | relationship strength, warm-intro paths, call prep |
| **Records keeper** (code) | The only writer of cards: validates every item against its source, merge rules, data checks | n/a | n/a |

Chat agents open a skill only when needed (`load_skill`); pipeline agents get theirs in their instructions, a stable
prefix the provider can cache. The scout never scrapes Handshake or LinkedIn (their terms forbid it), and a posting is
saved only if it quotes what a tool returned in that run, with a link the tool returned.

### Guardrails (all in `backend/config.py`, all tested in `tests/test_team.py` and `tests/test_safety.py`)

- **Nothing is sent without you:** no agent has a sending tool (a test fails if one ever does). The coach's drafts wait in
  the Outbox; approving one only copies it or opens your own mail app.
- **No endless loops:** per-run caps on model requests, tool calls and tokens; timeouts; delegation one level deep (max 4
  questions); skills (3), drafts (2), organisations (8, only the ones you asked about), pages (3, only links a board
  returned or you gave) and job-board requests (24) per run; an agent that errors 3 times in a row for a student is paused
  for 15 minutes, and a paused intake is not acknowledged to the Coach Connector, so nothing is lost.
- **Cost:** an 8,000-token cap per model answer, 60,000 tokens per agent run (120,000 for a job-board search), daily
  token budgets per student and for the site (429 when reached), and an `AI_PAUSED` switch that stops every AI route at
  zero tokens. Tokens of a run cut off at a limit are still counted against the budget.
- **Facts:** quotes, names, links and ids are checked in code; invented actions are refused; emails and phone numbers are
  never stored; a substituted model's answer is rejected.

## Run it locally (about 5 minutes)

Needs **Python 3.12+** and **Node 20+**. Check with `python3 --version`: macOS's built-in `python3` is 3.9, too old,
so if yours is older than 3.12 use a newer one in step 2 (e.g. `python3.13 -m venv .venv`).

1. Put a `.env` with `PORTKEY_API_KEY=…` in this folder **or one folder above it** (see `.env.example`).
2. Install the backend:
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
5. Open **http://127.0.0.1:8020** and click **Try the demo**. (If port 8020 is busy, any free port works: use the
   same number in steps 4 and 5.)

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

## Connecting channels (Setup tab)

All free and read-only; nothing is ever sent from a student's accounts.

- **Coach Connector** (`connector/coach_connector.py`, Python standard library only, works with macOS's built-in
  `python3`). The student creates a connector key on the Setup tab (shown once, stored hashed, revocable), then:
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
  reason code only to `POST /api/connector/checked` (zero tokens; the full error stays in the Mac's log), so the Setup
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
| `AI_PAUSED` | no | Kill switch: `1` stops every AI route (503, zero tokens); the rest of the app keeps working. |

`.env` lookup order: the repo folder, then one folder above it (a third, workspace-only fallback two folders up is
documented in `backend/config.py`). Variables already set by the host (e.g. Render) win.

## Safety and limits (tested)

```bash
backend/.venv/bin/python -m pytest tests -v     # 72 tests, no API key needed, no tokens spent
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
backend/   FastAPI app (main.py), agents/ (strategist = Career coach, scout, network, inbox, guide, skills, runtime),
           skills/ (playbooks per agent), keeper.py (Records keeper), jobboards.py (public job-board APIs), prompts/, safety.py, merge.py,
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
