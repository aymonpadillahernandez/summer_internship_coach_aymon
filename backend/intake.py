"""Paste / upload intake: how scattered information gets into the student's records without manual CRM work.

1. Shield (code): HTML is reduced to what a person would see (hidden text removed and listed); lines that read
   like instructions to an AI are quarantined (removed before any model sees them, and shown to the student).
2. Router (code, zero tokens): job posts and careers pages go to the Opportunity scout; conversations, chat
   exports and contact lists go to Network intelligence; a text with both signals goes to both, in parallel.
3. The specialist(s) extract typed records with exact quotes.
4. Validation (code): quotes, names, links and ids are checked against the pasted text and the student's own data;
   anything unsupported is rejected and reported with its reason.
5. Merge (code): the tracker's merge rules write what survived.
The pasted text itself is not stored: only the quotes that back each saved fact.
"""

from __future__ import annotations

import asyncio
import csv
import io
import re

import config
import db
import merge
import safety
from agents import network, scout
from agents.runtime import CoachRun, ModelSubstituted

POSTING = re.compile(r"\b(apply|application|deadline|internship|intern|qualifications?|responsibilit(y|ies)|requirements?|"
                     r"posting|job description|role overview|eligib|program|candidates?|compensation|summer associate)\b", re.I)
CONVERSATION = re.compile(r"(^\[?\d{1,2}[/.]\d{1,2}[/.]\d{2,4},?\s+\d{1,2}:\d{2}|^from:|^to:|^subject:|\bwrote:|^\s*(hi|hey|dear|hola)\b|"
                          r"\b(thanks|thank you|best,|cheers|coffee|catch up|intro(duce|duction)?|connect you|great (chatting|speaking)|"
                          r"call|zoom|reply|let me know)\b)", re.I | re.M)
LINKEDIN_CSV = re.compile(r"^\s*first name\s*,\s*last name\s*,", re.I | re.M)


def is_linkedin_export(text: str) -> bool:
    return bool(LINKEDIN_CSV.search(text[:3000]))


def filter_linkedin(text: str, user_id: int) -> tuple[str, int, int]:
    """Keep only connections at organisations the student tracks, and only name, company, position and date
    (profile URLs and email columns never reach the model). Zero tokens. Returns (csv text, kept, total)."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if LINKEDIN_CSV.match(line))
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))
    tracked = [a["company"].lower().strip() for a in db.list_applications(user_id) if len(a["company"].strip()) >= 3]

    def at_tracked(company: str) -> bool:
        c = (company or "").lower().strip()
        return len(c) >= 3 and any(c in t or t in c for t in tracked)

    kept = [r for r in rows if at_tracked(r.get("Company", ""))][: config.LINKEDIN_MAX_ROWS]
    out = io.StringIO()
    cols = ["First Name", "Last Name", "Company", "Position", "Connected On"]
    writer = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows({k: (r.get(k) or "").strip() for k in cols} for r in kept)
    return out.getvalue(), len(kept), len(rows)


def route_for(text: str, kind: str) -> list[str]:
    if kind == "opportunity":
        return ["scout"]
    if kind == "conversation":
        return ["network"]
    if LINKEDIN_CSV.search(text[:2000]):
        return ["network"]
    posting, convo = len(POSTING.findall(text)), len(CONVERSATION.findall(text))
    if posting >= 3 and convo >= 3:
        return ["scout", "network"]
    return ["scout"] if posting > convo else ["network"]


ORIGIN = {"scout": "posting", "network": "chat"}


async def process(user_id: int, text: str, kind: str, label: str, page_url: str | None = None) -> dict:
    """page_url: set when the text is a page the app fetched from a link the student gave (web.fetch)."""
    run = CoachRun(user_id, "intake")
    label = (label or "Pasted text").strip()[:80]
    if page_url:
        run.step("router", "page_fetched", f"Read the page you linked: {page_url[:200]}")
    hidden: list[str] = []
    if safety.looks_like_html(text):
        text, hidden = safety.visible_text(text)
        run.step("shield", "hidden_text_removed" if hidden else "html_cleaned",
                 f"{len(hidden)} hidden snippet(s) removed from the page" if hidden else "Page reduced to its visible text",
                 hidden=hidden[:5])
    if is_linkedin_export(text):
        text, kept, total = filter_linkedin(text, user_id)
        run.step("router", "export_filtered", f"LinkedIn export: kept {kept} of {total} connections, those at organisations "
                 "you track (name, company, position, date only)")
        if kept == 0:
            return {**run.finish("ok", "LinkedIn export: no connections at tracked organisations"), "routes": [],
                    "flagged": [], "hidden": [], "saved": {}, "rejected": [],
                    "fields_not_found": ["None of these connections work at an organisation you track yet. Add opportunities first."]}
    if page_url:
        text = f"{text}\n\nSource page: {page_url}"  # so the posting's link is backed by the source text
    text, flagged = safety.quarantine(text)
    if flagged:
        run.step("shield", "instructions_quarantined",
                 f"{len(flagged)} line(s) read like instructions to an AI and were removed before any model saw them",
                 lines=flagged[:5])
    routes = ["scout"] if page_url and kind == "auto" else route_for(text, kind)
    run.step("router", "routed", "Sent to " + " and ".join({"scout": "Opportunity scout", "network": "Network intelligence"}[r] for r in routes))

    ref = merge.source_ref(text)
    jobs = [scout.intake(run, user_id, text, label) if r == "scout" else network.intake(run, user_id, text, label) for r in routes]
    try:
        outputs = await asyncio.gather(*jobs)
    except ModelSubstituted as e:
        return {**run.finish("model_rejected", str(e)), "routes": routes, "flagged": flagged, "hidden": hidden,
                "saved": {}, "rejected": [], "fields_not_found": []}

    saved: dict = {}
    rejected: list[dict] = []
    not_found: list[str] = []
    origin = "linkedin" if LINKEDIN_CSV.search(text[:2000]) else None
    for route, out in zip(routes, outputs):
        if out is None:
            continue
        if route == "scout":
            good, bad = merge.validate_scout(out, text, user_id)
            saved.update(merge.apply_scout(user_id, good, origin or ORIGIN[route], ref, label, page_url))
        else:
            good, bad = merge.validate_network(out, text, user_id)
            saved.update(merge.apply_network(user_id, good, origin or ORIGIN[route], ref, label))
        rejected += bad
        not_found += good.fields_not_found
    if rejected:
        run.step("shield", "rejected_unsupported", f"{len(rejected)} item(s) rejected: not backed by the pasted text",
                 items=rejected[:6])
    counts = {k: (len(v) if isinstance(v, list) else v) for k, v in saved.items()}
    summary = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items() if v) or "nothing new"
    status = "ok" if any(o is not None for o in outputs) else "failed"
    return {**run.finish(status, f"Intake “{label}”: {summary}"), "routes": routes, "flagged": flagged, "hidden": hidden,
            "saved": saved, "rejected": rejected, "fields_not_found": not_found[:8]}
