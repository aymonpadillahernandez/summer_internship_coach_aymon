"""Skills: short playbooks an agent opens only when it needs them (backend/skills/<agent>/<name>.md), the course's
skills idea applied inside the app. Line 1 of a skill is its title, line 2 ("> …") says when to use it.

Two ways in, chosen per agent for cost:
- chat agents (Setup guide, Career coach) get a load_skill tool and see only the catalog (name + one line) in their
  instructions; a skill's full text costs tokens only in the turns that need it;
- pipeline agents (Inbox organizer, Opportunity scout, Network intelligence) always need the same few skills, so code
  adds them to the instructions. That keeps the prompt prefix byte-stable, which lets the provider cache it.
An agent may open at most MAX_SKILL_LOADS_PER_RUN skills per request (a refusal comes back as data, not an error).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext

import config

SKILLS = Path(__file__).resolve().parent.parent / "skills"


@lru_cache(maxsize=None)
def catalog(agent: str) -> dict[str, str]:
    """{skill name: when to use it} for one agent."""
    out: dict[str, str] = {}
    for path in sorted((SKILLS / agent).glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        desc = next((ln[1:].strip() for ln in lines[1:3] if ln.startswith(">")), "")
        out[path.stem] = desc
    return out


@lru_cache(maxsize=None)
def text(agent: str, name: str) -> str:
    if name not in catalog(agent):
        raise KeyError(name)
    return (SKILLS / agent / f"{name}.md").read_text(encoding="utf-8").strip()


def catalog_block(agent: str) -> str:
    items = "\n".join(f"- {name}: {desc}" for name, desc in catalog(agent).items())
    return (f"## Skills\nOpen one with load_skill(name) when the request needs it (at most {config.MAX_SKILL_LOADS_PER_RUN} "
            f"per request). Follow it.\n{items}") if items else ""


def inject(agent: str, names: list[str] | None = None) -> str:
    """The full text of an agent's skills (all of them by default), for its instructions."""
    names = names if names is not None else list(catalog(agent))
    return "\n\n".join(f"## Skill: {n}\n{text(agent, n)}" for n in names if n in catalog(agent))


def load_skill_tool(agent: str, actor: str | None = None):
    """A load_skill tool bound to one agent's skills folder. ctx.deps must have .run (a CoachRun). actor: the agent
    name shown in the trace, when it differs from the folder (the Career coach runs as "strategist")."""
    actor = actor or agent

    async def load_skill(ctx: RunContext[Any], name: str) -> str:
        """Open one of your skills by name (see the Skills list in your instructions) and follow it."""
        run = ctx.deps.run
        if run.skill_loads >= config.MAX_SKILL_LOADS_PER_RUN:
            run.step(actor, "skill_refused", f"Cap of {config.MAX_SKILL_LOADS_PER_RUN} skills per request reached")
            return f"Skill limit reached ({config.MAX_SKILL_LOADS_PER_RUN} per request). Answer with what you have."
        name = (name or "").strip().removesuffix(".md")
        if name not in catalog(agent):
            return f"No skill called {name!r}. Available: {', '.join(catalog(agent))}."
        run.skill_loads += 1
        run.step(actor, "opened_skill", name)
        return text(agent, name)

    return load_skill
