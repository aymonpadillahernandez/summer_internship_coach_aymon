"""One small database layer for local SQLite and production Postgres (Supabase).

Set DATABASE_URL to a postgresql:// URL to use Postgres; otherwise the local SQLite file data/coach.db is used
(created on first start and filled with nothing but the accounts people make, plus demo accounts).

SQL is written once, SQLite-style, with ? placeholders. For Postgres it is translated:
? -> %s, INSERT OR IGNORE -> ON CONFLICT DO NOTHING, datetime('now') / date('now') -> text timestamps in the same
format, IFNULL -> COALESCE. Rows behave like sqlite3.Row: row["col"] and row[0] both work, dict(row) gives a dict.
Copied from the author's internship tracker (store.py) and pointed at this app's own database only.
"""

from __future__ import annotations

import atexit
import os
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

import config  # loads .env (repo, then the folder above)

SQLITE_PATH = config.ROOT / "data" / "coach.db"


def _database_url() -> str:
    return (os.getenv("DATABASE_URL") or "").strip()


def is_postgres() -> bool:
    return _database_url().startswith(("postgres://", "postgresql://"))


# ─── Postgres translation ───────────────────────────────────────────────
_NOW_TS = "to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')"
_NOW_DATE = "to_char((now() at time zone 'utc')::date, 'YYYY-MM-DD')"


def translate(sql: str) -> str:
    """SQLite-style SQL -> Postgres. Only the constructs this app uses."""
    s = sql.replace("datetime('now')", _NOW_TS).replace("date('now')", _NOW_DATE).replace("IFNULL(", "COALESCE(")
    if re.search(r"\bINSERT OR IGNORE INTO\b", s):
        s = re.sub(r"\bINSERT OR IGNORE INTO\b", "INSERT INTO", s).rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return s.replace("%", "%%").replace("?", "%s")


class Row(dict):
    """A dict that also answers row[0], like sqlite3.Row."""

    __slots__ = ("_values",)

    def __init__(self, names: list[str], values: tuple):
        super().__init__(zip(names, values))
        self._values = values

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)

    def keys(self):  # sqlite3.Row compatibility
        return list(super().keys())


def _row_factory(cursor):
    names = [c.name for c in cursor.description] if cursor.description else []
    return lambda values: Row(names, values)


_pool = None


def _pg_pool():
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool

        # prepare_threshold=None: Supabase's pooler does not keep prepared statements.
        # check + max_idle: Supabase closes idle connections, so each one is tested before use.
        _pool = ConnectionPool(
            _database_url(),
            min_size=1,
            max_size=5,
            max_idle=60,
            check=ConnectionPool.check_connection,
            kwargs={"row_factory": _row_factory, "prepare_threshold": None},
            open=True,
        )
        atexit.register(_pool.close)
    return _pool


class _PgConn:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql: str, params: tuple | list = ()):
        return self.raw.execute(translate(sql), tuple(params))

    def executemany(self, sql: str, seq):
        with self.raw.cursor() as cur:
            cur.executemany(translate(sql), [tuple(p) for p in seq])
            return cur

    def executescript(self, script: str) -> None:
        for statement in (s.strip() for s in _split_sql(script)):
            if statement:
                self.raw.execute(statement)


def _split_sql(script: str) -> list[str]:
    no_comments = "\n".join(line for line in script.splitlines() if not line.strip().startswith("--"))
    return no_comments.split(";")


@contextmanager
def connect() -> Iterator[Any]:
    """`with connect() as conn:` commits on success and rolls back on error (both backends)."""
    if is_postgres():
        with _pg_pool().connection() as raw:  # the pool commits / rolls back for us
            yield _PgConn(raw)
        return
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def insert_id(conn, sql: str, params: tuple | list) -> int:
    """Run an INSERT and return the new row's id on both backends."""
    if is_postgres():
        return conn.execute(sql.rstrip().rstrip(";") + " RETURNING id", params).fetchone()[0]
    return conn.execute(sql, params).lastrowid
