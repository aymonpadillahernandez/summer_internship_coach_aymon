"""Accounts for Summer Internship Coach: sign-up, sign-in, a one-click demo account, and "delete my data".

- Passwords are hashed with scrypt (stdlib) and a per-user salt; sessions are random tokens and only their SHA-256
  hashes are stored, so a copy of the database cannot be used to sign in. (Copied from the author's tracker.)
- "Try the demo" creates a fresh private account filled with a fictional student's data, so every visitor gets their
  own sandbox. Demo accounts and their data are deleted after DEMO_TTL_DAYS.
- Sign-in, sign-up and demo creation are rate-limited per IP, per account and overall.
- Every data route depends on require_user(); queries are always scoped to that user's id.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

import config
import db
from store import connect, insert_id

SESSION_COOKIE = "coach_session"
SESSION_DAYS = 30
MIN_PASSWORD = 8

_N, _R, _P = 2**14, 8, 1  # scrypt: ~16 MB and a few tens of ms per hash


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        test = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(test.hex(), digest)
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password(secrets.token_hex(8))  # unknown emails take as long as known ones

# ─── Rate limiting (per process) ────────────────────────────────────────
_ATTEMPTS: dict[str, deque] = defaultdict(deque)
_WINDOW = 15 * 60
_LIMITS = {"ip": 10, "who": 10, "all": 200}
_MAX_KEYS = 5000


def _hit(key: str, limit: int, now: float) -> bool:
    q = _ATTEMPTS[key]
    while q and now - q[0] > _WINDOW:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def rate_limit(request: Request, bucket: str, who: str = "") -> None:
    now = time.monotonic()
    if len(_ATTEMPTS) > _MAX_KEYS:
        for k in [k for k, q in _ATTEMPTS.items() if not q or now - q[-1] > _WINDOW]:
            del _ATTEMPTS[k]
        if len(_ATTEMPTS) > _MAX_KEYS:
            _ATTEMPTS.clear()
    ip = (request.client.host if request.client else "?")[:64]
    keys = [(f"{bucket}:all", _LIMITS["all"]), (f"{bucket}:ip:{ip}", _LIMITS["ip"])]
    if who:
        keys.append((f"{bucket}:who:{who.strip().lower()[:200]}", _LIMITS["who"]))
    if not all(_hit(k, limit, now) for k, limit in keys):
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")


# ─── Accounts and sessions ──────────────────────────────────────────────
def public(user) -> dict:
    return {"id": user["id"], "email": user["email"], "name": user["name"], "is_demo": bool(user["is_demo"])}


def _new_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (_iso(_now()),))
        conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                     (_sha(token), user_id, _iso(_now() + timedelta(days=SESSION_DAYS))))
    return token


def signup(email: str, name: str, password: str, code: str = "") -> tuple[dict, str]:
    if config.SIGNUP_CODE and not hmac.compare_digest(code.strip(), config.SIGNUP_CODE):
        raise HTTPException(403, "That sign-up code is not right.")
    if len(password) < MIN_PASSWORD:
        raise HTTPException(422, f"Use at least {MIN_PASSWORD} characters for the password.")
    email = email.strip().lower()
    with connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(409, "An account with this email already exists. Sign in instead.")
        user_id = insert_id(conn, "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
                            (email, name.strip()[:80], hash_password(password)))
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return public(user), _new_session(user_id)


def login(email: str, password: str) -> tuple[dict, str]:
    with connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ? AND is_demo = 0", (email.strip().lower(),)).fetchone()
    if not verify_password(password, user["password_hash"] if user else _DUMMY_HASH) or user is None:
        raise HTTPException(401, "Wrong email or password.")
    return public(user), _new_session(user["id"])


def create_demo() -> tuple[dict, str]:
    """A fresh private account with the fictional demo student's data."""
    import demo

    purge_old_demos()
    email = f"demo-{secrets.token_hex(6)}@demo.local"
    with connect() as conn:
        user_id = insert_id(conn, "INSERT INTO users (email, name, password_hash, is_demo) VALUES (?, ?, ?, 1)",
                            (email, "Demo student", hash_password(secrets.token_urlsafe(16))))
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    demo.seed(user_id)
    return public(user), _new_session(user_id)


def purge_old_demos() -> int:
    cutoff = _iso(_now() - timedelta(days=config.DEMO_TTL_DAYS))
    with connect() as conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM users WHERE is_demo = 1 AND created_at < ?", (cutoff,))]
    for user_id in ids:
        db.delete_user_data(user_id)
    return len(ids)


def logout(token: str | None) -> None:
    if token:
        with connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_sha(token),))


# ─── Cookies and the FastAPI dependency ─────────────────────────────────
def set_session_cookie(request: Request, response: Response, token: str) -> None:
    secure = request.url.scheme == "https"  # Render terminates TLS; uvicorn runs with --proxy-headers
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, secure=secure,
                        samesite="lax", path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def current_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    with connect() as conn:
        user = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?",
            (_sha(token), _iso(_now())),
        ).fetchone()
    return public(user) if user else None


def require_user(request: Request) -> dict:
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "Sign in to use the coach.")
    return user
