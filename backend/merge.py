"""Validate what the specialists extracted, then merge it into the student's records.

Validation (the "hallucinated facts" and "prompt injection" defenses after the model answers):
- every evidence quote must appear in the pasted text, or the item is rejected;
- every person must be named in the pasted text, or the contact is rejected;
- URLs are kept only when they appear in the text; linked record ids must belong to this student;
- email addresses and phone numbers are scrubbed from every stored field;
- event dates must be real dates and not in the future.
Each rejection is reported back to the student with its reason.

Merge rules (copied from the author's tracker, apply_updates.py): newer evidence decides a contact's stage; a card
the student moved by hand keeps their choice until something newer happens; opportunities only move forward;
events and leads are de-duplicated by their source.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta

import db
import safety
from agents.models import NetworkIntake, ScoutIntake, trim
from store import connect, insert_id

STATUS_WORDS = re.compile(r"\b(appl(y|ied|ication)|submitted|interview|offer|regret|unfortunately|not (moving|selected)|reject)", re.I)
FIT_PRIORITY = {"strong": "A", "possible": "B", "weak": "B−", "unknown": ""}
STATUS_ORDER = db.STAGE_KEYS


def source_ref(text: str) -> str:
    return "paste:" + hashlib.sha256(text.encode()).hexdigest()[:12]


def _iso_date(value: str | None, allow_future: bool) -> str | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value[:16]) if "T" in value else datetime.fromisoformat(value[:10])
    except ValueError:
        return None
    if not allow_future and d.date() > date.today() + timedelta(days=1):
        return None
    return value[:16] if "T" in value else value[:10]


# ─── Validation ─────────────────────────────────────────────────────────
def validate_scout(report: ScoutIntake, source: str, user_id: int) -> tuple[ScoutIntake, list[dict]]:
    src = safety.norm(source)
    own = {a["id"] for a in db.list_applications(user_id)}
    rejected, kept_opps, kept_leads = [], [], []
    for o in report.opportunities[:10]:
        o.company, o.role, o.deadline, o.location = trim(o.company, 120), trim(o.role, 160), trim(o.deadline, 80), trim(o.location, 120)
        o.fit_reason, o.key_points = trim(o.fit_reason, 240), [trim(k, 80) for k in o.key_points[:3]]
        if not safety.in_source(o.evidence, src):
            rejected.append({"item": f"{o.company} — {o.role}", "reason": "its quote is not in the text you pasted"})
            continue
        if not (safety.in_source(o.company, src, min_len=2) or o.match_id in own):
            rejected.append({"item": o.company, "reason": "the organisation is not named in the text"})
            continue
        if o.match_id is not None and o.match_id not in own:
            o.match_id = None
        o.url = safety.url_in_source(o.url, src)
        if o.status_signal != "none" and not STATUS_WORDS.search(o.evidence):
            rejected.append({"item": f"{o.company}: marked '{o.status_signal}'", "reason": "the quote does not say so; kept as not started"})
            o.status_signal = "none"
        kept_opps.append(o)
    companies = [o.company.lower() for o in kept_opps if o.company]
    for l in report.leads[:8]:
        l.summary, l.when = trim(l.summary, 200), trim(l.when, 80)
        if l.kind in ("deadline", "posting") and any(c in l.summary.lower() for c in companies):
            continue  # the opportunity card already carries its own deadline: no duplicate lead
        if not safety.in_source(l.evidence, src):
            rejected.append({"item": l.summary[:80], "reason": "its quote is not in the text you pasted"})
            continue
        if l.match_id is not None and l.match_id not in own:
            l.match_id = None
        kept_leads.append(l)
    return ScoutIntake(opportunities=kept_opps, leads=kept_leads, fields_not_found=[trim(f, 200) for f in report.fields_not_found[:8]]), rejected


def validate_network(report: NetworkIntake, source: str, user_id: int) -> tuple[NetworkIntake, list[dict]]:
    src = safety.norm(source)
    own = {a["id"] for a in db.list_applications(user_id)}
    rejected, kept = [], []
    for c in report.contacts[:15]:
        c.name, c.affiliation, c.how_met = trim(c.name, 80), trim(c.affiliation, 120), trim(c.how_met, 160)
        c.next_step = trim(c.next_step, 160) or None
        c.events = c.events[:5]
        if not safety.name_in_source(c.name, src):
            rejected.append({"item": c.name, "reason": "this name does not appear in the text you pasted"})
            continue
        events = []
        for e in c.events:
            when = _iso_date(e.date, allow_future=False)
            if not safety.in_source(e.evidence, src):
                rejected.append({"item": f"{c.name}: {e.text[:60]}", "reason": "its quote is not in the text you pasted"})
            elif when is None:
                rejected.append({"item": f"{c.name}: {e.text[:60]}", "reason": "no valid past date"})
            else:
                e.date, e.text = when, trim(e.text, 180)
                events.append(e)
        c.events = events
        c.opportunity_ids = [i for i in c.opportunity_ids if i in own]
        c.can_help_ids = [i for i in c.can_help_ids if i in own]
        c.last_contact = _iso_date(c.last_contact, allow_future=False)
        c.next_date = _iso_date(c.next_date, allow_future=True)
        if c.status == "call_booked" and not c.next_date:
            c.status = "follow_up"  # a booked call must carry its date (tracker rule)
        kept.append(c)
    return NetworkIntake(contacts=kept, fields_not_found=[trim(f, 200) for f in report.fields_not_found[:8]]), rejected


# ─── Merge ──────────────────────────────────────────────────────────────
FIT_CHECK = {"strong": "yes", "possible": "yes", "weak": "check"}


def apply_scout(user_id: int, report: ScoutIntake, origin: str, ref: str, label: str, page_url: str | None = None) -> dict:
    """page_url: the page the student linked and the app read. It becomes the card's source link and its
    page check (status, deadline, quote, date), shown on the card and used by the action plan."""
    added, updated, leads = [], [], 0
    today = date.today().isoformat()
    with connect() as conn:
        for o in report.opportunities:
            if page_url and not o.url:
                o.url = page_url
            context = " · ".join(safety.scrub(p)[:80] for p in o.key_points)
            row = None
            if o.match_id is not None:
                row = conn.execute("SELECT * FROM applications WHERE id = ? AND user_id = ?", (o.match_id, user_id)).fetchone()
            if row is None:
                row = conn.execute("SELECT * FROM applications WHERE user_id = ? AND lower(company) = lower(?) AND lower(role) = lower(?)",
                                   (user_id, o.company, o.role)).fetchone()
            if row is None:
                app_id = insert_id(conn,
                    """INSERT INTO applications (user_id, company, role, formal_internship, mba_eligible, deadline, location,
                           priority, context, stakeholders, status, origin, source_url, added_on, fit, fit_reason, last_contact)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, safety.scrub(o.company), safety.scrub(o.role), o.formal_internship, o.mba_eligible,
                     safety.scrub(o.deadline), safety.scrub(o.location), FIT_PRIORITY[o.fit], context,
                     o.status_signal if o.status_signal in STATUS_ORDER else "not_started", origin, o.url, today,
                     o.fit, safety.scrub(o.fit_reason), today if o.status_signal != "none" else None))
                added.append({"id": app_id, "company": o.company, "role": o.role})
            else:
                app_id = row["id"]
                status = row["status"]
                if o.status_signal in STATUS_ORDER and STATUS_ORDER.index(o.status_signal) > STATUS_ORDER.index(status):
                    status = o.status_signal  # opportunities only move forward
                conn.execute(
                    """UPDATE applications SET deadline = ?, location = ?, formal_internship = ?, mba_eligible = ?,
                           status = ?, fit = COALESCE(?, fit), fit_reason = COALESCE(?, fit_reason),
                           context = CASE WHEN context = '' THEN ? ELSE context END,
                           source_url = CASE WHEN source_url = '' THEN ? ELSE source_url END,
                           last_contact = CASE WHEN ? THEN ? ELSE last_contact END, updated_at = datetime('now')
                       WHERE id = ? AND user_id = ?""",
                    (safety.scrub(o.deadline) or row["deadline"], safety.scrub(o.location) or row["location"],
                     o.formal_internship if o.formal_internship != "Not clear" else row["formal_internship"],
                     o.mba_eligible if o.mba_eligible != "Not clear" else row["mba_eligible"], status,
                     None if o.fit == "unknown" else o.fit, safety.scrub(o.fit_reason) or None, context, o.url,
                     o.status_signal != "none", today, app_id, user_id))
                updated.append({"id": app_id, "company": row["company"], "role": row["role"]})
            if page_url:
                conn.execute(
                    """UPDATE applications SET verified_status = ?, verified_summary = ?, verified_deadline = ?,
                           verified_url = ?, verified_evidence = ?, verified_on = ?, verified_fit = ?, source_url = ?
                       WHERE id = ? AND user_id = ?""",
                    (None if o.posting_status == "unknown" else o.posting_status, safety.scrub(" · ".join(o.key_points[:2])) or None,
                     safety.scrub(o.deadline) or None, page_url, safety.scrub(trim(o.evidence, 400)), today,
                     FIT_CHECK.get(o.fit), page_url, app_id, user_id))
            conn.execute(
                """INSERT OR IGNORE INTO events (user_id, contact_id, application_id, date, text, evidence,
                                                 source_message_id, source_subject, origin)
                   VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, app_id, today, safety.scrub(f"Added from your paste: {o.role}" + (f", deadline {o.deadline}" if o.deadline else "")),
                 safety.scrub(trim(o.evidence, 400)), ref, label, origin))
        for i, l in enumerate(report.leads):
            cur = conn.execute(
                """INSERT OR IGNORE INTO leads (user_id, application_ids, kind, date, when_text, summary, evidence, origin,
                                                source_ref, source_subject) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, json.dumps([l.match_id] if l.match_id else []), l.kind, today, safety.scrub(l.when),
                 safety.scrub(l.summary), safety.scrub(trim(l.evidence, 400)), origin, f"{ref}:{i}", label))
            leads += cur.rowcount
    return {"opportunities_added": added, "opportunities_updated": updated, "leads_added": leads}


def _forward(current: str, new: str) -> str:
    keys = db.NETWORK_KEYS
    if current not in keys:
        return new
    return new if keys.index(new) > keys.index(current) else current


def _pick_status(cur, theirs: str, new_status: str) -> str:
    """Newer evidence decides; older evidence never changes anything; the student's own moves win over older evidence."""
    ours = cur["last_contact"] or ""
    if cur["status_manual_at"] and cur["status_manual_at"] >= theirs:
        return cur["status"]
    if theirs > ours:
        return new_status
    if theirs == ours:
        return _forward(cur["status"], new_status)
    return cur["status"]


def apply_network(user_id: int, report: NetworkIntake, origin: str, ref: str, label: str) -> dict:
    added, updated, events = [], [], 0
    with connect() as conn:
        for c in report.contacts:
            name = safety.scrub(c.name).strip()
            cur = conn.execute("SELECT * FROM contacts WHERE user_id = ? AND lower(name) = lower(?)", (user_id, name)).fetchone()
            if cur is None:
                cid = insert_id(conn,
                    """INSERT INTO contacts (user_id, name, affiliation, status, last_contact, how_met, next_step, next_date,
                                             application_ids, network_ids, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, name, safety.scrub(c.affiliation), c.status, c.last_contact, safety.scrub(c.how_met),
                     safety.scrub(c.next_step) or None, c.next_date, json.dumps(sorted(set(c.opportunity_ids))),
                     json.dumps(sorted(set(c.can_help_ids))), origin))
                added.append({"id": cid, "name": name})
            else:
                cid = cur["id"]
                theirs = c.last_contact or ""
                newer = theirs >= (cur["last_contact"] or "")
                conn.execute(
                    """UPDATE contacts SET affiliation = ?, status = ?, last_contact = ?, how_met = ?, next_step = ?,
                              next_date = ?, application_ids = ?, network_ids = ? WHERE id = ? AND user_id = ?""",
                    (safety.scrub(c.affiliation) or cur["affiliation"], _pick_status(cur, theirs, c.status),
                     max(filter(None, [cur["last_contact"], c.last_contact]), default=None),
                     cur["how_met"] or safety.scrub(c.how_met),
                     (safety.scrub(c.next_step) or None) if newer and (c.next_step or c.next_date) else cur["next_step"],
                     c.next_date if newer and (c.next_step or c.next_date) else cur["next_date"],
                     json.dumps(sorted(set(json.loads(cur["application_ids"])) | set(c.opportunity_ids))),
                     json.dumps(sorted(set(json.loads(cur["network_ids"])) | set(c.can_help_ids))), cid, user_id))
                updated.append({"id": cid, "name": cur["name"]})
            for e in c.events:
                for app_id in c.opportunity_ids or [None]:
                    res = conn.execute(
                        """INSERT OR IGNORE INTO events (user_id, contact_id, application_id, date, text, evidence,
                                                         source_message_id, source_subject, origin)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (user_id, cid, app_id, e.date, safety.scrub(e.text), safety.scrub(trim(e.evidence, 400)), ref, label, origin))
                    events += res.rowcount
            if c.last_contact:
                for app_id in c.opportunity_ids:
                    conn.execute("""UPDATE applications SET last_contact = ? WHERE id = ? AND user_id = ?
                                    AND (last_contact IS NULL OR last_contact < ?)""", (c.last_contact, app_id, user_id, c.last_contact))
    return {"contacts_added": added, "contacts_updated": updated, "events_added": events}
