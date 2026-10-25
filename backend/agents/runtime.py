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
AGENT_TITLES = {"strategist": "Career strategist", "scout": "Opportunity scout", "network": "Network intelligence"}


def prompt(name: str) -> str:
    """A role prompt plus the shared safety block (prompts/_safety.md)."""
    return f"{(PROMPTS / f'{name}.md').read_text(encoding='utf-8').strip()}\n\n{(PROMPTS / '_safety.md').read_text(encoding='utf-8').strip()}"


def limits() -> UsageLimits:
    return UsageLimits(request_limit=config.AGENT_REQUEST_LIMIT, tool_calls_limit=config.AGENT_TOOL_CALLS_LIMIT,
                       total_tokens_limit=config.AGENT_TOTAL_TOKENS_LIMIT)


class ModelSubstituted(RuntimeError):
    pass


@dataclass
class CoachRun:
    user_id: int
    kind: str  # intake | plan | chat
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    trace: list[dict] = field(default_factory=list)
    delegations: int = 0
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
                    message_history: list | None = None) -> Any:
    """Run one agent; returns its output, or None when it failed or hit a limit (recorded in the trace)."""
    start = time.perf_counter()
    status, output, error = "ok", None, ""
    with capture_run_messages() as messages:
        try:
            result = await asyncio.wait_for(
                agent.run(user_prompt, deps=deps, usage_limits=limits(), message_history=message_history),
                timeout=config.AGENT_TIMEOUT_SECONDS)
            output = result.output
        except UsageLimitExceeded as e:
            status, error = "usage_limit", str(e)
        except asyncio.TimeoutError:
            status, error = "timeout", f"no answer within {config.AGENT_TIMEOUT_SECONDS} s"
        except Exception as e:  # noqa: BLE001 - any model/validation failure is recorded, never raised to the user raw
            status, error = "error", f"{type(e).__name__}: {str(e)[:200]}"
    responses = [m for m in messages if isinstance(m, ModelResponse)]
    usage = _usage_of(responses)
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
