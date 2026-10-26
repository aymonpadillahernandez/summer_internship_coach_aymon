"""Inbox organizer: reads ONE text from any channel (email, chat export, Messages, WhatsApp, Slack, LinkedIn export,
calendar invite, job posting, careers page, coffee-chat notes) and extracts opportunities, leads and people in one pass.

It replaced the two intake modes the Opportunity scout and Network intelligence used to have: one model call per
text instead of up to two in parallel, and one agent that sees both sides (e.g. a recruiter's email that is also a
posting). The router (code, zero tokens) still decides the focus hint and which channel it is.

Tools: none that reach outside. Skills: its reading guides (email, chat, LinkedIn export, posting, calendar invite)
and the stage definitions are part of its instructions (a byte-stable prefix the provider can cache).
Its output is typed (InboxReport) and nothing is written until the Records keeper (keeper.py) has checked it.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from pydantic_ai import Agent, NativeOutput

import config
import db
import safety
from agents import skills
from agents.models import InboxReport
from agents.runtime import CoachRun, prompt, run_agent

NAME = "inbox"
FOCUS = {"scout": "opportunities", "network": "people"}


@lru_cache(maxsize=1)
def agent() -> Agent:
    return Agent(config.build_model(), output_type=NativeOutput(InboxReport),
                 instructions=f"{prompt('inbox')}\n\n{skills.inject(NAME)}", model_settings=config.MODEL_SETTINGS,
                 retries=config.OUTPUT_RETRIES, defer_model_check=True)


def focus_of(routes: list[str]) -> str:
    return "both" if len(routes) > 1 else FOCUS.get(routes[0], "both")


async def read(run: CoachRun, user_id: int, text: str, label: str, routes: list[str]) -> InboxReport | None:
    stage = {s["key"]: s["label"] for s in db.STAGES}
    net = {s["key"]: s["label"] for s in db.NETWORK_STAGES}
    apps = [f"{a['id']} · {a['company']} · {a['role']} · {stage.get(a['status'], a['status'])} · {a['deadline'] or 'no deadline'}"
            for a in db.list_applications(user_id)]
    people = [f"{c['id']} · {c['name']} · {c['affiliation']} · {net.get(c['status'], c['status'])}" for c in db.list_contacts(user_id)]
    focus = focus_of(routes)
    user_prompt = (f"Today is {date.today():%A %Y-%m-%d}.\n\nStudent profile:\n{db.get_profile(user_id)[:1200] or '(no profile yet)'}\n\n"
                   "Opportunities:\n" + ("\n".join(apps) or "(none yet)") + "\n\nContacts:\n" + ("\n".join(people) or "(none yet)")
                   + f"\n\nFocus: {focus}\n\n" + safety.wrap_untrusted(text, label))
    run.step(NAME, "reading", f"Reading “{label}” for opportunities, people and dates (focus: {focus})")
    return await run_agent(run, NAME, agent(), user_prompt)
