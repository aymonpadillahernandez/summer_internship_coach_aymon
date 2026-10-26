#!/usr/bin/env python3
"""Summer Internship Coach · Coach Connector (free, runs on your own computer).

Connects YOUR Gmail, YOUR Messages (iMessage / SMS) and YOUR WhatsApp Desktop on a Mac to your coach account, the
same way the app's author connected his own tracker. It is read-only: it never sends, deletes, moves or marks anything
as read, and it never connects to WhatsApp (it reads the WhatsApp Desktop app's own data on this Mac).

What leaves your computer: only emails and conversations that match your target organisations, your people or
recruiting words. They are filtered here, on your computer, before anything is sent, and they go only to your own
coach account (your connector key). Your Gmail app password stays in this Mac's Keychain.

  python3 coach_connector.py setup               # once: coach address, connector key, Gmail app password
  python3 coach_connector.py run --dry-run       # shows what would be sent, sends nothing
  python3 coach_connector.py run                 # sends new matching items from Gmail, Messages and WhatsApp
  python3 coach_connector.py schedule            # auto-sync: runs on its own every 30 minutes while this Mac is awake
  python3 coach_connector.py status              # is auto-sync on, and what did the last run check?
  python3 coach_connector.py unschedule          # stops auto-sync
  python3 coach_connector.py gmail --since 2026-10-01
  python3 coach_connector.py whatsapp --dry-run

Standard library only (works with the python3 that comes with macOS). Settings live in ~/.coach_connector/.
"""

from __future__ import annotations

import argparse
import email
import glob
import hashlib
import imaplib
import json
import os
import plistlib
import re
import shutil
import sqlite3
import ssl
import subprocess
import sys
import time
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
CONFIG, STATE, STATUS, LOG = HOME / "config.json", HOME / "state.json", HOME / "status.json", HOME / "sync.log"
KEYCHAIN_SERVICE = "Summer Internship Coach · Gmail app password"
BATCH_CHARS = 18_000  # one upload; the coach accepts up to 20,000 characters
EMAIL_BODY_CHARS = 3_000  # per email
MAX_EMAILS = 150  # per run, newest first
DEFAULT_DAYS = 30  # first run looks back this far
CHAT_DB = Path.home() / "Library/Messages/chat.db"
WHATSAPP_DB = Path.home() / "Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite"
MAX_GROUP = 8  # small groups are where introductions happen; bigger class or friend groups are skipped
CONTEXT_DAYS = 7  # after the first run, chats are read this far back (for context)
CONTEXT_MESSAGES = 10  # messages before the new ones, sent with them so the coach knows what they answer
MAX_SHOWN = 80  # messages per conversation per upload, newest kept
LAUNCH_LABEL = "com.summerinternshipcoach.connector"
FULL_DISK_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
SCHEDULED = False  # True while launchd runs this on its own (then Python, not Terminal, needs Full Disk Access)
CONTACT_DBS = glob.glob(str(Path.home() / "Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb")) + \
    [str(Path.home() / "Library/Application Support/AddressBook/AddressBook-v22.abcddb")]
APPLE_EPOCH = 978307200
INTRO = re.compile(r"connecting you|connect you|introduc(e|ing) you|let me introduce|happy to introduce|meet each other|"
                   r"you two should|te presento|os presento|us presento|presentaros|presentarte|os pongo en contacto", re.I)
# Chats are mostly personal, so they need a stronger signal than email: one of your people, a clear recruiting
# phrase, or one of your organisations together with an interview-type word or a real introduction. (Everyday words
# such as coffee, Zoom or "applied" are not enough, and an organisation called Apple or Amazon is not either.)
STRONG = re.compile(r"\b(internships?|summer associate|recruiters?|recruiting|superday|coffee chat|informational( interview)?|"
                    r"referral|refer you|networking|prácticas|pràctiques)\b", re.I)
INTERVIEWISH = re.compile(r"\b(interview(s|ed|ing)?|hiring|offer letter|resume|résumé|cv|cover letter|application deadline)\b", re.I)
AUTOMATED = re.compile(r"verification code|your code is|one-time code|reply stop|text stop|tracking number|out for delivery", re.I)


# ─── Small helpers ──────────────────────────────────────────────────────
class ConnectorError(Exception):
    """A problem to explain in plain words (one channel failing never stops the others). `reason` is the short code
    the coach shows (it never gets the full message, which stays in this Mac's log)."""

    def __init__(self, message: str, reason: str = "error"):
        super().__init__(message)
        self.reason = reason


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
        raise ConnectorError(f"The coach answered HTTP {e.code}: {detail}", "server") from None
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise ConnectorError(f"Could not reach the coach at {cfg['base']} ({reason}). The free server may be waking up: "
                             "try again in a minute.", "server") from None


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


def fit(block: str) -> str:
    """A long conversation keeps its header line and its newest part (what triggered the upload)."""
    if len(block) <= BATCH_CHARS:
        return block
    head, _, body = block.partition("\n")
    return f"{head}\n…\n{body[-(BATCH_CHARS - len(head) - 4):]}"


def batches(blocks: list[tuple]) -> list[list[tuple]]:
    """(key, text) pairs grouped into uploads of at most BATCH_CHARS."""
    out, cur, size = [], [], 0
    for key, text in blocks:
        text = fit(text)
        if cur and size + len(text) > BATCH_CHARS:
            out.append(cur)
            cur, size = [], 0
        cur.append((key, text))
        size += len(text) + 7  # the "\n\n---\n\n" between items
    return out + ([cur] if cur else [])


def topic_regex(ctx: dict) -> re.Pattern:
    words = ctx.get("keywords", []) + [o for o in ctx.get("organisations", []) if len(o) >= 3]
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True)) + r")\b", re.I)


def words_regex(words: list[str]) -> re.Pattern | None:
    words = sorted({w for w in words if len(w) >= 3}, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I) if words else None


def chat_matters(text: str, on_list: bool, ctx: dict) -> bool:
    """Should these chat messages reach the coach? (The rule for Messages and WhatsApp; email uses topic_regex.)"""
    if on_list:
        return True
    if AUTOMATED.search(text):
        return False
    if STRONG.search(text):
        return True
    orgs = words_regex(ctx.get("organisations", []))
    return bool(orgs and orgs.search(text) and (INTERVIEWISH.search(text) or INTRO.search(text)))


def contact_detail(name: str) -> bool:
    """A 'name' that is really a phone number or an email address (it must never leave the Mac)."""
    return "@" in name or len(re.sub(r"\D", "", name)) >= 7


def mentions_person(text: str, people: list[str]) -> bool:
    t = f" {norm(text)} "
    return any(f" {p} " in t for p in people)


# ─── Setup ──────────────────────────────────────────────────────────────
def ask_yes(question: str) -> bool:
    return input(question).strip().lower() not in ("n", "no")


def setup() -> None:
    cfg = load(CONFIG, {})
    say("Summer Internship Coach · Coach Connector setup\n")
    base = input(f"Coach address [{cfg.get('base', DEFAULT_COACH)}]: ").strip() or cfg.get("base", DEFAULT_COACH)
    say("Connector key: create one in the coach on the Connect page (it starts with sic_).")
    key = getpass("Paste your connector key (hidden): ").strip() or cfg.get("key", "")
    if not key.startswith("sic_"):
        sys.exit("That does not look like a connector key (it starts with sic_).")
    cfg.update({"base": base, "key": key})
    try:
        ctx = coach("GET", "/api/connector/context", cfg)
    except ConnectorError as e:
        sys.exit(str(e))
    say(f"Connected to your coach: {len(ctx.get('organisations', []))} organisations and {len(ctx.get('people', []))} people "
        "will be used to filter on this computer.\n")
    address = input(f"Gmail address to connect (Enter to skip) [{cfg.get('gmail', {}).get('address', '')}]: ").strip() \
        or cfg.get("gmail", {}).get("address", "")
    if address:
        say("Gmail app password: Google Account > Security > 2-Step Verification (on) > App passwords > create one.")
        pw = getpass("Paste the 16-character app password (hidden, Enter to keep the saved one): ").replace(" ", "").strip()
        gmail_cfg = {"address": address}
        if pw:
            if keychain_set(address, pw):
                gmail_cfg["password_in"] = "keychain"
                say("Saved in this Mac's Keychain.")
            else:
                gmail_cfg.update({"password_in": "file", "password": pw})
                say("No Keychain here: saved in ~/.coach_connector/config.json, readable only by you.")
        else:
            gmail_cfg.update({k: v for k, v in cfg.get("gmail", {}).items() if k != "address"})
        cfg["gmail"] = gmail_cfg
    mac = sys.platform == "darwin"
    cfg["messages"] = mac and ask_yes("Connect Messages (iMessage / SMS) on this Mac? [Y/n]: ")
    if mac and WHATSAPP_DB.exists():
        say("WhatsApp: reads the WhatsApp Desktop app's data on this Mac, read-only. It never connects to WhatsApp and is not\n"
            "a WhatsApp feature; if you prefer, skip it and upload Export chat files on the Connect page instead.")
        cfg["whatsapp"] = ask_yes("Connect WhatsApp Desktop on this Mac? [Y/n]: ")
    else:
        cfg["whatsapp"] = False
        if mac:
            say("WhatsApp Desktop is not on this Mac. To connect it: install it from whatsapp.com/download, link your phone,\n"
                "then run setup again. Or upload Export chat files on the Connect page.")
    save(CONFIG, cfg)
    say("\nDone. Try:  python3 coach_connector.py run --dry-run\nThen turn on auto-sync:  python3 coach_connector.py schedule")


# ─── Gmail (IMAP, read-only) ────────────────────────────────────────────
def gmail_password(g: dict) -> str:
    pw = keychain_get(g["address"]) if g.get("password_in") == "keychain" else g.get("password")
    if not pw:
        raise ConnectorError("No Gmail app password saved. Run: python3 coach_connector.py setup")
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
    try:
        text = part.get_content()
    except (LookupError, UnicodeError):  # a charset Python doesn't know: read it as UTF-8, replacing odd bytes
        text = (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
    if part.get_content_type() == "text/html":
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def send(cfg: dict, channel: str, blocks: list[tuple], noun: str, done=None) -> int:
    """Upload (key, text) items in batches. done(keys) runs after each accepted batch, so if a later batch fails,
    the next run starts from there instead of re-sending (and re-paying for) what the coach already has."""
    sent = 0
    for group in batches(blocks):
        r = coach("POST", "/api/connector/intake", cfg, {"channel": channel, "text": "\n\n---\n\n".join(t for _, t in group),
                                                          "label": f"{CHANNEL_NAMES[channel]} · {len(group)} {noun}",
                                                          "items": len(group)})
        if done:
            done([k for k, _ in group])
        sent += len(group)
        say(f"  sent {len(group)} {noun} → {r.get('saved')} (shield {r.get('shield', 0)}, rejected {r.get('rejected', 0)})")
    return sent


def message_ids(imap: imaplib.IMAP4_SSL, uids: list[bytes]) -> dict[bytes, str]:
    """Message-ID of each email from its headers only, so emails already seen are never downloaded again."""
    ids: dict[bytes, str] = {}
    if not uids:
        return ids
    _, data = imap.uid("fetch", b",".join(uids), "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
    for item in data or []:
        if isinstance(item, tuple):
            m = re.search(rb"UID (\d+)", item[0])
            mid = email.message_from_bytes(item[1]).get("Message-ID")
            if m and mid:
                ids[m.group(1)] = " ".join(str(mid).split())
    return ids


def email_block(imap: imaplib.IMAP4_SSL, uid: bytes, topic: re.Pattern, people: list[str]) -> tuple[str, str] | None:
    """(subject, text) for an email that matches the student's search, else None."""
    _, raw = imap.uid("fetch", uid, "(BODY.PEEK[])")  # PEEK: the email stays unread
    if not raw or not isinstance(raw[0], tuple):
        return None
    msg = email.message_from_bytes(raw[0][1], policy=policy.default)
    name, addr = parseaddr(str(msg.get("From", "")))
    subject, body = str(msg.get("Subject", "")), body_of(msg)
    text = f"{name} {addr} {subject} {body[:EMAIL_BODY_CHARS]}"
    bulk = bool(msg.get("List-Unsubscribe"))
    person = mentions_person(f"{name} {body[:EMAIL_BODY_CHARS]}", people)
    if AUTOMATED.search(text) or (bulk and not person):
        return None  # codes, deliveries, newsletters (unless they involve one of your people)
    if not (person or topic.search(text)):
        return None
    sender = name if name and not contact_detail(name) else addr.split("@")[0]
    return subject or "(no subject)", f"From: {sender}\nDate: {msg.get('Date', '')}\nSubject: {subject}\n\n{body[:EMAIL_BODY_CHARS]}"


def gmail(cfg: dict, ctx: dict, since: str | None, dry_run: bool) -> dict:
    g = cfg["gmail"]
    state = load(STATE, {})
    seen = set(state.get("gmail_seen", []))
    start = since or state.get("gmail_since") or (date.today() - timedelta(days=DEFAULT_DAYS)).isoformat()
    topic, people = topic_regex(ctx), [norm(p) for p in ctx.get("people", []) if len(p) >= 4]
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=tls(), timeout=60)
    except OSError as e:
        raise ConnectorError(f"Could not reach Gmail ({e}).", "server") from None
    blocks, picked, newly_seen = [], [], []
    try:
        try:
            imap.login(g["address"], gmail_password(g))
        except imaplib.IMAP4.error:
            raise ConnectorError("Gmail refused the sign-in. Check the address and create a new app password "
                                 "(2-Step Verification must be on).", "sign_in") from None
        imap.select(all_mail_folder(imap), readonly=True)  # read-only: nothing is changed or marked as read
        _, data = imap.uid("search", None, f'(SINCE {datetime.fromisoformat(start):%d-%b-%Y})')
        uids = (data[0] or b"").split()[-MAX_EMAILS:][::-1]
        ids = message_ids(imap, uids)
        for uid in uids:
            key = ids.get(uid) or f"uid:{uid.decode()}"
            if key in seen:
                continue
            newly_seen.append(key)
            try:
                found = email_block(imap, uid, topic, people)
            except (LookupError, UnicodeError, ValueError, IndexError, TypeError):
                continue  # one odd email never stops the run (and it is not retried)
            if found:
                picked.append(found[0])
                blocks.append((key, found[1]))
    except (imaplib.IMAP4.error, OSError) as e:  # the connection dropped (sleep, Wi-Fi): the next run picks up from here
        raise ConnectorError(f"Gmail stopped answering ({type(e).__name__}); the next run continues.", "server") from None
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001 - already disconnected
            pass
    say(f"Gmail: {len(uids)} emails since {start} checked, {len(newly_seen)} new, {len(blocks)} match your search.")
    for s in ([] if SCHEDULED else picked[:20]):  # automatic runs log counts only
        say(f"  · {s[:90]}")
    if dry_run:
        return {"checked": len(newly_seen), "sent": 0}

    def done(keys: list) -> None:
        seen.update(keys)
        st = load(STATE, {})
        st["gmail_seen"] = list(seen)[-5000:]
        save(STATE, st)

    sent = send(cfg, "gmail", blocks, "emails", done)
    seen.update(newly_seen)
    st = load(STATE, {})
    st["gmail_seen"] = (list(seen))[-5000:]
    st["gmail_since"] = (date.today() - timedelta(days=2)).isoformat()  # small overlap, seen emails are skipped
    save(STATE, st)
    return {"checked": len(newly_seen), "sent": sent}


# ─── Conversations: only new messages that matter are sent ─────────────
def send_chats(cfg: dict, channel: str, prefix: str, convs: dict, titles: dict, decide, kind: str, since: str | None,
               dry_run: bool) -> dict:
    """convs: {chat: [(row id, stamp, sender, text), …]}, oldest first.

    New means a row id above the one remembered for that chat. Row ids are the database's insert order, so messages
    that reach the Mac late (after sleep, or from someone who was offline) still count. A chat is uploaded only when
    decide(chat, new messages) says they matter, with CONTEXT_MESSAGES before them. Old, unchanged chats are never
    re-sent, so a schedule every 30 minutes spends no tokens when nothing new happened."""
    state = load(STATE, {})
    marks = {} if since else state.get(f"{prefix}_marks", {})
    base = 0 if since else state.get(f"{prefix}_base", 0)  # for chats not seen in the last run's window
    newest = {cid: max(m[0] for m in msgs) for cid, msgs in convs.items()}
    blocks, fresh = [], 0
    for cid, msgs in convs.items():
        new = [m for m in msgs if m[0] > marks.get(str(cid), base)]
        if not new:
            continue
        fresh += 1
        if not decide(cid, new):
            continue
        first = msgs.index(new[0])
        shown = msgs[max(0, first - CONTEXT_MESSAGES):][-MAX_SHOWN:]
        blocks.append(((cid, newest[cid]), f"{kind} with {titles[cid]}\n" + "\n".join(f"[{s}] {w}: {b}" for _, s, w, b in shown)))
    say(f"{CHANNEL_NAMES[channel]}: {len(convs)} conversations read, {fresh} with something new, {len(blocks)} matter.")
    for (cid, _), _text in ([] if SCHEDULED else blocks[:20]):  # automatic runs log counts only
        say(f"  · {titles[cid][:70]}")
    if dry_run:
        return {"checked": fresh, "sent": 0}

    def done(keys: list) -> None:  # remembered per accepted batch
        st = load(STATE, {})
        st.setdefault(f"{prefix}_marks", {}).update({str(cid): row for cid, row in keys})
        save(STATE, st)

    sent = send(cfg, channel, blocks, "conversations", done)
    st = load(STATE, {})
    st[f"{prefix}_marks"] = {str(cid): row for cid, row in newest.items()}  # every chat read is now up to date
    st[f"{prefix}_base"] = max(list(newest.values()) + [base])
    st[f"{prefix}_since"] = (date.today() - timedelta(days=CONTEXT_DAYS)).isoformat()
    save(STATE, st)
    return {"checked": fresh, "sent": sent}


def chat_start(prefix: str, since: str | None) -> str:
    return since or load(STATE, {}).get(f"{prefix}_since") or (date.today() - timedelta(days=DEFAULT_DAYS)).isoformat()


# ─── Messages (iMessage / SMS on a Mac, read-only) ──────────────────────
def read_only(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def no_access(app: str) -> ConnectorError:
    return ConnectorError(f"{app} can't be read: this needs Full Disk Access. System Settings > Privacy & Security > "
                          f"Full Disk Access: turn on {access_holder()}, then run again.", "full_disk_access")


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
    name = names.get(norm_handle(handle), "")
    if name and not contact_detail(name):
        return name
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


def messages(cfg: dict, ctx: dict, since: str | None, dry_run: bool) -> dict:
    start = chat_start("messages", since)
    try:
        con = read_only(str(CHAT_DB))
        con.execute("SELECT 1 FROM message LIMIT 1")
    except sqlite3.Error:
        raise no_access("Messages") from None
    names = contact_names()
    people = [norm(p) for p in ctx.get("people", []) if len(p) >= 4]
    oldest = int((datetime.fromisoformat(start).timestamp() - APPLE_EPOCH) * 1e9)
    try:
        handles = dict(con.execute("SELECT ROWID, id FROM handle"))
        members: dict[int, list[str]] = {}
        for chat_id, handle_id in con.execute("SELECT chat_id, handle_id FROM chat_handle_join"):
            if handle_id in handles:
                members.setdefault(chat_id, []).append(handles[handle_id])
        rows = con.execute("""SELECT m.ROWID, cmj.chat_id, m.date, m.is_from_me, m.handle_id, m.text, m.attributedBody
                              FROM message m JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                              WHERE m.date >= ? ORDER BY m.date""", (oldest,)).fetchall()
    finally:
        con.close()
    convs: dict[int, list[tuple]] = {}
    for rowid, chat_id, when, mine, handle_id, text, blob in rows:
        if len(members.get(chat_id, [])) > MAX_GROUP:
            continue  # big group chats are skipped: too many other people's messages
        body = body_text(text, blob).replace("\ufffc", "").strip()
        if body:
            stamp = datetime.fromtimestamp(when / 1e9 + APPLE_EPOCH, timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
            who = "You" if mine else label(handles.get(handle_id, ""), names)
            convs.setdefault(chat_id, []).append((rowid, stamp, who, body))
    titles = {cid: ", ".join(label(h, names) for h in members.get(cid, [])) or "a conversation" for cid in convs}

    def decide(cid, new) -> bool:
        return chat_matters("\n".join(m[3] for m in new), mentions_person(titles[cid], people), ctx)

    return send_chats(cfg, "imessage", "messages", convs, titles, decide, "Messages", since, dry_run)


# ─── WhatsApp (WhatsApp Desktop on a Mac, read-only) ────────────────────
def whatsapp_number(jid: str) -> str:
    digits = re.sub(r"\D", "", (jid or "").split("@")[0])
    return f"number ending {digits[-4:]}" if digits else "someone"


def whatsapp(cfg: dict, ctx: dict, since: str | None, dry_run: bool) -> dict:
    """Reads the WhatsApp Desktop app's local database read-only (the way the author's tracker does). It never talks
    to WhatsApp. Phone numbers are masked; groups of more than MAX_GROUP members are skipped."""
    start = chat_start("whatsapp", since)
    if not WHATSAPP_DB.exists():
        raise ConnectorError("WhatsApp Desktop is not on this Mac (install it from whatsapp.com/download and link your "
                             "phone), or use Export chat on the Connect page.", "not_installed")
    try:
        con = read_only(str(WHATSAPP_DB))
        con.execute("SELECT 1 FROM ZWAMESSAGE LIMIT 1")
    except sqlite3.Error:
        raise no_access("WhatsApp Desktop") from None
    people = [norm(p) for p in ctx.get("people", []) if len(p) >= 4]
    oldest = datetime.fromisoformat(start).timestamp() - APPLE_EPOCH
    try:
        sessions = {pk: {"jid": jid or "", "name": (name or "").strip(), "group": stype == 1}
                    for pk, jid, name, stype in con.execute(
                        "SELECT Z_PK, ZCONTACTJID, ZPARTNERNAME, ZSESSIONTYPE FROM ZWACHATSESSION WHERE ZSESSIONTYPE IN (0, 1)")}
        member_name = {pk: (jid or "", (cname or first or "").strip()) for pk, jid, cname, first in
                       con.execute("SELECT Z_PK, ZMEMBERJID, ZCONTACTNAME, ZFIRSTNAME FROM ZWAGROUPMEMBER")}
        try:  # real group size from WhatsApp's member list (who posted lately would undercount big groups)
            sizes: dict | None = dict(con.execute("SELECT ZCHATSESSION, COUNT(*) FROM ZWAGROUPMEMBER "
                                                  "WHERE COALESCE(ZISACTIVE, 1) != 0 GROUP BY ZCHATSESSION"))
        except sqlite3.Error:
            sizes = None  # unknown: every group counts as big
        push = dict(con.execute("SELECT ZJID, ZPUSHNAME FROM ZWAPROFILEPUSHNAME"))
        rows = con.execute("""SELECT Z_PK, ZCHATSESSION, ZMESSAGEDATE, ZISFROMME, ZGROUPMEMBER, ZFROMJID, ZTEXT FROM ZWAMESSAGE
                              WHERE ZMESSAGEDATE >= ? AND ZTEXT IS NOT NULL AND ZTEXT != '' ORDER BY ZMESSAGEDATE""",
                           (oldest,)).fetchall()
    except sqlite3.Error as e:
        raise ConnectorError(f"This WhatsApp Desktop version stores chats differently ({e}). Use Export chat on the "
                             "Connect page for now.") from None
    finally:
        con.close()

    def clean(name: str | None) -> str:
        return "" if not name or contact_detail(name) else name.strip()

    one_to_one = {s["jid"]: clean(s["name"]) for s in sessions.values() if not s["group"]}

    def who(jid: str, fallback: str = "") -> str:
        return one_to_one.get(jid) or clean(fallback) or clean(push.get(jid)) or whatsapp_number(jid)

    def big(cid: int) -> bool:
        return sessions[cid]["group"] and (sizes is None or sizes.get(cid, MAX_GROUP + 1) > MAX_GROUP)

    convs: dict[int, list[tuple]] = {}
    for rowid, chat, when, mine, member, from_jid, text in rows:
        s = sessions.get(chat)
        if s is None or big(chat):
            continue
        stamp = datetime.fromtimestamp(when + APPLE_EPOCH, timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        if mine:
            sender = "You"
        elif s["group"]:
            jid, name = member_name.get(member, (from_jid or "", ""))
            sender = who(jid, name)
        else:
            sender = who(s["jid"])
        convs.setdefault(chat, []).append((rowid, stamp, sender, text.strip()))
    titles = {c: (clean(sessions[c]["name"]) or "a group") if sessions[c]["group"] else who(sessions[c]["jid"]) for c in convs}

    def decide(cid, new) -> bool:
        on_list = mentions_person(" ".join([titles[cid]] + [m[2] for m in new]), people)
        return chat_matters("\n".join(m[3] for m in new), on_list, ctx)

    return send_chats(cfg, "whatsapp", "whatsapp", convs, titles, decide, "WhatsApp chat", since, dry_run)


CHANNELS = {"gmail": gmail, "imessage": messages, "whatsapp": whatsapp}
CHANNEL_NAMES = {"gmail": "Gmail", "imessage": "Messages", "whatsapp": "WhatsApp"}
COMMAND_CHANNELS = {"run": ["gmail", "imessage", "whatsapp"], "gmail": ["gmail"], "messages": ["imessage"], "whatsapp": ["whatsapp"]}


def enabled(cfg: dict, channel: str) -> bool:
    return bool(cfg.get({"gmail": "gmail", "imessage": "messages", "whatsapp": "whatsapp"}[channel]))


# ─── Auto-sync (macOS launchd: a per-user LaunchAgent, no admin rights) ─
def launch_label() -> str:
    """One schedule per settings folder (a test folder set with COACH_CONNECTOR_HOME gets its own)."""
    custom = os.environ.get("COACH_CONNECTOR_HOME")
    return LAUNCH_LABEL + ("." + hashlib.sha1(str(HOME).encode()).hexdigest()[:8] if custom else "")


def plist_path() -> Path:
    return Path.home() / "Library/LaunchAgents" / f"{launch_label()}.plist"


def build_plist(every: int, dry_run: bool = False) -> dict:
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    if os.environ.get("COACH_CONNECTOR_HOME"):
        env["COACH_CONNECTOR_HOME"] = str(HOME)
    return {
        "Label": launch_label(),
        "ProgramArguments": [sys.executable, str(Path(__file__).resolve()), "run", "--scheduled"] + (["--dry-run"] if dry_run else []),
        "StartInterval": every * 60, "RunAtLoad": True,  # every N minutes while the Mac is awake; once on login
        "StandardOutPath": str(LOG), "StandardErrorPath": str(LOG),
        "EnvironmentVariables": env, "WorkingDirectory": str(HOME),
        "ProcessType": "Background", "LowPriorityIO": True, "Nice": 10,
    }


def access_holder() -> str:
    """What needs Full Disk Access: Terminal when you run it by hand, this Python when it runs on its own."""
    if SCHEDULED:
        return f"Python ({python_app()})"
    return "Terminal (or the app you run this from), quit and reopen it"


def python_app() -> str:
    """The Python to add to Full Disk Access for auto-sync: the app bundle macOS checks, else the binary itself."""
    real = Path(os.path.realpath(sys.executable))
    app = real.parent.parent / "Resources" / "Python.app"
    return str(app if app.exists() else real)


def launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def schedule(every: int, dry_run: bool) -> int:
    if sys.platform != "darwin":
        say("Auto-sync uses macOS. On Linux, add this line with `crontab -e` instead:\n"
            f"*/{every} * * * * {sys.executable} {Path(__file__).resolve()} run --scheduled")
        return 1
    cfg = load(CONFIG, {})
    if not cfg.get("key"):
        sys.exit("Not set up yet. Run: python3 coach_connector.py setup")
    HOME.mkdir(mode=0o700, exist_ok=True)
    plist = plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    domain = f"gui/{os.getuid()}"
    launchctl("bootout", f"{domain}/{launch_label()}")  # replace an older schedule, if any
    with plist.open("wb") as f:
        plistlib.dump(build_plist(every, dry_run), f)
    cfg["schedule_minutes"] = every
    save(CONFIG, cfg)
    before = load(STATUS, {}).get("at")
    for attempt in range(3):  # right after a bootout, macOS sometimes needs a moment
        r = launchctl("bootstrap", domain, str(plist))
        if r.returncode == 0:
            break
        time.sleep(1 + attempt)
    else:
        if launchctl("load", "-w", str(plist)).returncode != 0:
            sys.exit(f"macOS refused the schedule ({r.stderr.strip() or r.returncode}).")
    say(f"Auto-sync is on: every {every} minutes while this Mac is awake{' (dry run: nothing is sent)' if dry_run else ''}.")
    say("First run started; waiting for it (up to 2 minutes: the free server may be waking up)…")
    for _ in range(60):
        time.sleep(2)
        st = load(STATUS, {})
        if st.get("at") and st.get("at") != before:
            break
    else:
        say(f"No result yet. Check later with:  python3 {Path(__file__).name} status   (log: {LOG})")
        return 0
    show_status(st)
    if any(c.get("reason") == "full_disk_access" for c in st.get("channels", {}).values()):
        say("\nOne more step for auto-sync to read Messages / WhatsApp: macOS asks for it separately.\n"
            "System Settings > Privacy & Security > Full Disk Access > + > press Cmd+Shift+G, paste this path, Open, turn it on:\n"
            f"  {python_app()}\n"
            "Note: this gives Full Disk Access to this Mac's Python, so any script you run with it gets the same access.\n"
            f"If you'd rather not, skip it: Gmail still syncs on its own, and `python3 {Path(__file__).name} run` syncs\n"
            "Messages and WhatsApp by hand from Terminal.\n"
            f"Then run:  python3 {Path(__file__).name} schedule" +
            ("   (Gmail already syncs without it.)" if st.get("channels", {}).get("gmail", {}).get("ok") else ""))
        subprocess.run(["open", FULL_DISK_PANE], capture_output=True)
    say(f"\nStop it any time:  python3 {Path(__file__).name} unschedule")
    return 0


def unschedule() -> int:
    plist = plist_path()
    launchctl("bootout", f"gui/{os.getuid()}/{launch_label()}")
    existed = plist.exists()
    if existed:
        plist.unlink()
    cfg = load(CONFIG, {})
    if cfg.pop("schedule_minutes", None) is not None:
        save(CONFIG, cfg)
    if cfg.get("key"):
        try:  # so the Connect page stops showing auto-sync
            coach("POST", "/api/connector/checked", cfg, {"channels": {}, "stopped": True})
        except ConnectorError:
            pass
    say("Auto-sync is off." if existed else "Auto-sync was not on.")
    return 0


def show_status(st: dict | None = None) -> None:
    st = st if st is not None else load(STATUS, {})
    if not st:
        say("No run yet.")
        return
    say(f"Last run {st.get('at', '?')} ({'automatic' if st.get('scheduled') else 'by hand'}{', dry run' if st.get('dry_run') else ''}):")
    for ch, c in st.get("channels", {}).items():
        say(f"  {CHANNEL_NAMES.get(ch, ch)}: " + (f"{c.get('checked', 0)} new checked, {c.get('sent', 0)} sent" if c.get("ok")
                                                   else f"not read — {c.get('note', '')}"))
    if st.get("error"):
        say(f"  Problem: {st['error']}")


def status() -> int:
    on = plist_path().exists()
    every = load(CONFIG, {}).get("schedule_minutes")
    say(f"Auto-sync: {'on, every ' + str(every) + ' minutes while this Mac is awake' if on else 'off'}.")
    if on:
        info = launchctl("print", f"gui/{os.getuid()}/{launch_label()}").stdout
        m = re.search(r"last exit code = (\S+)", info)
        if m:
            say(f"  last exit code: {m.group(1)} (0 = fine)")
    show_status()
    say(f"Log: {LOG}")
    return 0


def trim_log() -> None:
    try:
        if LOG.stat().st_size > 1_000_000:
            LOG.write_bytes(LOG.read_bytes()[-300_000:])
    except OSError:
        pass


# ─── Command line ───────────────────────────────────────────────────────
def run(command: str, since: str | None, dry_run: bool, scheduled: bool) -> int:
    global SCHEDULED
    SCHEDULED = scheduled
    cfg = load(CONFIG, {})
    if not cfg.get("key"):
        sys.exit("Not set up yet. Run: python3 coach_connector.py setup")
    if scheduled:
        trim_log()
        say(f"\n── {datetime.now():%Y-%m-%d %H:%M} · automatic run ──")
    result = {"at": datetime.now().isoformat(timespec="seconds"), "scheduled": scheduled, "dry_run": dry_run, "channels": {}}
    try:
        ctx = coach("GET", "/api/connector/context", cfg)
    except ConnectorError as e:
        say(str(e))
        save(STATUS, {**result, "error": str(e)})
        return 1
    failed = False
    for ch in COMMAND_CHANNELS[command]:
        if not enabled(cfg, ch):
            if command != "run":
                say(f"{CHANNEL_NAMES[ch]} is not set up (run setup to add it).")
            continue
        try:
            result["channels"][ch] = {"ok": True, **CHANNELS[ch](cfg, ctx, since, dry_run)}
        except ConnectorError as e:
            failed = True
            say(f"{CHANNEL_NAMES[ch]}: {e}")
            result["channels"][ch] = {"ok": False, "reason": e.reason, "note": str(e)[:200]}
        except Exception as e:  # noqa: BLE001 - an unexpected problem in one channel never stops the others
            failed = True
            say(f"{CHANNEL_NAMES[ch]}: unexpected problem ({type(e).__name__}: {e})")
            result["channels"][ch] = {"ok": False, "reason": "error", "note": f"{type(e).__name__}: {e}"[:200]}
    if dry_run:
        say("Dry run: nothing was sent.")
    elif result["channels"]:
        auto = scheduled or (sys.platform == "darwin" and plist_path().exists())
        report = {ch: {k: v for k, v in c.items() if k != "note"} for ch, c in result["channels"].items()}
        try:  # counts and a reason code only (the message stays here), so the Connect page shows auto-sync is working
            coach("POST", "/api/connector/checked", cfg, {"channels": report,
                                                          "every_minutes": cfg.get("schedule_minutes") if auto else None})
        except ConnectorError as e:
            say(f"(Could not report the check to the coach: {e})")
    save(STATUS, result)
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["setup", "run", "gmail", "messages", "whatsapp", "schedule", "unschedule", "status"])
    ap.add_argument("--since", help="YYYY-MM-DD: look back to this date (default: since the last run, or 30 days)")
    ap.add_argument("--dry-run", action="store_true", help="show what would be sent; send nothing")
    ap.add_argument("--every", type=int, default=30, help="schedule: minutes between automatic runs (default 30)")
    ap.add_argument("--scheduled", action="store_true", help=argparse.SUPPRESS)  # set by the schedule itself
    args = ap.parse_args()
    if args.since:
        try:
            date.fromisoformat(args.since)
        except ValueError:
            sys.exit("--since must look like 2026-10-01")
    if args.command == "setup":
        setup()
        return 0
    if args.command == "schedule":
        if not 5 <= args.every <= 1440:
            sys.exit("--every must be between 5 and 1440 minutes")
        return schedule(args.every, args.dry_run)
    if args.command == "unschedule":
        return unschedule()
    if args.command == "status":
        return status()
    return run(args.command, args.since, args.dry_run, args.scheduled)


if __name__ == "__main__":
    sys.exit(main())
