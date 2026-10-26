"""Records keeper (code, not an AI agent: zero tokens, and the same result every time). It is the only part of the
app that writes the cards on the Opportunities, Networking and Action plan boards.

Agents only propose. The Inbox organizer and the Opportunity scout return typed reports; the keeper then
1. checks each item against its source (merge.validate_*): quotes must appear in the text, people's names must be in
   it, links must be in it, record ids must be the student's own. Anything else is rejected with its reason;
2. writes what survived with the merge rules from the author's tracker (merge.apply_*): one card per organisation +
   role and per person, newer evidence decides, older evidence never moves a card back, the student's own moves win,
   a fit is only re-judged by a posting or a page;
3. re-runs the data checks (checks.run) so a stage never disagrees with its own dates, and reports what needs attention.
The Action plan is derived from these records in code (frontend/src/actions.ts), so it always matches them.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import checks
import config
import merge
import safety
import web
from agents.models import NetworkIntake, ScoutIntake
from agents.runtime import CoachRun

NAME = "keeper"


def keep(run: CoachRun, user_id: int, source: str, *, opportunities: ScoutIntake | None = None,
         people: NetworkIntake | None = None, origin_opportunities: str = "posting", origin_people: str = "chat",
         ref: str = "", label: str = "", page_url: str | None = None, refit: bool = False) -> dict:
    saved: dict = {}
    rejected: list[dict] = []
    not_found: list[str] = []
    if opportunities is not None:
        good, bad = merge.validate_scout(opportunities, source, user_id)
        if good.opportunities or good.leads:
            saved.update(merge.apply_scout(user_id, good, origin_opportunities, ref, label, page_url, refit=refit))
        rejected += bad
        not_found += good.fields_not_found
    if people is not None:
        good, bad = merge.validate_network(people, source, user_id)
        if good.contacts:
            saved.update(merge.apply_network(user_id, good, origin_people, ref, label))
        rejected += bad
        not_found += good.fields_not_found
    issues = checks.run(user_id)
    counts = {k: (len(v) if isinstance(v, list) else v) for k, v in saved.items()}
    wrote = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items() if v) or "nothing new"
    run.step(NAME, "kept", f"Checked and saved: {wrote}; {len(rejected)} rejected; {len(issues)} record(s) need attention",
             issues=len(issues))
    return {"saved": saved, "rejected": rejected, "fields_not_found": not_found}


# ─── Web results: read each page, keep only what it really says ─────────
BLOCKED_HOSTS = ("linkedin.com", "joinhandshake.com", "12twenty.com", "symplicity.com")  # their terms forbid automated reading


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _read(url: str) -> tuple[str, str | None]:
    """(page text, why it could not be used). Uses the link reader's guards: public addresses only, robots.txt."""
    host = _host(url)
    if not url.startswith(("http://", "https://")) or not host:
        return "", "not a web link"
    if any(host == b or host.endswith("." + b) for b in BLOCKED_HOSTS):
        return "", f"{host} does not allow automated reading"
    try:
        final, raw = web.fetch(url)
    except web.FetchError as e:
        return "", str(e)
    text, _hidden = safety.visible_text(raw) if safety.looks_like_html(raw) else (raw, [])
    text, _flagged = safety.quarantine(text)
    return f"{text}\n\nSource page: {url}", None


def page_sentence(text: str, words: list[str]) -> str:
    """A real sentence or line from the page that contains all the given words (used when the model paraphrased)."""
    words = [safety.norm(w) for w in words if len(w) >= 3][:4]
    if not words:
        return ""
    import re as _re
    for chunk in _re.split(r"(?<=[.!?])\s+|\n+", text):
        chunk = chunk.strip()
        if 12 <= len(chunk) <= 400 and all(w in safety.norm(chunk) for w in words):
            return chunk
    return ""


def key_words(item) -> list[str]:
    """What a confirming sentence must contain: a person's name, or the distinctive words of a role."""
    if getattr(item, "name", None):
        return item.name.split()
    generic = {"summer", "intern", "internship", "associate", "program", "role", "2027", "2026", "the", "and", "for"}
    return [w for w in safety.norm(getattr(item, "role", "")).replace(",", " ").split() if len(w) >= 4 and w not in generic][:2] \
        or [w for w in safety.norm(getattr(item, "role", "")).split() if len(w) >= 4][:2]


async def verify_web(run, items: list, *, must_contain: callable) -> tuple[list[tuple[object, str]], list[dict]]:
    """Read the page of each web result (at most MAX_VERIFY_PAGES) and keep it only if the page contains its exact quote
    and what must_contain(item) lists (e.g. the company, the person's name). Returns ([(item, page text)], [rejected])."""
    items = items[: config.MAX_VERIFY_PAGES]
    pages = await asyncio.gather(*(asyncio.to_thread(_read, i.url.strip()) for i in items))
    kept, rejected = [], []
    for item, (text, problem) in zip(items, pages):
        norm = safety.norm(text)
        if problem:
            rejected.append({"item": getattr(item, "company", None) or getattr(item, "name", ""), "url": item.url, "reason": problem})
        elif not safety.in_source(item.quote, norm) and not page_sentence(text, key_words(item)):
            rejected.append({"item": getattr(item, "company", None) or getattr(item, "name", ""), "url": item.url,
                             "reason": "the page does not show it"})
        elif not all(safety.name_in_source(x, norm) for x in must_contain(item) if x):
            rejected.append({"item": getattr(item, "company", None) or getattr(item, "name", ""), "url": item.url,
                             "reason": "the page does not name it"})
        else:
            if not safety.in_source(item.quote, norm):  # the model paraphrased: quote the page itself instead
                item.quote = page_sentence(text, key_words(item))
            kept.append((item, text))
    run.step(NAME, "verified_web", f"Read {len(items)} source page(s): {len(kept)} confirmed, {len(rejected)} not confirmed",
             rejected=rejected[:6])
    return kept, rejected
