"""Paste / upload intake: how scattered information gets into the student's records without manual CRM work.

1. Shield (code): HTML is reduced to what a person would see (hidden text removed and listed); lines that read
   like instructions to an AI are quarantined (removed before any model sees them, and shown to the student).
2. Router (code, zero tokens): decides what the text is about (opportunities, people or both) and which channel it
   came from, and filters exports (LinkedIn) before any model sees them.
3. The Inbox organizer (one model call) extracts typed opportunities, leads and people with exact quotes.
4. The Records keeper (code) checks every quote, name, link and id against the text and the student's own data,
   rejects what is unsupported (with its reason), writes the rest with the merge rules and re-runs the data checks.
The pasted text itself is not stored: only the quotes that back each saved fact.
"""

from __future__ import annotations

import csv
import io
import re

import config
import db
import merge
import safety
import signals
import keeper
from agents import inbox
from agents.runtime import CoachRun, ModelSubstituted

POSTING = re.compile(r"\b(apply|application|deadline|internship|intern|qualifications?|responsibilit(y|ies)|requirements?|"
                     r"posting|job description|role overview|eligib|program|candidates?|compensation|summer associate)\b", re.I)
CONVERSATION = re.compile(r"(^\[?\d{1,2}[/.]\d{1,2}[/.]\d{2,4},?\s+\d{1,2}:\d{2}|^from:|^to:|^subject:|\bwrote:|^\s*(hi|hey|dear|hola)\b|"
                          r"\b(thanks|thank you|best,|cheers|coffee|catch up|intro(duce|duction)?|connect you|great (chatting|speaking)|"
                          r"call|zoom|reply|let me know)\b)", re.I | re.M)
LINKEDIN_CSV = re.compile(r"^\s*first name\s*,\s*last name\s*,", re.I | re.M)
LINKEDIN_MESSAGES = re.compile(r"^\s*conversation id\s*,", re.I | re.M)  # messages.csv from "Download your data"
MESSAGES_BUDGET_CHARS = 18_000  # what Network intelligence may read from one LinkedIn messages file


def is_linkedin_export(text: str) -> bool:
    head = text[:3000]
    return bool(LINKEDIN_CSV.search(head) or LINKEDIN_MESSAGES.search(head))


def filter_linkedin_messages(text: str, user_id: int) -> tuple[str, int, int]:
    """Keep only LinkedIn conversations with the student's people, about their organisations, or about recruiting;
    newest first, within MESSAGES_BUDGET_CHARS; profile URLs never reach the model. Zero tokens.
    Returns (text, conversations kept, conversations in the file)."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if LINKEDIN_MESSAGES.match(line))
    rows = [{k.strip().upper(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(io.StringIO("\n".join(lines[start:])))]
    ctx = signals.context(user_id)
    people = [signals.norm(p) for p in ctx["people"] if len(p) >= 4]
    topic = signals.topic_regex(ctx["organisations"])
    convs: dict[str, list[dict]] = {}
    for r in rows:
        convs.setdefault(r.get("CONVERSATION ID") or r.get("CONVERSATION TITLE", ""), []).append(r)

    def relevant(msgs: list[dict]) -> bool:
        names = signals.norm(" ".join(m.get("FROM", "") + " " + m.get("TO", "") for m in msgs))
        body = " ".join(m.get("SUBJECT", "") + " " + m.get("CONTENT", "") for m in msgs)
        if signals.AUTOMATED.search(body):
            return False
        return any(p in names for p in people) or bool(topic.search(body))

    kept = sorted((m for m in convs.values() if relevant(m)), key=lambda m: max(x.get("DATE", "") for x in m), reverse=True)
    out, used, n = [], 0, 0
    for msgs in kept:
        block = [f"Conversation: {msgs[0].get('CONVERSATION TITLE') or 'LinkedIn messages'}"]
        for m in sorted(msgs, key=lambda x: x.get("DATE", "")):
            content = re.sub(r"<[^>]+>", " ", m.get("CONTENT", ""))
            block.append(f"[{m.get('DATE', '')}] {m.get('FROM', '')} → {m.get('TO', '')}: {m.get('SUBJECT', '')} {content}".strip())
        piece = "\n".join(block) + "\n"
        if used + len(piece) > MESSAGES_BUDGET_CHARS:
            break
        out.append(piece)
        used += len(piece)
        n += 1
    return "\n".join(out), n, len(convs)


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
    linkedin = is_linkedin_export(text)
    if linkedin and LINKEDIN_MESSAGES.search(text[:3000]):
        text, kept, total = filter_linkedin_messages(text, user_id)
        run.step("router", "export_filtered", f"LinkedIn messages: kept {kept} of {total} conversations, those with your people, "
                 "about your organisations or about recruiting (no profile links)")
        if kept == 0:
            return {**run.finish("ok", "LinkedIn messages: nothing relevant"), "routes": [], "flagged": [], "hidden": [],
                    "saved": {}, "rejected": [], "fields_not_found": ["No conversation in this file is with your people, about your "
                                                                      "organisations or about recruiting."]}
        kind = "conversation"
    elif linkedin:
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
    run.step("router", "routed", f"Sent to the Inbox organizer (focus: {inbox.focus_of(routes)})")

    ref = merge.source_ref(text)
    try:
        report = await inbox.read(run, user_id, text, label, routes)
    except ModelSubstituted as e:
        return {**run.finish("model_rejected", str(e)), "routes": ["inbox"], "flagged": flagged, "hidden": hidden,
                "saved": {}, "rejected": [], "fields_not_found": []}
    outputs = [report]
    origin = "linkedin" if linkedin else None
    kept = keeper.keep(run, user_id, text, ref=ref, label=label, page_url=page_url,
                       opportunities=report.scout_part() if report else None,
                       people=report.network_part() if report and inbox.focus_of(routes) != "opportunities" else None,
                       origin_opportunities=origin or ORIGIN["scout"], origin_people=origin or ORIGIN["network"],
                       refit=bool(page_url) or routes == ["scout"]) if report else {"saved": {}, "rejected": [], "fields_not_found": []}
    saved, rejected, not_found = kept["saved"], kept["rejected"], kept["fields_not_found"]
    routes = ["inbox"]
    if rejected:
        run.step("shield", "rejected_unsupported", f"{len(rejected)} item(s) rejected: not backed by the pasted text",
                 items=rejected[:6])
    counts = {k: (len(v) if isinstance(v, list) else v) for k, v in saved.items()}
    summary = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items() if v) or "nothing new"
    status = "ok" if any(o is not None for o in outputs) else "failed"
    return {**run.finish(status, f"Intake “{label}”: {summary}"), "routes": routes, "flagged": flagged, "hidden": hidden,
            "saved": saved, "rejected": rejected, "fields_not_found": not_found[:8]}
