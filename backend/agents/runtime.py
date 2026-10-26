"""How every agent runs: one wrapper that enforces the limits, checks the model, and records real token usage.

- CoachRun is one student request (an intake, a plan or a chat). It holds the step-by-step trace the app shows
  ("Coach asked Network intelligence: …") and the running token totals.
- run_agent() runs one agent inside UsageLimits and a timeout, then writes one model_runs row with the token counts
  the model reported for every response: input, cached input, output and reasoning. Failed and cut-off runs are
  recorded too, so no spent token goes missing (Lecture 11 dropped a failed specialist's usage).
- Every response's model name is checked: the course key may only use gpt-6-luna, and Portkey can silently
  substitute another model for an unknown name. A substituted answer is rejected.
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse
from pydantic_ai.usage import UsageLimits

import config
import db

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
AGENT_TITLES = {"strategist": "Career coach", "scout": "Opportunity scout", "network": "Network intelligence",
                "inbox": "Inbox organizer", "guide": "Setup guide", "keeper": "Records keeper"}


def prompt(name: str) -> str:
    """A role prompt plus the shared safety block (prompts/_safety.md)."""
    return f"{(PROMPTS / f'{name}.md').read_text(encoding='utf-8').strip()}\n\n{(PROMPTS / '_safety.md').read_text(encoding='utf-8').strip()}"


def limits(requests: int | None = None, tool_calls: int | None = None, total_tokens: int | None = None) -> UsageLimits:
    return UsageLimits(request_limit=requests or config.AGENT_REQUEST_LIMIT,
                       tool_calls_limit=tool_calls or config.AGENT_TOOL_CALLS_LIMIT,
                       total_tokens_limit=total_tokens or config.AGENT_TOTAL_TOKENS_LIMIT)


class ModelSubstituted(RuntimeError):
    pass


@dataclass
class CoachRun:
    user_id: int
    kind: str  # intake | plan | chat
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    trace: list[dict] = field(default_factory=list)
    delegations: int = 0
    skill_loads: int = 0
    drafts: int = 0
    tokens: dict[str, int] = field(default_factory=lambda: {"requests": 0, "input": 0, "cached": 0, "output": 0, "reasoning": 0})
    started: float = field(default_factory=time.perf_counter)

    def __post_init__(self):
        db.start_run(self.run_id, self.user_id, self.kind)

    def step(self, agent: str, event: str, detail: str = "", **extra: Any) -> None:
        self.trace.append({"t": round(time.perf_counter() - self.started, 2), "agent": agent, "event": event,
                           "detail": detail[:400], **extra})

    def finish(self, status: str, summary: str) -> dict:
        seconds = time.perf_counter() - self.started
        db.finish_run(self.run_id, status, seconds, self.trace, summary)
        return {"run_id": self.run_id, "status": status, "seconds": round(seconds, 2), "trace": self.trace,
                "usage": {**self.tokens, "cost_usd": config.cost_usd(self.tokens["input"], self.tokens["cached"], self.tokens["output"])}}


def _usage_of(responses: list[ModelResponse]) -> dict[str, int]:
    out = {"requests": len(responses), "input": 0, "cached": 0, "output": 0, "reasoning": 0}
    for r in responses:
        u = r.usage
        out["input"] += u.input_tokens or 0
        out["cached"] += u.cache_read_tokens or 0
        out["output"] += u.output_tokens or 0
        out["reasoning"] += (u.details or {}).get("reasoning_tokens", 0)
    return out


async def run_agent(run: CoachRun, name: str, agent: Agent, user_prompt: str, deps: Any = None,
                    message_history: list | None = None, timeout: float | None = None,
                    usage_limits: UsageLimits | None = None) -> Any:
    """Run one agent; returns its output, or None when it failed, hit a limit or was paused (recorded in the trace).

    Two stops before any model call (0 tokens): the AI_PAUSED kill switch, and a circuit breaker that pauses an agent
    for a student after FAILURE_PAUSE_AFTER failures in a row (a broken input is not paid for again and again)."""
    if config.AI_PAUSED:
        run.step(name, "paused", "AI is paused on this server (AI_PAUSED)")
        return None
    if db.failure_streak(run.user_id, name, config.FAILURE_PAUSE_MINUTES) >= config.FAILURE_PAUSE_AFTER:
        run.step(name, "paused_after_failures",
                 f"{config.FAILURE_PAUSE_AFTER} failed runs in a row: paused for {config.FAILURE_PAUSE_MINUTES} minutes")
        return None
    timeout = timeout or config.AGENT_TIMEOUT_SECONDS
    start = time.perf_counter()
    status, output, error = "ok", None, ""
    with capture_run_messages() as messages:
        try:
            result = await asyncio.wait_for(
                agent.run(user_prompt, deps=deps, usage_limits=usage_limits or limits(), message_history=message_history),
                timeout=timeout)
            output = result.output
        except UsageLimitExceeded as e:
            status, error = "usage_limit", str(e)
        except asyncio.TimeoutError:
            status, error = "timeout", f"no answer within {timeout:.0f} s"
        except Exception as e:  # noqa: BLE001 - any model/validation failure is recorded, never raised to the user raw
            status, error = "error", f"{type(e).__name__}: {str(e)[:200]}"
    responses = [m for m in messages if isinstance(m, ModelResponse)]
    usage = _usage_of(responses)
    if status == "usage_limit":  # the response that crossed the limit is billed but never captured: count it too
        m = re.search(r"total_tokens=(\d+)", error)
        if m and int(m.group(1)) > usage["input"] + usage["output"]:
            usage["input"] += int(m.group(1)) - usage["input"] - usage["output"]
    models = sorted({r.model_name for r in responses if r.model_name})
    bad = [m for m in models if not m.startswith(config.MODEL)]
    if bad:
        status, error, output = "model_rejected", f"answered by {', '.join(bad)} instead of {config.MODEL}", None
    seconds = round(time.perf_counter() - start, 2)
    db.record_model_run({"run_id": run.run_id, "user_id": run.user_id, "agent": name, "model": ", ".join(models),
                         "requests": usage["requests"], "input_tokens": usage["input"], "cached_tokens": usage["cached"],
                         "output_tokens": usage["output"], "reasoning_tokens": usage["reasoning"],
                         "seconds": seconds, "status": status})
    for k in run.tokens:
        run.tokens[k] += usage[k]
    run.step(name, "finished" if status == "ok" else status, error, seconds=seconds,
             tokens={k: usage[k] for k in ("input", "cached", "output")})
    if bad:
        raise ModelSubstituted(error)
    return output
