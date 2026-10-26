"""Setup guide: the first step of a new account. It walks the student, one step at a time, through connecting or
exporting every channel (the Setup page), checking what is already in.

Tools: connection_status() and next_setup_step() read the student's own setup state (zero tokens to compute), and
load_skill(name) opens one channel's playbook (backend/skills/guide/). It cannot click, create keys, read accounts or
send anything: it tells the student what to do.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from pydantic_ai import Agent, RunContext

import config
import db
from agents import skills
from agents.runtime import CoachRun, prompt, run_agent

NAME = "guide"


@dataclass
class GuideDeps:
    run: CoachRun
    user_id: int


def status(user_id: int) -> dict:
    """What the student has set up so far (shared with the Setup page's checklist)."""
    apps, people = db.list_applications(user_id), db.list_contacts(user_id)
    syncs = {s["channel"]: s for s in db.list_syncs(user_id)}
    keys = [k for k in db.list_connector_keys(user_id) if not k.get("revoked_at")]
    # people keep their channel in contacts.source (merge.apply_network); opportunities in applications.origin
    origins = Counter(c.get("source") or "note" for c in people) + Counter(a.get("origin") or "manual" for a in apps)
    channel = lambda c: ({"connected": True, "working": bool(syncs[c]["ok"]), "auto_sync": bool(syncs[c]["auto_minutes"]),  # noqa: E731
                          "last": syncs[c]["synced_at"], "summary": syncs[c]["summary"]} if c in syncs else {"connected": False})
    with db.connect() as conn:
        demo = bool((conn.execute("SELECT is_demo FROM users WHERE id = ?", (user_id,)).fetchone() or [0])[0])
    return {"demo": demo, "profile_filled": len(db.get_profile(user_id).strip()) >= 40, "opportunities": len(apps), "people": len(people),
            "connector_keys": len(keys), "gmail": channel("gmail"), "messages": channel("imessage"), "whatsapp": channel("whatsapp"),
            "records_by_source": dict(origins)}


def working(channel: dict) -> bool:
    """Connected AND its last check could read it (a channel waiting for Full Disk Access is not done)."""
    return bool(channel.get("connected") and channel.get("working"))


def next_step(user_id: int) -> dict:
    """The recommended next setup step, in a fixed order (code, zero tokens)."""
    s = status(user_id)
    steps = [
        (s["profile_filled"], "profile", "Fill in your profile (Profile, top right): target roles, industries, locations, timing."),
        (s["opportunities"] >= 3, "targets", "Add at least 3 target organisations: paste your target list or a posting on Today."),
        (s["connector_keys"] > 0, "connector_key", "Create your connector key on the Setup page (step 1 of the Coach Connector)."),
        (working(s["gmail"]), "gmail", "Connect Gmail with the Coach Connector (an app password, read-only)."),
        (working(s["messages"]), "messages", "Connect Messages on your Mac (Full Disk Access for Terminal)."),
        (working(s["whatsapp"]) or s["records_by_source"].get("chat", 0) > 0, "whatsapp",  # an Export chat upload counts too
         "Bring in WhatsApp: WhatsApp Desktop on your Mac, or upload an Export chat .zip."),
        (s["records_by_source"].get("linkedin", 0) > 0, "linkedin", "Upload LinkedIn's Connections.csv and messages.csv (Download your data)."),
        (any(working(s[c]) and s[c].get("auto_sync") for c in ("gmail", "messages", "whatsapp")), "auto_sync",
         "Turn on auto-sync: python3 ~/coach_connector.py schedule."),
    ]
    done = [key for ok, key, _ in steps if ok]
    nxt = next(((key, what) for ok, key, what in steps if not ok), None)
    return {"done": done, "next": {"key": nxt[0], "what": nxt[1]} if nxt else None, "total": len(steps)}


def connection_status(ctx: RunContext[GuideDeps]) -> str:
    """What the student has already connected or imported (channels, records by source, connector keys, auto-sync)."""
    ctx.deps.run.step(NAME, "checked_status", "Read the student's setup status")
    return json.dumps(status(ctx.deps.user_id), ensure_ascii=False, separators=(",", ":"))


def next_setup_step(ctx: RunContext[GuideDeps]) -> str:
    """The recommended next setup step and the steps already done."""
    return json.dumps(next_step(ctx.deps.user_id), ensure_ascii=False, separators=(",", ":"))


@lru_cache(maxsize=1)
def agent() -> Agent:
    return Agent(config.build_model(), deps_type=GuideDeps, output_type=str,
                 instructions=f"{prompt('guide')}\n\n{skills.catalog_block(NAME)}",
                 tools=[connection_status, next_setup_step, skills.load_skill_tool(NAME)],
                 model_settings=config.MODEL_SETTINGS, retries=config.OUTPUT_RETRIES, defer_model_check=True)


async def ask(run: CoachRun, user_id: int, messages: list[dict]) -> str | None:
    earlier = "\n".join(f"{'Student' if m['role'] == 'user' else 'Guide'}: {m['content'][:1500]}" for m in messages[:-1])
    user_prompt = (f"Today is {date.today():%A %Y-%m-%d}.\n\n" + (f"Earlier in this chat:\n{earlier}\n\n" if earlier else "")
                   + f"Student: {messages[-1]['content']}")
    run.step(NAME, "thinking", messages[-1]["content"][:200])
    return await run_agent(run, NAME, agent(), user_prompt, deps=GuideDeps(run, user_id))
