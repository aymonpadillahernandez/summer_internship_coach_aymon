"""Auto-sync: the connector's schedule, its WhatsApp Desktop reader and the counts-only check it reports.
Everything runs on throwaway files: a synthetic WhatsApp database, a temporary settings folder, no network, no tokens.
Several tests pin bugs an adversarial review found (Oct 25): late messages, failed uploads, big groups, masked names,
an odd email charset stopping every channel, and free text in the status report."""

from __future__ import annotations

import importlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from email import message_from_bytes, policy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import db
import main

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "connector"))

APPLE_EPOCH = 978307200
CTX = {"organisations": ["Harborview Capital", "Apple"], "people": ["Priya Natarajan"], "keywords": ["internship", "coffee"]}


@pytest.fixture
def cc(tmp_path, monkeypatch):
    """The connector module with its settings folder in a temporary directory."""
    monkeypatch.setenv("COACH_CONNECTOR_HOME", str(tmp_path / "settings"))
    import coach_connector

    return importlib.reload(coach_connector)


def _apple(days_ago: float) -> float:
    return (datetime.now() - timedelta(days=days_ago)).timestamp() - APPLE_EPOCH


@pytest.fixture
def wa_db(cc, tmp_path, monkeypatch) -> sqlite3.Connection:
    """A synthetic WhatsApp Desktop database (the columns the connector reads, from a real one's schema)."""
    path = tmp_path / "ChatStorage.sqlite"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE ZWACHATSESSION (Z_PK INTEGER PRIMARY KEY, ZCONTACTJID TEXT, ZPARTNERNAME TEXT, ZSESSIONTYPE INTEGER);
        CREATE TABLE ZWAGROUPMEMBER (Z_PK INTEGER PRIMARY KEY, ZCHATSESSION INTEGER, ZISACTIVE INTEGER, ZMEMBERJID TEXT,
                                     ZCONTACTNAME TEXT, ZFIRSTNAME TEXT);
        CREATE TABLE ZWAPROFILEPUSHNAME (ZJID TEXT, ZPUSHNAME TEXT);
        CREATE TABLE ZWAMESSAGE (Z_PK INTEGER PRIMARY KEY, ZCHATSESSION INTEGER, ZMESSAGEDATE REAL, ZISFROMME INTEGER,
                                 ZGROUPMEMBER INTEGER, ZFROMJID TEXT, ZTEXT TEXT);
        INSERT INTO ZWACHATSESSION VALUES (1, '15550001111@s.whatsapp.net', 'Priya Natarajan', 0),
                                          (2, '15550002222@s.whatsapp.net', 'Mom', 0),
                                          (3, '15559871234@s.whatsapp.net', '+1 (555) 987-1234', 0),
                                          (4, '120363@g.us', 'Class of 2028', 1),
                                          (5, '15550005555@s.whatsapp.net', 'Alex', 0);
    """)
    # 12 members but only 2 of them post: the size must come from the member list, not from who spoke lately
    con.executemany("INSERT INTO ZWAGROUPMEMBER VALUES (?, 4, 1, ?, ?, NULL)",
                    [(100 + i, f"1555300{i:04}@s.whatsapp.net", f"Classmate {i}") for i in range(12)])
    rows = [(1, _apple(2), 0, None, "Happy to do a coffee chat about the Harborview summer team."),
            (1, _apple(1.9), 1, None, "Thank you, Thursday works!"),
            (2, _apple(1), 0, None, "Dinner on Sunday?"),
            (3, _apple(1), 0, None, "Hi, I'm the alum you met: free for a coffee chat next week?"),
            (4, _apple(1), 0, 100, "Anyone applying to the internship fair?"),
            (4, _apple(1), 0, 101, "Me! Coffee chat prep tonight?"),
            (5, _apple(1), 0, None, "Coffee and a catch up on Zoom later? I applied at the Apple store!")]
    con.executemany("INSERT INTO ZWAMESSAGE (ZCHATSESSION, ZMESSAGEDATE, ZISFROMME, ZGROUPMEMBER, ZTEXT) VALUES (?, ?, ?, ?, ?)", rows)
    con.commit()
    monkeypatch.setattr(cc, "WHATSAPP_DB", path)
    return con


@pytest.fixture
def sent(cc, wa_db, monkeypatch) -> list:
    """Records uploads in place of send() (accepting every batch)."""
    out: list[list[str]] = []

    def fake_send(cfg, channel, blocks, noun, done=None):
        if blocks:
            out.append([t for _, t in blocks])
            if done:
                done([k for k, _ in blocks])
        return len(blocks)

    monkeypatch.setattr(cc, "send", fake_send)
    return out


def _add(con, chat: int, days_ago: float, text: str) -> None:
    con.execute("INSERT INTO ZWAMESSAGE (ZCHATSESSION, ZMESSAGEDATE, ZISFROMME, ZTEXT) VALUES (?, ?, 0, ?)", (chat, _apple(days_ago), text))
    con.commit()


def test_whatsapp_desktop_is_read_filtered_masked_and_never_resent(cc, wa_db, sent):
    assert cc.whatsapp({}, CTX, None, dry_run=True) == {"checked": 4, "sent": 0}  # the 12-member group is not read
    assert not sent and not cc.STATE.exists()  # a dry run sends and remembers nothing

    assert cc.whatsapp({}, CTX, None, dry_run=False) == {"checked": 4, "sent": 2}
    blocks = "\n".join(sent[0])
    assert "Priya Natarajan" in blocks and "number ending 1234" in blocks  # on the list; a clear recruiting phrase
    assert "Dinner on Sunday" not in blocks and "Class of 2028" not in blocks  # personal chat; a big group
    assert "Apple store" not in blocks  # everyday words, and an organisation called Apple, are not enough
    assert "987-1234" not in blocks and "15559871234" not in blocks  # a number saved as the chat's name is masked too

    sent.clear()
    assert cc.whatsapp({}, CTX, None, dry_run=False) == {"checked": 0, "sent": 0}  # nothing new: no upload, no tokens
    assert not sent

    _add(wa_db, 1, 0, "See you Thursday!")
    _add(wa_db, 3, 0, "lol ok")  # new, but personal, in a chat whose person is not on the list
    assert cc.whatsapp({}, CTX, None, dry_run=False) == {"checked": 2, "sent": 1}
    assert len(sent[0]) == 1 and "See you Thursday!" in sent[0][0] and "coffee chat" in sent[0][0]  # sent with context


def test_a_message_that_reaches_the_mac_late_is_still_sent(cc, wa_db, sent):
    cc.whatsapp({}, CTX, None, dry_run=False)
    sent.clear()
    _add(wa_db, 5, 1.5, "Alex here: I can refer you for the Harborview internship")  # dated before rows already read
    assert cc.whatsapp({}, CTX, None, dry_run=False)["sent"] == 1
    assert "refer you" in sent[0][0]


def test_a_failed_upload_resends_only_what_the_coach_did_not_get(cc, wa_db, monkeypatch):
    monkeypatch.setattr(cc, "BATCH_CHARS", 150)  # one conversation per upload
    posts: list[str] = []

    def coach(method, path, cfg, payload=None):
        posts.append(payload["text"])
        if len(posts) == 2:
            raise cc.ConnectorError("The coach answered HTTP 429: daily budget", "server")
        return {"saved": {}}

    monkeypatch.setattr(cc, "coach", coach)
    with pytest.raises(cc.ConnectorError):
        cc.whatsapp({}, CTX, None, dry_run=False)
    accepted = posts[0]
    posts.clear()
    cc.whatsapp({}, CTX, None, dry_run=False)
    assert accepted not in posts and len(posts) == 1  # the accepted chat is not sent (or paid for) twice


class FakeGmail:
    """Just enough IMAP for gmail(): two emails, one in a charset Python 3.9 can't decode, one from a 'name' that is a number."""
    EMAILS = {b"1": b"From: Priya Natarajan <p@example.com>\r\nMessage-ID: <one@x>\r\nSubject: Coffee chat\r\n"
                    b"Content-Type: text/plain; charset=iso-8859-8-i\r\n\r\nHappy to talk about the Harborview internship.",
              b"2": b"From: +1 555 123 4567 <x@example.com>\r\nMessage-ID: <two@x>\r\nSubject: Internship referral\r\n\r\nI can refer you."}
    full_fetches: list = []

    def __init__(self, *a, **k): ...
    def login(self, *a): ...
    def logout(self): ...
    def list(self): return "OK", [b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"']
    def select(self, *a, **k): return "OK", [b"2"]

    def uid(self, cmd, *args):
        if cmd == "search":
            return "OK", [b"1 2"]
        ids, what = args
        if "HEADER.FIELDS" in what:
            return "OK", [(b"%s (UID %s BODY[HEADER.FIELDS (MESSAGE-ID)] {20}" % (u, u), self.EMAILS[u].split(b"Subject")[0])
                          for u in ids.split(b",")]
        FakeGmail.full_fetches.append(ids)
        return "OK", [(b"%s (UID %s BODY[] {99}" % (ids, ids), self.EMAILS[ids]), b")"]


def test_gmail_reads_odd_charsets_masks_numbers_and_never_redownloads(cc, monkeypatch):
    monkeypatch.setattr(cc.imaplib, "IMAP4_SSL", FakeGmail)
    monkeypatch.setattr(cc, "gmail_password", lambda g: "app-password")
    uploads: list[str] = []
    monkeypatch.setattr(cc, "coach", lambda m, path, cfg, payload=None: uploads.append(payload["text"]) or {"saved": {}})
    FakeGmail.full_fetches = []
    assert cc.gmail({"gmail": {"address": "me@example.com"}}, CTX, None, dry_run=False) == {"checked": 2, "sent": 2}
    assert "Harborview internship" in uploads[0] and "From: x\n" in uploads[0] and "555 123" not in uploads[0]
    FakeGmail.full_fetches = []
    assert cc.gmail({"gmail": {"address": "me@example.com"}}, CTX, None, dry_run=False) == {"checked": 0, "sent": 0}
    assert FakeGmail.full_fetches == []  # seen emails: headers only, no full download every 30 minutes


def test_schedule_is_a_user_launch_agent_every_30_minutes(cc):
    p = cc.build_plist(30)
    assert p["ProgramArguments"][1:] == [str(Path(cc.__file__).resolve()), "run", "--scheduled"]
    assert p["ProgramArguments"][0] == sys.executable
    assert p["StartInterval"] == 1800 and p["RunAtLoad"] is True
    assert p["StandardOutPath"] == str(cc.LOG) and str(cc.HOME) in p["StandardOutPath"]
    assert p["EnvironmentVariables"]["COACH_CONNECTOR_HOME"] == str(cc.HOME)
    assert cc.launch_label().startswith("com.summerinternshipcoach.connector.")  # a test folder gets its own label
    assert str(cc.plist_path()).startswith(str(Path.home() / "Library/LaunchAgents"))
    assert cc.build_plist(30, dry_run=True)["ProgramArguments"][-1] == "--dry-run"


def test_one_channel_failing_never_stops_the_others(cc, monkeypatch):
    cc.save(cc.CONFIG, {"base": "http://coach.test", "key": "sic_test", "gmail": {"address": "a@b.c"}, "messages": True,
                        "whatsapp": True, "schedule_minutes": 30})
    calls: list[tuple] = []

    def fake_coach(method, path, cfg, payload=None):
        calls.append((method, path, payload))
        return CTX if path.endswith("/context") else {"ok": True}

    def odd_charset(cfg, ctx, since, dry_run):
        raise LookupError("unknown encoding: iso-8859-8-i")  # not a ConnectorError: must not stop the run

    def no_access(cfg, ctx, since, dry_run):
        raise cc.no_access("Messages")

    monkeypatch.setattr(cc, "coach", fake_coach)
    monkeypatch.setitem(cc.CHANNELS, "gmail", odd_charset)
    monkeypatch.setitem(cc.CHANNELS, "imessage", no_access)
    monkeypatch.setitem(cc.CHANNELS, "whatsapp", lambda cfg, ctx, since, dry_run: {"checked": 2, "sent": 0})

    assert cc.run("run", None, dry_run=False, scheduled=True) == 1  # launchd records the failure
    report = calls[-1][2]
    assert calls[-1][1] == "/api/connector/checked" and report["every_minutes"] == 30
    assert report["channels"]["whatsapp"] == {"ok": True, "checked": 2, "sent": 0}  # still ran
    assert report["channels"]["gmail"] == {"ok": False, "reason": "error"}
    assert report["channels"]["imessage"] == {"ok": False, "reason": "full_disk_access"}  # a code, never free text
    status = json.loads(cc.STATUS.read_text())  # the full message stays on the Mac
    assert "Python" in status["channels"]["imessage"]["note"]  # on a schedule, Python is what needs the access
    assert "LookupError" in status["channels"]["gmail"]["note"]


def test_an_email_in_an_unknown_charset_is_read_not_fatal(cc):
    raw = (b"From: Priya Natarajan <p@example.com>\r\nSubject: Coffee chat\r\nContent-Type: text/plain; charset=iso-8859-8-i\r\n\r\n"
           b"Happy to talk about the Harborview internship.")
    assert "Harborview internship" in cc.body_of(message_from_bytes(raw, policy=policy.default))


def test_the_check_report_shows_auto_sync_and_costs_no_tokens(demo_client):
    key = demo_client.post("/api/connector/keys", json={}).json()["key"]
    with db.connect() as conn:
        runs_before = conn.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0]
    with TestClient(main.app) as connector:
        h = {"Authorization": f"Bearer {key}"}
        body = {"every_minutes": 30, "channels": {
            "gmail": {"ok": True, "checked": 12, "sent": 2},
            "imessage": {"ok": False, "reason": "full_disk_access", "note": "Click here to verify your account"}}}
        assert connector.post("/api/connector/checked", headers=h, json=body).json() == {"ok": True}
        for bad in ({"channels": {"slack": {"ok": True}}}, {"channels": {"gmail": {"ok": False, "reason": "phish"}}}):
            assert connector.post("/api/connector/checked", headers=h, json=bad).status_code == 422
        assert connector.post("/api/connector/checked", json=body).status_code == 401  # needs a connector key
        syncs = {s["channel"]: s for s in demo_client.get("/api/connector/status").json()["syncs"]}
        assert syncs["gmail"]["ok"] is True and syncs["gmail"]["auto_minutes"] == 30 and syncs["gmail"]["summary"] == "12 checked, 2 sent"
        assert syncs["imessage"]["ok"] is False and syncs["imessage"]["summary"] == "Needs Full Disk Access on the Mac"  # fixed text
        assert connector.post("/api/connector/checked", headers=h, json={"stopped": True}).json() == {"ok": True}
    assert all(s["auto_minutes"] is None for s in demo_client.get("/api/connector/status").json()["syncs"])  # auto-sync off
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0] == runs_before  # counts only: no model call


def test_downloaded_connector_defaults_to_the_coach_it_came_from():
    """A copy downloaded from a coach on this computer talks to that coach; any other host keeps the live site."""
    with TestClient(main.app, base_url="http://127.0.0.1:8041") as local:
        assert 'DEFAULT_COACH = "http://127.0.0.1:8041"' in local.get("/connector/coach_connector.py").text
    with TestClient(main.app, base_url="https://summer-internship-coach.onrender.com") as live:
        assert 'DEFAULT_COACH = "https://summer-internship-coach.onrender.com"' in live.get("/connector/coach_connector.py").text
    with TestClient(main.app, base_url="http://evil.example:8041") as other:
        assert 'DEFAULT_COACH = "https://summer-internship-coach.onrender.com"' in other.get("/connector/coach_connector.py").text
