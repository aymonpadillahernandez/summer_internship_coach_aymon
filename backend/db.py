"""Storage for Summer Internship Coach: local SQLite, or Postgres (Supabase) when DATABASE_URL is set.

Multi-user from the ground up: every data table has user_id, and every query here takes the user's id, so one
student can never read or change another student's rows (tests/test_safety.py checks it).
The opportunity, contact, event and lead tables keep the shape of the author's internship tracker, so the board,
cards and action plan copied from it work unchanged. New here: profiles, agent_runs (one per request, with the
agent trace), model_runs (one per agent run, with real token counts) and plans (the strategist's latest ranking).
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets

from store import connect, insert_id, is_postgres

# Opportunity pipeline, in order.
STAGES = [
    {"key": "not_started", "label": "Not started"},
    {"key": "wip", "label": "WIP"},
    {"key": "applied", "label": "Applied"},
    {"key": "interview", "label": "Interview"},
    {"key": "offer", "label": "Offer"},
    {"key": "rejected", "label": "Rejected"},
]
STAGE_KEYS = [s["key"] for s in STAGES]

# Networking pipeline, in order.
NETWORK_STAGES = [
    {"key": "to_contact", "label": "To contact"},
    {"key": "reached_out", "label": "Reached out"},
    {"key": "call_booked", "label": "Call booked"},
    {"key": "follow_up", "label": "Follow up · 2 weeks"},
    {"key": "keep_warm", "label": "Keep warm"},
]
NETWORK_KEYS = [s["key"] for s in NETWORK_STAGES]
FOLLOW_UP_DAYS = 14

DATA_TABLES = ["events", "leads", "contacts", "applications", "actions_done", "profiles", "plans", "model_runs",
               "agent_runs", "connector_syncs", "connector_keys", "sessions"]  # deletion order (children first)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    is_demo       INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL
);
-- The student's own short profile (goals, background, languages): context for the strategist and call prep.
CREATE TABLE IF NOT EXISTS profiles (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    text       TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS applications (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company           TEXT NOT NULL,
    role              TEXT NOT NULL DEFAULT '',
    formal_internship TEXT NOT NULL DEFAULT 'Not clear',
    mba_eligible      TEXT NOT NULL DEFAULT 'Not clear',
    deadline          TEXT NOT NULL DEFAULT '',
    location          TEXT NOT NULL DEFAULT '',
    priority          TEXT NOT NULL DEFAULT '',
    context           TEXT NOT NULL DEFAULT '',
    stakeholders      TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'not_started',
    last_contact      TEXT,
    follow_up_days    INTEGER NOT NULL DEFAULT 7,
    notes             TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    origin            TEXT NOT NULL DEFAULT 'manual',
    source_url        TEXT NOT NULL DEFAULT '',
    added_on          TEXT,
    fit               TEXT,
    fit_reason        TEXT,
    verified_status   TEXT,
    verified_summary  TEXT,
    verified_opens    TEXT,
    verified_deadline TEXT,
    verified_url      TEXT,
    verified_evidence TEXT,
    verified_on       TEXT,
    verified_fit      TEXT,
    not_interested_at TEXT,
    door_paths        TEXT,
    door_paths_at     TEXT
);
CREATE INDEX IF NOT EXISTS applications_user ON applications (user_id);
CREATE TABLE IF NOT EXISTS contacts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    affiliation      TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'to_contact',
    last_contact     TEXT,
    how_met          TEXT NOT NULL DEFAULT '',
    next_step        TEXT,
    next_date        TEXT,
    application_ids  TEXT NOT NULL DEFAULT '[]',
    network_ids      TEXT NOT NULL DEFAULT '[]',
    source           TEXT NOT NULL DEFAULT 'manual',
    notes            TEXT NOT NULL DEFAULT '',
    status_manual_at TEXT,
    not_interested_at TEXT,
    UNIQUE (user_id, name)
);
-- Dated, evidence-backed facts: each keeps the exact quote it came from.
CREATE TABLE IF NOT EXISTS events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    contact_id        INTEGER REFERENCES contacts(id) ON DELETE CASCADE,
    application_id    INTEGER REFERENCES applications(id) ON DELETE CASCADE,
    date              TEXT NOT NULL,
    text              TEXT NOT NULL,
    evidence          TEXT NOT NULL DEFAULT '',
    source_message_id TEXT NOT NULL DEFAULT '',
    source_subject    TEXT NOT NULL DEFAULT '',
    origin            TEXT NOT NULL DEFAULT 'note'
);
CREATE UNIQUE INDEX IF NOT EXISTS events_dedupe
    ON events (user_id, IFNULL(contact_id, 0), IFNULL(application_id, 0), source_message_id, text);
CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    application_ids TEXT NOT NULL DEFAULT '[]',
    kind            TEXT NOT NULL DEFAULT 'tip',
    date            TEXT NOT NULL,
    when_text       TEXT NOT NULL DEFAULT '',
    summary         TEXT NOT NULL,
    posted_by       TEXT NOT NULL DEFAULT '',
    evidence        TEXT NOT NULL DEFAULT '',
    url             TEXT NOT NULL DEFAULT '',
    origin          TEXT NOT NULL DEFAULT 'posting',
    source_ref      TEXT NOT NULL,
    source_subject  TEXT NOT NULL DEFAULT '',
    UNIQUE (user_id, source_ref)
);
CREATE TABLE IF NOT EXISTS actions_done (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key     TEXT NOT NULL,
    done_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, key)
);
-- One row per request that used AI (intake, plan, chat), with the step-by-step agent trace.
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id      TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    seconds     REAL,
    trace       TEXT NOT NULL DEFAULT '[]',
    summary     TEXT NOT NULL DEFAULT ''
);
-- One row per agent run (one agent working on one request), with the token counts the model reported.
CREATE TABLE IF NOT EXISTS model_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT NOT NULL,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent            TEXT NOT NULL,
    model            TEXT NOT NULL DEFAULT '',
    requests         INTEGER NOT NULL DEFAULT 0,
    input_tokens     INTEGER NOT NULL DEFAULT 0,
    cached_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens    INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    seconds          REAL NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'ok',
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS model_runs_user ON model_runs (user_id, created_at);
-- The strategist's latest ranking for each user.
CREATE TABLE IF NOT EXISTS plans (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    run_id     TEXT NOT NULL,
    plan       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Keys for the Coach Connector, a script the student runs on their own computer (Gmail, iMessage). Only the
-- SHA-256 hash of each key is stored; the student sees the key once.
CREATE TABLE IF NOT EXISTS connector_keys (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash     TEXT NOT NULL UNIQUE,
    label        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at TEXT,
    revoked_at   TEXT
);
-- What the connector last sent, per channel (shown on the Connect page).
CREATE TABLE IF NOT EXISTS connector_syncs (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel   TEXT NOT NULL,
    synced_at TEXT NOT NULL DEFAULT (datetime('now')),
    items     INTEGER NOT NULL DEFAULT 0,
    run_id    TEXT NOT NULL DEFAULT '',
    summary   TEXT NOT NULL DEFAULT '',
    ok        INTEGER NOT NULL DEFAULT 1,  -- 0: the last check could not read the channel (e.g. no Full Disk Access)
    auto_minutes INTEGER,                  -- set when the connector runs on its own schedule
    PRIMARY KEY (user_id, channel)
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_PG_NOW = "to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')"


def pg_schema() -> str:
    """The same schema for Postgres, plus row-level security on every table: Supabase's Data API then sees
    nothing, while the app (the table owner) is not restricted."""
    s = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY").replace("REAL", "DOUBLE PRECISION")
    s = s.replace("(datetime('now'))", f"({_PG_NOW})").replace("IFNULL(", "COALESCE(")
    tables = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA)
    return s + "\n".join(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;" for t in tables)


ADDED_COLUMNS = {"applications": {"door_paths": "TEXT", "door_paths_at": "TEXT"},  # added after the first deploy
                 "connector_syncs": {"ok": "INTEGER NOT NULL DEFAULT 1", "auto_minutes": "INTEGER"}}


def init_db() -> None:
    with connect() as conn:
        conn.executescript(pg_schema() if is_postgres() else SCHEMA)
        for table, cols in ADDED_COLUMNS.items():  # databases created before a column existed get it in place
            for col, ddl in cols.items():
                if is_postgres():
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {ddl}")
                elif col not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _loads(row: dict, *cols: str) -> dict:
    for c in cols:
        row[c] = json.loads(row[c]) if isinstance(row.get(c), str) else (row.get(c) or [])
    return row


# ─── Profiles ───────────────────────────────────────────────────────────
def get_profile(user_id: int) -> str:
    with connect() as conn:
        row = conn.execute("SELECT text FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
    return row[0] if row else ""


def set_profile(user_id: int, text: str) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO profiles (user_id, text, updated_at) VALUES (?, ?, datetime('now'))
               ON CONFLICT(user_id) DO UPDATE SET text = excluded.text, updated_at = excluded.updated_at""",
            (user_id, text),
        )


# ─── Opportunities ──────────────────────────────────────────────────────
def list_applications(user_id: int) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM applications WHERE user_id = ? ORDER BY id", (user_id,))]


def get_application(user_id: int, app_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM applications WHERE id = ? AND user_id = ?", (app_id, user_id)).fetchone()
    return dict(row) if row else None


def update_status(user_id: int, app_id: int, status: str) -> dict | None:
    with connect() as conn:
        conn.execute("UPDATE applications SET status = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
                     (status, app_id, user_id))
    return get_application(user_id, app_id)


def set_not_interested(user_id: int, table: str, row_id: int, not_interested: bool) -> bool:
    assert table in ("applications", "contacts")
    value = "date('now')" if not_interested else "NULL"
    with connect() as conn:
        cur = conn.execute(f"UPDATE {table} SET not_interested_at = {value} WHERE id = ? AND user_id = ?", (row_id, user_id))
        return cur.rowcount > 0


# ─── Contacts and their events ──────────────────────────────────────────
def list_contacts(user_id: int) -> list[dict]:
    with connect() as conn:
        contacts = [dict(r) for r in conn.execute("SELECT * FROM contacts WHERE user_id = ? ORDER BY name", (user_id,))]
        events = [dict(r) for r in conn.execute(
            "SELECT * FROM events WHERE user_id = ? AND contact_id IS NOT NULL ORDER BY date DESC, id DESC", (user_id,))]
    by_contact: dict[int, list[dict]] = {}
    for e in events:
        by_contact.setdefault(e["contact_id"], []).append(e)
    for c in contacts:
        _loads(c, "application_ids", "network_ids")
        c["events"] = by_contact.get(c["id"], [])
    return contacts


def get_contact(user_id: int, contact_id: int) -> dict | None:
    return next((c for c in list_contacts(user_id) if c["id"] == contact_id), None)


def update_contact(user_id: int, contact_id: int, status: str | None = None, last_contact: str | None = None) -> dict | None:
    with connect() as conn:
        if status is not None:
            conn.execute("UPDATE contacts SET status = ?, status_manual_at = date('now') WHERE id = ? AND user_id = ?",
                         (status, contact_id, user_id))
        if last_contact is not None:
            conn.execute("UPDATE contacts SET last_contact = ? WHERE id = ? AND user_id = ?",
                         (last_contact or None, contact_id, user_id))
    return get_contact(user_id, contact_id)


# ─── Leads ──────────────────────────────────────────────────────────────
def list_leads(user_id: int) -> list[dict]:
    with connect() as conn:
        leads = [dict(r) for r in conn.execute("SELECT * FROM leads WHERE user_id = ? ORDER BY date DESC, id DESC", (user_id,))]
    return [_loads(lead, "application_ids") for lead in leads]


# ─── What each opportunity card shows ───────────────────────────────────
def board(user_id: int) -> list[dict]:
    """Opportunities with their activity, linked people and leads (the tracker's card shape)."""
    apps = list_applications(user_id)
    contacts = list_contacts(user_id)
    leads = list_leads(user_id)
    with connect() as conn:
        activity_rows = [dict(r) for r in conn.execute(
            """SELECT e.*, c.name AS contact, c.status AS contact_status
               FROM events e LEFT JOIN contacts c ON c.id = e.contact_id
               WHERE e.user_id = ? AND e.application_id IS NOT NULL ORDER BY e.date DESC, e.id ASC""", (user_id,))]
    activity: dict[int, list[dict]] = {}
    for r in activity_rows:
        activity.setdefault(r["application_id"], []).append(r)
    network: dict[int, list[dict]] = {}
    for c in contacts:
        summary = {k: c[k] for k in ("id", "name", "affiliation", "status", "next_step", "next_date", "last_contact")}
        for app_id in c["network_ids"]:
            network.setdefault(app_id, []).append(summary)
    by_app: dict[int, list[dict]] = {}
    for lead in leads:
        for app_id in lead["application_ids"]:
            by_app.setdefault(app_id, []).append(lead)
    return [{**a, "logo": None, "door_paths": json.loads(a["door_paths"]) if a.get("door_paths") else None,
             "activity": activity.get(a["id"], []), "network": network.get(a["id"], []),
             "leads": by_app.get(a["id"], []), "found": []} for a in apps]


def save_doors(user_id: int, app_id: int, result: dict) -> None:
    with connect() as conn:
        conn.execute("UPDATE applications SET door_paths = ?, door_paths_at = datetime('now') WHERE id = ? AND user_id = ?",
                     (json.dumps(result, ensure_ascii=False), app_id, user_id))


# ─── Action plan ticks ──────────────────────────────────────────────────
def done_actions(user_id: int) -> list[str]:
    with connect() as conn:
        return [r[0] for r in conn.execute("SELECT key FROM actions_done WHERE user_id = ?", (user_id,))]


def set_action_done(user_id: int, key: str, done: bool) -> None:
    with connect() as conn:
        if done:
            conn.execute("INSERT OR IGNORE INTO actions_done (user_id, key) VALUES (?, ?)", (user_id, key))
        else:
            conn.execute("DELETE FROM actions_done WHERE user_id = ? AND key = ?", (user_id, key))


# ─── Agent runs, token usage and plans ──────────────────────────────────
def start_run(run_id: str, user_id: int, kind: str) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO agent_runs (run_id, user_id, kind) VALUES (?, ?, ?)", (run_id, user_id, kind))


def finish_run(run_id: str, status: str, seconds: float, trace: list[dict], summary: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE agent_runs SET status = ?, seconds = ?, trace = ?, summary = ? WHERE run_id = ?",
                     (status, round(seconds, 2), json.dumps(trace, ensure_ascii=False), summary[:500], run_id))


def record_model_run(row: dict) -> None:
    cols = ["run_id", "user_id", "agent", "model", "requests", "input_tokens", "cached_tokens", "output_tokens",
            "reasoning_tokens", "seconds", "status"]
    with connect() as conn:
        conn.execute(f"INSERT INTO model_runs ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                     [row[c] for c in cols])


def tokens_today(user_id: int | None = None) -> int:
    """Tokens used since midnight UTC, by one user or (None) by the whole site."""
    sql = "SELECT IFNULL(SUM(input_tokens + output_tokens), 0) FROM model_runs WHERE created_at >= date('now')"
    with connect() as conn:
        if user_id is None:
            return int(conn.execute(sql).fetchone()[0])
        return int(conn.execute(sql + " AND user_id = ?", (user_id,)).fetchone()[0])


def list_runs(user_id: int, limit: int = 30) -> list[dict]:
    with connect() as conn:
        runs = [dict(r) for r in conn.execute(
            "SELECT run_id, kind, status, started_at, seconds, summary FROM agent_runs WHERE user_id = ? "
            "ORDER BY started_at DESC LIMIT ?", (user_id, limit))]
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM model_runs WHERE user_id = ? ORDER BY id", (user_id,))]
    by_run: dict[str, list[dict]] = {}
    for r in rows:
        by_run.setdefault(r["run_id"], []).append(r)
    for run in runs:
        run["agents"] = by_run.get(run["run_id"], [])
    return runs


def get_run(user_id: int, run_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs WHERE run_id = ? AND user_id = ?", (run_id, user_id)).fetchone()
        if row is None:
            return None
        agents = [dict(r) for r in conn.execute(
            "SELECT * FROM model_runs WHERE run_id = ? AND user_id = ? ORDER BY id", (run_id, user_id))]
    run = dict(row)
    run["trace"] = json.loads(run["trace"])
    run["agents"] = agents
    return run


def save_plan(user_id: int, run_id: str, plan: dict) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO plans (user_id, run_id, plan, created_at) VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(user_id) DO UPDATE SET run_id = excluded.run_id, plan = excluded.plan,
               created_at = excluded.created_at""",
            (user_id, run_id, json.dumps(plan, ensure_ascii=False)),
        )


def latest_plan(user_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT run_id, plan, created_at FROM plans WHERE user_id = ?", (user_id,)).fetchone()
    return {"run_id": row["run_id"], "created_at": row["created_at"], **json.loads(row["plan"])} if row else None


# ─── Accounts: delete everything a user owns ────────────────────────────
def delete_user_data(user_id: int, delete_account: bool = True) -> None:
    with connect() as conn:
        for table in DATA_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        if delete_account:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


# ─── Coach Connector keys and syncs ─────────────────────────────────────
def create_connector_key(user_id: int, label: str) -> tuple[str, int]:
    """Returns the raw key (shown to the student once) and its id; only the hash is stored."""
    raw = "sic_" + secrets.token_urlsafe(32)
    with connect() as conn:
        key_id = insert_id(conn, "INSERT INTO connector_keys (user_id, key_hash, label) VALUES (?, ?, ?)",
                           (user_id, hashlib.sha256(raw.encode()).hexdigest(), label[:80]))
    return raw, key_id


def list_connector_keys(user_id: int) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, label, created_at, last_used_at, revoked_at FROM connector_keys WHERE user_id = ? ORDER BY id DESC",
            (user_id,))]


def revoke_connector_key(user_id: int, key_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("UPDATE connector_keys SET revoked_at = datetime('now') WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
                           (key_id, user_id))
        return cur.rowcount > 0


def user_for_connector_key(raw: str) -> tuple[dict, int] | None:
    """(user, key id) for a valid, unrevoked key; also records when it was last used."""
    with connect() as conn:
        row = conn.execute(
            """SELECT u.*, k.id AS key_id FROM connector_keys k JOIN users u ON u.id = k.user_id
               WHERE k.key_hash = ? AND k.revoked_at IS NULL""", (hashlib.sha256(raw.encode()).hexdigest(),)).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE connector_keys SET last_used_at = datetime('now') WHERE id = ?", (row["key_id"],))
    return dict(row), row["key_id"]


def record_sync(user_id: int, channel: str, items: int, run_id: str, summary: str) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO connector_syncs (user_id, channel, synced_at, items, run_id, summary)
               VALUES (?, ?, datetime('now'), ?, ?, ?)
               ON CONFLICT(user_id, channel) DO UPDATE SET synced_at = excluded.synced_at, items = excluded.items,
               run_id = excluded.run_id, summary = excluded.summary""",
            (user_id, channel, items, run_id, summary[:300]))


def record_check(user_id: int, channel: str, ok: bool, sent: int, summary: str, auto_minutes: int | None) -> None:
    """One connector run's result for a channel (counts only): shows whether auto-sync is on and working."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO connector_syncs (user_id, channel, synced_at, items, run_id, summary, ok, auto_minutes)
               VALUES (?, ?, datetime('now'), ?, '', ?, ?, ?)
               ON CONFLICT(user_id, channel) DO UPDATE SET synced_at = excluded.synced_at, items = excluded.items,
               summary = excluded.summary, ok = excluded.ok, auto_minutes = excluded.auto_minutes""",
            (user_id, channel, sent, summary[:300], 1 if ok else 0, auto_minutes))


def stop_auto_sync(user_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE connector_syncs SET auto_minutes = NULL WHERE user_id = ?", (user_id,))


def list_syncs(user_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT channel, synced_at, items, summary, ok, auto_minutes FROM connector_syncs WHERE user_id = ?",
                            (user_id,))
        return [{**dict(r), "ok": bool(r["ok"])} for r in rows]


def new_id(conn, sql: str, params: tuple | list) -> int:
    return insert_id(conn, sql, params)
