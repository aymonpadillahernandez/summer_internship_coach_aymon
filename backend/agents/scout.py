"""Opportunity scout: finds summer internships on the public job boards companies publish for this purpose
(Greenhouse, Lever, Ashby, SmartRecruiters) and on careers pages, judges them against the student's profile, and
answers the Career coach's questions about the student's opportunities from the records it retrieves.

Tools (discovery only): search_job_boards(company) and read_careers_page(url), both capped per run
(MAX_DISCOVER_COMPANIES, MAX_PAGES_PER_RUN, jobboards.MAX_REQUESTS_PER_RUN) and limited to public sources: the four
job-board API hosts, and pages that pass the link reader's checks (public address, robots.txt). It never scrapes
Handshake or LinkedIn. Skills: source policy, MBA summer eligibility, reading a posting, fit rubric (in its instructions).
Everything it returns is typed and goes through the Records keeper: a posting must quote what a tool returned in
this run, and its link must be one of the links the tools returned.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from pydantic_ai import Agent, NativeOutput, RunContext

import config
import db
import jobboards
import retrieval
import safety
import web
from agents import skills
from agents.models import DiscoveryReport, ScoutIntake, SpecialistAnswer, trim
from agents.runtime import CoachRun, limits, prompt, run_agent

NAME = "scout"


@lru_cache(maxsize=1)
def consult_agent() -> Agent:
    return Agent(config.build_model(), output_type=NativeOutput(SpecialistAnswer), instructions=prompt("scout_consult"),
                 model_settings=config.MODEL_SETTINGS, retries=config.OUTPUT_RETRIES, defer_model_check=True)


def _profile(user_id: int) -> str:
    return db.get_profile(user_id)[:1200] or "(no profile yet)"


async def consult(run: CoachRun, user_id: int, question: str) -> dict:
    """Answer the strategist from the top-k retrieved opportunity records; cited ids are checked in code."""
    records = retrieval.urgency_order(retrieval.opportunity_records(user_id), user_id)
    picked = retrieval.search(records, question, config.RETRIEVAL_TOP_K)
    allowed = {rid for rid, _ in picked} | {f"CON-{c['id']}" for c in db.list_contacts(user_id)}
    block = "\n".join(text for _, text in picked) or "(no opportunities yet)"
    user_prompt = (f"Today is {date.today():%A %Y-%m-%d}.\nStudent profile:\n{_profile(user_id)}\n\n"
                   f"Question from the Career coach: {question}\n\n"
                   + safety.wrap_untrusted(block, f"student records: {len(picked)} of {len(records)} opportunities"))
    run.step(NAME, "searching", f"Read {len(picked)} of {len(records)} opportunity records (BM25)",
             records=[rid for rid, _ in picked])
    answer = await run_agent(run, NAME, consult_agent(), user_prompt, timeout=config.SPECIALIST_TIMEOUT_SECONDS)
    return checked_answer(answer, allowed)


def checked_answer(answer: SpecialistAnswer | None, allowed: set[str]) -> dict:
    if answer is None:
        return {"answer": "The specialist could not answer this time.", "findings": [], "unknowns": [], "dropped_ids": []}
    dropped = []
    findings = []
    for f in answer.findings[:6]:
        good = [i for i in f.record_ids if i in allowed]
        dropped += [i for i in f.record_ids if i not in allowed]
        findings.append({"statement": trim(f.statement, 300), "record_ids": good})
    return {"answer": trim(answer.answer, 900), "findings": findings, "unknowns": [trim(u, 200) for u in answer.unknowns[:4]],
            "dropped_ids": dropped}


def compact(result: dict) -> str:
    return json.dumps({k: v for k, v in result.items() if k != "dropped_ids"}, ensure_ascii=False, separators=(",", ":"))


# ─── Discovery: public job boards and careers pages ─────────────────────
@dataclass
class DiscoverDeps:
    run: CoachRun
    user_id: int
    budget: jobboards.Budget = field(default_factory=jobboards.Budget)
    searched: set[str] = field(default_factory=set)
    pages: int = 0
    returned: list[str] = field(default_factory=list)  # everything the tools returned: the source postings must quote
    readable: dict[str, str] = field(default_factory=dict)  # links it may open (normalised -> as given): job boards, student's records
    board_links: set[str] = field(default_factory=set)  # links the boards returned: a saved posting must use one of these
    allowed: set[str] = field(default_factory=set)  # the organisations the student asked about


def _norm_url(url: str) -> str:
    return (url or "").strip().split("#")[0].rstrip("/").lower()


def _record_links(user_id: int) -> dict[str, str]:
    """Links the student gave (a careers page they linked, a posting they pasted), not ones discovery saved."""
    links: dict[str, str] = {}
    for a in db.list_applications(user_id):
        if a.get("origin") != "job_board":
            for k in ("source_url", "verified_url"):
                u = (a.get(k) or "").strip()
                if u.startswith(("http://", "https://")):
                    links[_norm_url(u)] = u
    return links


def _posting_block(p: dict) -> str:
    return (f"[{p['source']}] {p['company']} — {p['title']} — {p['location'] or 'location not stated'} — "
            f"updated {p['updated'] or 'n/a'}\n{p['url']}\n{p['text']}")


async def search_job_boards(ctx: RunContext[DiscoverDeps], company: str) -> str:
    """Search one organisation's public job board (Greenhouse, Lever, Ashby or SmartRecruiters) for internship
    postings. One organisation per call; call several in the same turn."""
    d = ctx.deps
    key = company.strip().lower()
    if key not in d.allowed:  # text from a posting cannot make it look up anything else
        d.run.step(NAME, "search_refused", f"Not one of the organisations asked about: {company[:80]}")
        return f"{company} is not one of the organisations the student asked about."
    if key in d.searched:
        return f"{company} was already searched in this run."
    if len(d.searched) >= config.MAX_DISCOVER_COMPANIES:
        d.run.step(NAME, "search_refused", f"Cap of {config.MAX_DISCOVER_COMPANIES} organisations per run reached")
        return f"Limit reached ({config.MAX_DISCOVER_COMPANIES} organisations per run). Report what you found."
    d.searched.add(key)
    result = await jobboards.search(company.strip()[:80], d.budget)
    if not result["board"] and not result["tried"]:
        d.run.step(NAME, "search_refused", f"{company}: not searched, the run's job-board request budget is spent")
        return f"{company} was NOT searched: the job-board request budget for this run is spent. Do not report it as not found."
    postings = [p for p in result["postings"] if jobboards.is_internship(p["title"], p["text"])]
    d.run.step(NAME, "searched_job_board", f"{company}: " + (f"{len(postings)} internship posting(s) on {result['board']} (board found by its name)"
               if result["board"] else "no public job board found"), board=result["board"])
    if not postings:
        return (f"No internship posting found for {company} on a public job board (tried: {', '.join(result['tried'][:6]) or 'none'}). "
                "Put it in not_found.")
    postings = [{**p, "text": p["text"][: config.DISCOVER_POSTING_CHARS]} for p in postings]
    block, flagged = safety.quarantine("\n\n".join(_posting_block(p) for p in postings))  # postings are untrusted text too
    if flagged:
        d.run.step("shield", "instructions_quarantined", f"{len(flagged)} instruction-like line(s) removed from {company}'s postings",
                   lines=flagged[:5])
    d.returned.append(block)
    links = {_norm_url(p["url"]) for p in postings if p.get("url")}
    d.readable.update({_norm_url(p["url"]): p["url"] for p in postings if p.get("url")})
    d.board_links.update(links)
    note = (f"The board {result['board']} was found by guessing from the name. If these postings are not from {company}, "
            "put it in not_found instead.\n\n")
    return safety.wrap_untrusted(note + block, f"{company} job board: {len(postings)} internship postings")


async def read_careers_page(ctx: RunContext[DiscoverDeps], url: str) -> str:
    """Read one careers or posting page: a link a job board returned in this run, or one already in the student's
    records (the reader also checks the address and respects robots.txt)."""
    d = ctx.deps
    allowed = d.readable.get(_norm_url(url))
    if allowed is None:  # a link invented by the model, or planted in a posting, could carry data out
        d.run.step(NAME, "page_not_allowed", f"Not a link from the job boards or the student's records: {url[:120]}")
        return "Only links returned by the job boards in this run, or saved in the student's records, can be read."
    if d.pages >= config.MAX_PAGES_PER_RUN:
        d.run.step(NAME, "page_refused", f"Cap of {config.MAX_PAGES_PER_RUN} pages per run reached")
        return f"Limit reached ({config.MAX_PAGES_PER_RUN} pages per run). Report what you found."
    d.pages += 1
    try:
        final, raw = await asyncio.to_thread(web.fetch, allowed)  # the link exactly as it was given, not the model's copy
    except web.FetchError as e:
        d.run.step(NAME, "page_not_read", f"{url[:120]}: {e}")
        return f"Could not read that page: {e}"
    text, hidden = safety.visible_text(raw) if safety.looks_like_html(raw) else (raw, [])
    text, flagged = safety.quarantine(text)
    text = f"{text[:12000]}\n\nSource page: {final}"
    d.returned.append(text)
    d.run.step(NAME, "read_page", f"Read {final[:160]}" + (f" ({len(hidden)} hidden snippet(s) removed)" if hidden else "")
               + (f" ({len(flagged)} instruction-like line(s) quarantined)" if flagged else ""))
    return safety.wrap_untrusted(text, f"careers page {final[:100]}")


@lru_cache(maxsize=1)
def discover_agent() -> Agent:
    return Agent(config.build_model(), deps_type=DiscoverDeps, output_type=NativeOutput(DiscoveryReport),
                 instructions=f"{prompt('scout_discover')}\n\n{skills.inject(NAME)}",
                 tools=[search_job_boards, read_careers_page], model_settings=config.MODEL_SETTINGS,
                 retries=config.OUTPUT_RETRIES, defer_model_check=True)


async def discover(run: CoachRun, user_id: int, companies: list[str]) -> tuple[DiscoveryReport | None, str]:
    """(report, source text the tools returned). The Records keeper checks the report against that source.
    Code then keeps only postings whose link a board returned, and never takes a pipeline status from a board."""
    names = list(dict.fromkeys(c.strip() for c in companies if c.strip()))[: config.MAX_DISCOVER_COMPANIES]
    deps = DiscoverDeps(run, user_id, readable=_record_links(user_id), allowed={n.lower() for n in names})
    user_prompt = (f"Today is {date.today():%A %Y-%m-%d}.\n\nStudent profile:\n{_profile(user_id)}\n\n"
                   f"Organisations to search ({len(names)}): {', '.join(names)}")
    run.step(NAME, "discovering", f"Looking for summer internships at {len(names)} organisation(s) on public job boards")
    report = await run_agent(run, NAME, discover_agent(), user_prompt, deps=deps, timeout=config.DISCOVER_TIMEOUT_SECONDS,
                             usage_limits=limits(config.DISCOVER_REQUEST_LIMIT, config.DISCOVER_TOOL_CALLS_LIMIT,
                                                 config.DISCOVER_TOTAL_TOKENS_LIMIT))
    if report is not None:
        kept = []
        for o in report.opportunities:
            o.status_signal = "none"  # a public job board cannot know where the student's own application stands
            o.match_id = None  # it was never shown the student's cards: the keeper matches by organisation + role
            if _norm_url(o.url) in deps.board_links:
                kept.append(o)
            else:
                run.step(NAME, "link_not_from_board", f"Dropped {o.company} — {o.role}: its link was not one a job board returned")
        report.opportunities = kept
    return report, "\n\n".join(deps.returned)
