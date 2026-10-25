"""Career strategist (the boss): decides where the student should spend this week, and answers questions in chat.

It never reads the database directly. It delegates through two tools, each starting a separate specialist run:
  ask_opportunity_scout(question) -> Opportunity scout (retrieves OPP- records)
  ask_network_intel(question)     -> Network intelligence (retrieves CON- records)
and one deterministic tool, get_data_checks(). Delegation is capped at MAX_DELEGATIONS_PER_RUN per request; a call
over the cap returns a refusal as data, so the strategist still finishes.

Plans: it may only rank the candidate actions the app derived from the student's data (the action plan). It sees
them under short aliases (A1, A2, …; measured: the model shortened the app's long keys, which failed validation),
and code maps the aliases back. An output validator rejects any alias that is not in the list and asks again
(ModelRetry); after OUTPUT_RETRIES the code drops what is still invalid. Record ids it cites must have come back
from a specialist in this run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from pydantic_ai import Agent, ModelRetry, NativeOutput, RunContext

import checks
import config
import db
from agents import network, scout
from agents.models import CoachPlan, trim
from agents.runtime import CoachRun, prompt, run_agent

NAME = "strategist"


@dataclass
class StrategistDeps:
    run: CoachRun
    user_id: int
    candidate_keys: set[str]
    seen_ids: set[str] = field(default_factory=set)


async def _delegate(ctx: RunContext[StrategistDeps], to: str, question: str) -> str:
    run = ctx.deps.run
    if run.delegations >= config.MAX_DELEGATIONS_PER_RUN:
        run.step(NAME, "delegation_refused", f"Cap of {config.MAX_DELEGATIONS_PER_RUN} specialist questions reached")
        return (f"Delegation limit reached ({config.MAX_DELEGATIONS_PER_RUN} questions per request). "
                "Answer with the reports you already have.")
    run.delegations += 1
    run.step(NAME, "delegated", question, to=to)
    specialist = scout if to == "scout" else network
    result = await specialist.consult(run, ctx.deps.user_id, question[:600])
    for f in result["findings"]:
        ctx.deps.seen_ids.update(f["record_ids"])
    if result["dropped_ids"]:
        run.step(to, "ids_dropped", f"Removed ids it was not given: {', '.join(result['dropped_ids'][:6])}")
    run.step(to, "answered", result["answer"][:300])
    return scout.compact(result)


async def ask_opportunity_scout(ctx: RunContext[StrategistDeps], question: str) -> str:
    """Ask the Opportunity scout one focused question about the student's opportunities (deadlines, fit,
    eligibility, what is missing). Name the organisations you mean."""
    return await _delegate(ctx, "scout", question)


async def ask_network_intel(ctx: RunContext[StrategistDeps], question: str) -> str:
    """Ask Network intelligence one focused question about the student's people (who can help where,
    relationship strength, follow-ups owed). Name the people or organisations you mean."""
    return await _delegate(ctx, "network", question)


def get_data_checks(ctx: RunContext[StrategistDeps]) -> str:
    """Records whose stage disagrees with their own dates (e.g. a booked call whose date has passed)."""
    found = checks.run(ctx.deps.user_id)
    ctx.deps.run.step(NAME, "checked_data", f"{len(found)} data checks")
    return json.dumps([{k: i[k] for k in ("name", "problem", "fix")} for i in found[:10]], ensure_ascii=False)


TOOLS = [ask_opportunity_scout, ask_network_intel, get_data_checks]


@lru_cache(maxsize=1)
def plan_agent() -> Agent:
    agent = Agent(config.build_model(), deps_type=StrategistDeps, output_type=NativeOutput(CoachPlan),
                  instructions=prompt("strategist_plan"), tools=TOOLS, model_settings=config.MODEL_SETTINGS,
                  retries=config.OUTPUT_RETRIES, defer_model_check=True)

    @agent.output_validator
    def only_candidates(ctx: RunContext[StrategistDeps], plan: CoachPlan) -> CoachPlan:
        bad = [a.key for a in plan.top_actions if a.key.strip() not in ctx.deps.candidate_keys]
        if bad:
            ctx.deps.run.step(NAME, "rejected_invented_action", f"Not in the candidate list: {', '.join(bad[:4])}")
            raise ModelRetry(f"These are not candidate aliases: {bad}. Use only aliases from the list (A1, A2, …).")
        return plan

    return agent


@lru_cache(maxsize=1)
def chat_agent() -> Agent:
    return Agent(config.build_model(), deps_type=StrategistDeps, output_type=str, instructions=prompt("strategist_chat"),
                 tools=TOOLS, model_settings=config.MODEL_SETTINGS, retries=config.OUTPUT_RETRIES, defer_model_check=True)


def _aliases(candidates: list[dict]) -> dict[str, dict]:
    return {f"A{i + 1}": c for i, c in enumerate(candidates)}


def _candidate_lines(aliases: dict[str, dict]) -> str:
    return "\n".join(f"{a} · {c['title']} · due {c.get('due') or 'no date'} · {c.get('why', '')[:140]}"
                     for a, c in aliases.items()) or "(no candidate actions)"


def _pipeline(user_id: int) -> str:
    apps = [a for a in db.list_applications(user_id) if not a.get("not_interested_at")]
    people = [c for c in db.list_contacts(user_id) if not c.get("not_interested_at")]
    by = lambda rows, key: {k: sum(1 for r in rows if r["status"] == k) for k in key}  # noqa: E731
    return (f"Opportunities by stage: {json.dumps(by(apps, db.STAGE_KEYS))}\n"
            f"People by stage: {json.dumps(by(people, db.NETWORK_KEYS))}")


async def plan(run: CoachRun, user_id: int, candidates: list[dict]) -> dict:
    aliases = _aliases(candidates)
    deps = StrategistDeps(run, user_id, set(aliases))
    user_prompt = (f"Today is {date.today():%A %Y-%m-%d}.\n\nStudent profile:\n{db.get_profile(user_id)[:1200] or '(none)'}\n\n"
                   f"{_pipeline(user_id)}\n\nCandidate actions ({len(candidates)}), as alias · what · due · why:\n"
                   f"{_candidate_lines(aliases)}")
    run.step(NAME, "planning", f"Ranking {len(candidates)} candidate actions for this week")
    result: CoachPlan | None = await run_agent(run, NAME, plan_agent(), user_prompt, deps=deps)
    if result is None:
        return {}
    def plain(text: str, n: int) -> str:
        """Aliases are for the model only: shown text names the action instead."""
        named = re.sub(r"\bA(\d{1,2})\b", lambda m: f"“{aliases[m.group(0)]['title']}”" if m.group(0) in aliases else m.group(0), text)
        return trim(named, n)

    actions = []
    for a in result.top_actions[:5]:
        a.why_now, a.how = plain(a.why_now, 300), plain(a.how, 300)
        c = aliases.get(a.key.strip())
        if c is None:
            continue  # still invented after the retries: dropped in code
        ids = [i for i in a.record_ids if i in deps.seen_ids]
        actions.append({**a.model_dump(), "key": c["key"], "record_ids": ids, "title": c["title"],
                        "due": c.get("due"), "subtitle": c.get("subtitle", "")})
    return {"headline": plain(result.headline, 240), "top_actions": actions,
            "can_wait": [aliases[k]["key"] for k in result.can_wait if k in aliases][:8],
            "watch_outs": [plain(w, 300) for w in result.watch_outs[:3]],
            "open_questions": [plain(q, 220) for q in result.open_questions[:3]]}


async def chat(run: CoachRun, user_id: int, messages: list[dict], candidates: list[dict]) -> str | None:
    aliases = _aliases(candidates[:20])
    deps = StrategistDeps(run, user_id, set(aliases))
    earlier = "\n".join(f"{'Student' if m['role'] == 'user' else 'Coach'}: {m['content'][:1500]}" for m in messages[:-1])
    user_prompt = (f"Today is {date.today():%A %Y-%m-%d}.\n\nStudent profile:\n{db.get_profile(user_id)[:1200] or '(none)'}\n\n"
                   f"{_pipeline(user_id)}\n\nOpen actions (top {len(aliases)}):\n{_candidate_lines(aliases)}\n\n"
                   + (f"Earlier in this chat:\n{earlier}\n\n" if earlier else "") + f"Student: {messages[-1]['content']}")
    run.step(NAME, "thinking", messages[-1]["content"][:200])
    return await run_agent(run, NAME, chat_agent(), user_prompt, deps=deps)
