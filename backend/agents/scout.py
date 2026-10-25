"""Opportunity scout: turns a pasted posting / careers page / email into opportunity records, and answers the
strategist's questions about the student's opportunities from the records it retrieves.

Tools: none that reach outside. It reads only (a) the pasted text it is handed and (b) the BM25-retrieved records.
Its output is typed (agents/models.py) and validated in code (merge.validate_scout) before anything is saved.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache

from pydantic_ai import Agent, NativeOutput

import config
import db
import retrieval
import safety
from agents.models import ScoutIntake, SpecialistAnswer, trim
from agents.runtime import CoachRun, prompt, run_agent

NAME = "scout"


@lru_cache(maxsize=1)
def intake_agent() -> Agent:
    return Agent(config.build_model(), output_type=NativeOutput(ScoutIntake), instructions=prompt("scout_intake"),
                 model_settings=config.MODEL_SETTINGS, retries=config.OUTPUT_RETRIES, defer_model_check=True)


@lru_cache(maxsize=1)
def consult_agent() -> Agent:
    return Agent(config.build_model(), output_type=NativeOutput(SpecialistAnswer), instructions=prompt("scout_consult"),
                 model_settings=config.MODEL_SETTINGS, retries=config.OUTPUT_RETRIES, defer_model_check=True)


def _profile(user_id: int) -> str:
    return db.get_profile(user_id)[:1200] or "(no profile yet)"


async def intake(run: CoachRun, user_id: int, text: str, label: str) -> ScoutIntake | None:
    stage = {s["key"]: s["label"] for s in db.STAGES}
    current = [f"{a['id']} · {a['company']} · {a['role']} · {stage.get(a['status'], a['status'])} · {a['deadline'] or 'no deadline'}"
               for a in db.list_applications(user_id)]
    user_prompt = (f"Today is {date.today():%A %Y-%m-%d}.\n\nStudent profile:\n{_profile(user_id)}\n\n"
                   f"Current opportunities:\n" + ("\n".join(current) or "(none yet)") + "\n\n"
                   + safety.wrap_untrusted(text, label))
    run.step(NAME, "reading", f"Reading “{label}” for opportunities and deadlines")
    return await run_agent(run, NAME, intake_agent(), user_prompt)


async def consult(run: CoachRun, user_id: int, question: str) -> dict:
    """Answer the strategist from the top-k retrieved opportunity records; cited ids are checked in code."""
    records = retrieval.urgency_order(retrieval.opportunity_records(user_id), user_id)
    picked = retrieval.search(records, question, config.RETRIEVAL_TOP_K)
    allowed = {rid for rid, _ in picked} | {f"CON-{c['id']}" for c in db.list_contacts(user_id)}
    block = "\n".join(text for _, text in picked) or "(no opportunities yet)"
    user_prompt = (f"Today is {date.today():%A %Y-%m-%d}.\nStudent profile:\n{_profile(user_id)}\n\n"
                   f"Question from the Career strategist: {question}\n\n"
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
