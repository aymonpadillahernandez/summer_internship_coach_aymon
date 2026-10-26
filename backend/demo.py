"""The demo dataset: a fictional MBA student ("Jordan Rivera") with fictional organisations and people.

data/demo/demo_seed.json is the small test dataset shipped in the repo. Dates in it are written relative to today
(@iso+6 = six days from today as YYYY-MM-DD, @text+6 = "Nov 2, 2026", @us+6 = "11/2/26", @dt+2T15:00 = a date and time), so the
demo always looks current. data/demo/samples/ holds texts to paste in the demo (a posting, an email, a WhatsApp
export, a LinkedIn CSV, and two prompt-injection attacks); samples.json describes them.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

import config
import db
from store import connect, insert_id

DEMO_DIR = config.ROOT / "data" / "demo"
TOKEN = re.compile(r"@(iso|text|dt|us)([+-]\d+)(?:T(\d\d:\d\d))?")


def _resolve(value):
    if isinstance(value, str):
        def sub(m: re.Match) -> str:
            d = date.today() + timedelta(days=int(m.group(2)))
            if m.group(1) == "text":
                return f"{d:%b} {d.day}, {d.year}"
            if m.group(1) == "us":  # WhatsApp export style: 10/22/26
                return f"{d.month}/{d.day}/{d:%y}"
            if m.group(1) == "dt":
                return f"{d.isoformat()}T{m.group(3) or '12:00'}"
            return d.isoformat()
        return TOKEN.sub(sub, value)
    if isinstance(value, list):
        return [_resolve(v) for v in value]
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    return value


def seed(user_id: int) -> None:
    data = _resolve(json.loads((DEMO_DIR / "demo_seed.json").read_text(encoding="utf-8")))
    db.set_profile(user_id, data["profile"])
    ids: dict[str, int] = {}
    with connect() as conn:
        for a in data["opportunities"]:
            ids[a["ref"]] = insert_id(conn,
                """INSERT INTO applications (user_id, company, role, formal_internship, mba_eligible, deadline, location,
                       priority, context, stakeholders, status, last_contact, notes, origin, source_url, added_on, fit, fit_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'demo', ?, ?, ?, ?)""",
                (user_id, a["company"], a["role"], a.get("formal_internship", "Not clear"), a.get("mba_eligible", "Not clear"),
                 a.get("deadline", ""), a.get("location", ""), a.get("priority", ""), a.get("context", ""),
                 a.get("stakeholders", ""), a.get("status", "not_started"), a.get("last_contact"), a.get("notes", ""),
                 a.get("source_url", ""), date.today().isoformat(), a.get("fit"), a.get("fit_reason")))
        for c in data["contacts"]:
            apps = [ids[r] for r in c.get("opportunities", [])]
            doors = [ids[r] for r in c.get("can_help", [])]
            cid = insert_id(conn,
                """INSERT INTO contacts (user_id, name, affiliation, status, last_contact, how_met, next_step, next_date,
                       application_ids, network_ids, source, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, c["name"], c.get("affiliation", ""), c["status"], c.get("last_contact"), c.get("how_met", ""),
                 c.get("next_step"), c.get("next_date"), json.dumps(apps), json.dumps(doors), c.get("source", "demo"),
                 c.get("notes", "")))
            for i, e in enumerate(c.get("events", [])):
                for app_id in apps or [None]:
                    conn.execute(
                        """INSERT OR IGNORE INTO events (user_id, contact_id, application_id, date, text, evidence,
                               source_message_id, source_subject, origin) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (user_id, cid, app_id, e["date"], e["text"], e["evidence"], f"demo:{cid}:{i}",
                         e.get("subject", ""), e.get("origin", "demo")))
        for i, lead in enumerate(data["leads"]):
            conn.execute(
                """INSERT INTO leads (user_id, application_ids, kind, date, when_text, summary, posted_by, evidence, url,
                       origin, source_ref, source_subject) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, json.dumps([ids[r] for r in lead.get("opportunities", [])]), lead["kind"], lead["date"],
                 lead.get("when", ""), lead["summary"], lead.get("posted_by", ""), lead.get("evidence", ""),
                 lead.get("url", ""), "demo", f"demo:lead:{i}", lead.get("subject", "")))
    if data.get("prefs"):
        db.set_prefs(user_id, data["prefs"])  # last, so its organisations match the demo's cards: the form shows filled in


SAMPLE_FILES = {  # name -> (download file name, what it is): the channel-card samples on the Setup tab, demo accounts only
    "whatsapp": ("WhatsApp Chat - Priya Shah.zip", "WhatsApp's Export chat (without media)"),
    "linkedin_connections": ("Connections.csv", "LinkedIn's Download your data: connections"),
    "linkedin_messages": ("messages.csv", "LinkedIn's Download your data: messages"),
    "email": ("Re Harborview partnerships internship.eml", "an email downloaded from Gmail or Outlook"),
    "calendar": ("Coffee chat - Maya Chen.ics", "a calendar invite"),
    "imessage": ("Messages - Luis Moreno.txt", "a Messages thread copied from a Mac"),
}


def sample_file(name: str) -> tuple[str, bytes, str]:
    """(file name, bytes, media type) of one fictional channel export, built from the demo samples with current dates."""
    import io
    import zipfile
    from email.message import EmailMessage

    read = lambda f: _resolve((DEMO_DIR / "samples" / f).read_text(encoding="utf-8"))  # noqa: E731
    filename = SAMPLE_FILES[name][0]
    if name == "whatsapp":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("_chat.txt", read("whatsapp_priya.txt"))
        return filename, buf.getvalue(), "application/zip"
    if name in ("linkedin_connections", "linkedin_messages"):
        return filename, read(f"{name}.csv").encode(), "text/csv"
    if name == "email":
        head, _, body = read("email_harborview.txt").partition("\n\n")
        fields = dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)
        msg = EmailMessage()
        msg["From"] = f"{fields.get('From', 'Elena Petrova')} <elena.petrova@example.com>"
        msg["To"] = "Jordan Rivera <jordan.rivera@example.com>"
        msg["Subject"] = fields.get("Subject", "")
        msg["Date"] = fields.get("Date", "")
        msg.set_content(body)
        return filename, bytes(msg), "message/rfc822"
    if name == "calendar":
        d = date.today() + timedelta(days=3)
        ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Summer Internship Coach demo//EN\r\nBEGIN:VEVENT\r\n"
               f"UID:demo-coffee-chat-{d:%Y%m%d}@example.com\r\nDTSTART:{d:%Y%m%d}T150000\r\nDTEND:{d:%Y%m%d}T153000\r\n"
               "SUMMARY:Coffee chat: Jordan Rivera / Maya Chen (Northbridge Sports Group)\r\n"
               "ORGANIZER;CN=Maya Chen:mailto:maya.chen@example.com\r\n"
               "DESCRIPTION:30 minutes on the Northbridge strategy internship and the summer team.\r\n"
               "END:VEVENT\r\nEND:VCALENDAR\r\n")
        return filename, ics.encode(), "text/calendar"
    if name == "imessage":
        return filename, read("messages_luis.txt").encode(), "text/plain"
    raise KeyError(name)


def samples() -> list[dict]:
    manifest = json.loads((DEMO_DIR / "samples.json").read_text(encoding="utf-8"))
    out = []
    for s in manifest:
        text = _resolve((DEMO_DIR / "samples" / s["file"]).read_text(encoding="utf-8"))
        out.append({**s, "text": text})
    return out
