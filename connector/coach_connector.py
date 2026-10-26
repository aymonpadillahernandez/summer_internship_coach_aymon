#!/usr/bin/env python3
"""Summer Internship Coach · Coach Connector (free, runs on your own computer).

Connects YOUR Gmail and YOUR Messages (iMessage / SMS on a Mac) to your coach account, the same way the app's author
connected his own tracker. It is read-only: it never sends, deletes, moves or marks anything as read.

What leaves your computer: only emails and conversations that match your target organisations, your people or
recruiting words. They are filtered here, on your computer, before anything is sent, and they go only to your own
coach account (your connector key). Your Gmail app password stays in this Mac's Keychain.

  python3 coach_connector.py setup               # once: coach address, connector key, Gmail app password
  python3 coach_connector.py run --dry-run       # shows what would be sent, sends nothing
  python3 coach_connector.py run                 # sends new matching items from Gmail and Messages
  python3 coach_connector.py gmail --since 2026-10-01
  python3 coach_connector.py messages --dry-run

Standard library only (works with the python3 that comes with macOS). Settings live in ~/.coach_connector/.
"""

from __future__ import annotations

import argparse
import email
import glob
import imaplib
import json
import os
import re
import shutil
import sqlite3
import ssl
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email import policy
from email.utils import parseaddr
from getpass import getpass
from pathlib import Path

DEFAULT_COACH = "https://summer-internship-coach.onrender.com"
HOME = Path(os.environ.get("COACH_CONNECTOR_HOME") or Path.home() / ".coach_connector")  # settings folder
CONFIG, STATE = HOME / "config.json", HOME / "state.json"
KEYCHAIN_SERVICE = "Summer Internship Coach · Gmail app password"
BATCH_CHARS = 18_000  # one upload; the coach accepts up to 20,000 characters
EMAIL_BODY_CHARS = 3_000  # per email
MAX_EMAILS = 150  # per run, newest first
DEFAULT_DAYS = 30  # first run looks back this far
CHAT_DB = Path.home() / "Library/Messages/chat.db"
CONTACT_DBS = glob.glob(str(Path.home() / "Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb")) + \
    [str(Path.home() / "Library/Application Support/AddressBook/AddressBook-v22.abcddb")]
APPLE_EPOCH = 978307200
INTRO = re.compile(r"connecting you|connect you|introduc|\bintro\b|meet each other|you two|te presento|os presento", re.I)
AUTOMATED = re.compile(r"verification code|your code is|one-time code|reply stop|text stop|tracking number|out for delivery", re.I)


# ─── Small helpers ──────────────────────────────────────────────────────
def say(msg: str) -> None:
    print(msg, flush=True)


def norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def load(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def save(path: Path, data: dict) -> None:
    HOME.mkdir(mode=0o700, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))
    os.chmod(path, 0o600)


def tls() -> ssl.SSLContext:
    """Certificates: Python's own store, else the system bundle macOS ships (python.org builds may have none)."""
    ctx = ssl.create_default_context()
    if not ctx.cert_store_stats().get("x509_ca") and os.path.exists("/etc/ssl/cert.pem"):
        ctx.load_verify_locations("/etc/ssl/cert.pem")
    return ctx


def coach(method: str, path: str, cfg: dict, payload: dict | None = None) -> dict:
    """Call your coach account with your connector key."""
    url = cfg["base"].rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json", "User-Agent": "CoachConnector/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=150, context=tls()) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except ValueError:
            pass
        sys.exit(f"The coach answered HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach the coach at {cfg['base']} ({e.reason}). The free server may be waking up: try again in a minute.")


def keychain_get(account: str) -> str | None:
    if not shutil.which("security"):
        return None
    r = subprocess.run(["security", "find-generic-password", "-a", account, "-s", KEYCHAIN_SERVICE, "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip() or None if r.returncode == 0 else None


def keychain_set(account: str, secret: str) -> bool:
    if not shutil.which("security"):
        return False
    r = subprocess.run(["security", "add-generic-password", "-U", "-a", account, "-s", KEYCHAIN_SERVICE, "-w", secret],
                       capture_output=True, text=True)
    return r.returncode == 0


def batches(blocks: list[str]) -> list[list[str]]:
    out, cur, size = [], [], 0
    for b in blocks:
        b = b[:BATCH_CHARS]
        if cur and size + len(b) > BATCH_CHARS:
            out.append(cur)
            cur, size = [], 0
        cur.append(b)
        size += len(b) + 2
    return out + ([cur] if cur else [])


def topic_regex(ctx: dict) -> re.Pattern:
    words = ctx.get("keywords", []) + [o for o in ctx.get("organisations", []) if len(o) >= 3]
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True)) + r")\b", re.I)


def mentions_person(text: str, people: list[str]) -> bool:
    t = f" {norm(text)} "
    return any(f" {p} " in t for p in people)


# ─── Setup ──────────────────────────────────────────────────────────────
def setup() -> None:
    cfg = load(CONFIG, {})
    say("Summer Internship Coach · Coach Connector setup\n")
    base = input(f"Coach address [{cfg.get('base', DEFAULT_COACH)}]: ").strip() or cfg.get("base", DEFAULT_COACH)
    say("Connector key: create one in the coach on the Connect page (it starts with sic_).")
    key = getpass("Paste your connector key (hidden): ").strip() or cfg.get("key", "")
    if not key.startswith("sic_"):
        sys.exit("That does not look like a connector key (it starts with sic_).")
    cfg.update({"base": base, "key": key})
    ctx = coach("GET", "/api/connector/context", cfg)
    say(f"Connected to your coach: {len(ctx.get('organisations', []))} organisations and {len(ctx.get('people', []))} people "
        "will be used to filter on this computer.\n")
    address = input(f"Gmail address to connect (Enter to skip) [{cfg.get('gmail', {}).get('address', '')}]: ").strip() \
        or cfg.get("gmail", {}).get("address", "")
    if address:
        say("Gmail app password: Google Account > Security > 2-Step Verification (on) > App passwords > create one.")
        pw = getpass("Paste the 16-character app password (hidden, Enter to keep the saved one): ").replace(" ", "").strip()
        gmail = {"address": address}
        if pw:
            if keychain_set(address, pw):
                gmail["password_in"] = "keychain"
                say("Saved in this Mac's Keychain.")
            else:
                gmail.update({"password_in": "file", "password": pw})
                say("No Keychain here: saved in ~/.coach_connector/config.json, readable only by you.")
        else:
            gmail.update({k: v for k, v in cfg.get("gmail", {}).items() if k != "address"})
        cfg["gmail"] = gmail
    cfg["messages"] = sys.platform == "darwin" and input("Connect Messages (iMessage / SMS) on this Mac? [Y/n]: ").strip().lower() != "n"
    save(CONFIG, cfg)
    say("\nDone. Try:  python3 coach_connector.py run --dry-run")


# ─── Gmail (IMAP, read-only) ────────────────────────────────────────────
def gmail_password(g: dict) -> str:
    pw = keychain_get(g["address"]) if g.get("password_in") == "keychain" else g.get("password")
    if not pw:
        sys.exit("No Gmail app password saved. Run: python3 coach_connector.py setup")
    return pw


def all_mail_folder(imap: imaplib.IMAP4_SSL) -> str:
    """The 'All Mail' folder whatever the Gmail language (it carries the \\All flag)."""
    _, folders = imap.list()
    for line in folders or []:
        text = line.decode(errors="replace")
        if "\\All" in text:
            return text.rsplit(' "/" ', 1)[-1]
    return "INBOX"


def body_of(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    text = part.get_content()
    if part.get_content_type() == "text/html":
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def gmail(cfg: dict, ctx: dict, since: str | None, dry_run: bool) -> None:
    g = cfg.get("gmail")
    if not g:
        say("Gmail is not set up (run setup to add it).")
        return
    state = load(STATE, {})
    seen = set(state.get("gmail_seen", []))
    start = since or state.get("gmail_since") or (date.today() - timedelta(days=DEFAULT_DAYS)).isoformat()
    topic, people = topic_regex(ctx), [norm(p) for p in ctx.get("people", []) if len(p) >= 4]
    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=tls())
    try:
        imap.login(g["address"], gmail_password(g))
    except imaplib.IMAP4.error:
        sys.exit("Gmail refused the sign-in. Check the address and create a new app password (2-Step Verification must be on).")
    imap.select(all_mail_folder(imap), readonly=True)  # read-only: nothing is changed or marked as read
    _, data = imap.uid("search", None, f'(SINCE {datetime.fromisoformat(start):%d-%b-%Y})')
    uids = (data[0] or b"").split()[-MAX_EMAILS:][::-1]
    blocks, picked, newly_seen = [], [], []
    for uid in uids:
        _, raw = imap.uid("fetch", uid, "(BODY.PEEK[])")  # PEEK: the email stays unread
        if not raw or not isinstance(raw[0], tuple):
            continue
        msg = email.message_from_bytes(raw[0][1], policy=policy.default)
        mid = str(msg.get("Message-ID", uid.decode()))
        if mid in seen:
            continue
        newly_seen.append(mid)
        name, addr = parseaddr(str(msg.get("From", "")))
        subject, body = str(msg.get("Subject", "")), body_of(msg)
        text = f"{name} {addr} {subject} {body[:EMAIL_BODY_CHARS]}"
        bulk = bool(msg.get("List-Unsubscribe"))
        person = mentions_person(f"{name} {body[:EMAIL_BODY_CHARS]}", people)
        if AUTOMATED.search(text) or (bulk and not person):
            continue  # codes, deliveries, newsletters (unless they involve one of your people)
        if not (person or topic.search(text)):
            continue
        picked.append(subject or "(no subject)")
        blocks.append(f"From: {name or addr.split('@')[0]}\nDate: {msg.get('Date', '')}\nSubject: {subject}\n\n{body[:EMAIL_BODY_CHARS]}")
    imap.logout()
    say(f"Gmail: {len(uids)} emails since {start} checked, {len(blocks)} match your search.")
    for s in picked[:20]:
        say(f"  · {s[:90]}")
    if dry_run:
        say("Dry run: nothing was sent.")
        return
    for group in batches(blocks):
        r = coach("POST", "/api/connector/intake", cfg, {"channel": "gmail", "text": "\n\n---\n\n".join(group),
                                                          "label": f"Gmail · {len(group)} emails", "items": len(group)})
        say(f"  sent {len(group)} emails → {r.get('saved')} (shield {r.get('shield', 0)}, rejected {r.get('rejected', 0)})")
    state["gmail_seen"] = (list(seen) + newly_seen)[-5000:]
    state["gmail_since"] = (date.today() - timedelta(days=2)).isoformat()  # small overlap, duplicates are skipped
    save(STATE, state)


# ─── Messages (iMessage / SMS on a Mac, read-only) ──────────────────────
def read_only(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def norm_handle(h: str) -> str:
    return h.strip().lower() if "@" in h else re.sub(r"\D", "", h)[-10:]


def contact_names() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in CONTACT_DBS:
        try:
            con = read_only(path)
            people = {pk: f"{f or ''} {l or ''}".strip() for pk, f, l in con.execute("SELECT Z_PK, ZFIRSTNAME, ZLASTNAME FROM ZABCDRECORD")}
            for table, col in (("ZABCDPHONENUMBER", "ZFULLNUMBER"), ("ZABCDEMAILADDRESS", "ZADDRESS")):
                for owner, value in con.execute(f"SELECT ZOWNER, {col} FROM {table}"):
                    if value and people.get(owner):
                        out[norm_handle(value)] = people[owner]
        except sqlite3.Error:
            continue
    return out


def label(handle: str, names: dict[str, str]) -> str:
    """A saved name, or a masked handle: phone numbers and email addresses never leave this computer."""
    if names.get(norm_handle(handle)):
        return names[norm_handle(handle)]
    digits = re.sub(r"\D", "", handle)
    return f"number ending {digits[-4:]}" if "@" not in handle else "an email contact"


def body_text(text: str | None, blob: bytes | None) -> str:
    """Newer macOS keeps the text inside attributedBody (a serialized NSAttributedString)."""
    if text:
        return text
    if not blob or b"NSString" not in blob:
        return ""
    rest = blob.split(b"NSString", 1)[1][5:]
    if not rest:
        return ""
    length, start = (int.from_bytes(rest[1:3], "little"), 3) if rest[0] == 0x81 else (rest[0], 1)
    return rest[start:start + length].decode("utf-8", "replace")


def messages(cfg: dict, ctx: dict, since: str | None, dry_run: bool) -> None:
    if not cfg.get("messages"):
        say("Messages is not set up (run setup on a Mac to add it).")
        return
    state = load(STATE, {})
    start = since or state.get("messages_since") or (date.today() - timedelta(days=DEFAULT_DAYS)).isoformat()
    try:
        con = read_only(str(CHAT_DB))
        con.execute("SELECT 1 FROM message LIMIT 1")
    except sqlite3.Error:
        sys.exit("Messages can't be read yet. Open System Settings > Privacy & Security > Full Disk Access, turn it on for "
                 "Terminal (or the app you run this from), quit and reopen it, then try again.")
    names = contact_names()
    topic, people = topic_regex(ctx), [norm(p) for p in ctx.get("people", []) if len(p) >= 4]
    oldest = int((datetime.fromisoformat(start).timestamp() - APPLE_EPOCH) * 1e9)
    handles = dict(con.execute("SELECT ROWID, id FROM handle"))
    members: dict[int, list[str]] = {}
    for chat_id, handle_id in con.execute("SELECT chat_id, handle_id FROM chat_handle_join"):
        if handle_id in handles:
            members.setdefault(chat_id, []).append(handles[handle_id])
    convs: dict[int, list[tuple[str, str, str]]] = {}
    rows = con.execute("""SELECT cmj.chat_id, m.date, m.is_from_me, m.handle_id, m.text, m.attributedBody
                          FROM message m JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                          WHERE m.date >= ? ORDER BY m.date""", (oldest,))
    for chat_id, when, mine, handle_id, text, blob in rows:
        body = body_text(text, blob).replace("￼", "").strip()
        if body:
            stamp = datetime.fromtimestamp(when / 1e9 + APPLE_EPOCH, timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
            who = "You" if mine else label(handles.get(handle_id, ""), names)
            convs.setdefault(chat_id, []).append((stamp, who, body))
    blocks, picked = [], []
    for chat_id, msgs in convs.items():
        who = [label(h, names) for h in members.get(chat_id, [])]
        text = "\n".join(b for _, _, b in msgs)
        on_list = mentions_person(" ".join(who), people)
        if not on_list and AUTOMATED.search(text):
            continue
        if not (on_list or topic.search(text) or INTRO.search(text)):
            continue
        title = ", ".join(who) or "a conversation"
        picked.append(f"{title} ({len(msgs)} messages)")
        blocks.append(f"Messages with {title}\n" + "\n".join(f"[{s}] {w}: {b}" for s, w, b in msgs[-80:]))
    say(f"Messages: {len(convs)} conversations since {start} checked, {len(blocks)} match your search.")
    for p in picked[:20]:
        say(f"  · {p[:90]}")
    if dry_run:
        say("Dry run: nothing was sent.")
        return
    for group in batches(blocks):
        r = coach("POST", "/api/connector/intake", cfg, {"channel": "imessage", "text": "\n\n---\n\n".join(group),
                                                          "label": f"Messages · {len(group)} conversations", "items": len(group)})
        say(f"  sent {len(group)} conversations → {r.get('saved')} (shield {r.get('shield', 0)}, rejected {r.get('rejected', 0)})")
    state["messages_since"] = (date.today() - timedelta(days=2)).isoformat()
    save(STATE, state)


# ─── Command line ───────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["setup", "run", "gmail", "messages"])
    ap.add_argument("--since", help="YYYY-MM-DD: look back to this date (default: since the last run, or 30 days)")
    ap.add_argument("--dry-run", action="store_true", help="show what would be sent; send nothing")
    args = ap.parse_args()
    if args.since:
        try:
            date.fromisoformat(args.since)
        except ValueError:
            sys.exit("--since must look like 2026-10-01")
    if args.command == "setup":
        setup()
        return 0
    cfg = load(CONFIG, {})
    if not cfg.get("key"):
        sys.exit("Not set up yet. Run: python3 coach_connector.py setup")
    ctx = coach("GET", "/api/connector/context", cfg)
    if args.command in ("run", "gmail"):
        gmail(cfg, ctx, args.since, args.dry_run)
    if args.command in ("run", "messages"):
        messages(cfg, ctx, args.since, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
