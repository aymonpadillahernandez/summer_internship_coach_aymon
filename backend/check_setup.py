"""Setup check: finds the .env, makes one gpt-6-luna call and reports the model and its real token usage.

    .venv/bin/python check_setup.py            # from inside backend/
    .venv/bin/python check_setup.py --out ../output/setup_check.json

Exit code 0 = ready; 1 = something is missing. Never prints the key.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import config

PROMPT = "Reply with exactly one word: ready"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=config.ROOT / "output" / "setup_check.json")
    args = parser.parse_args()

    slots = dict(zip(config.ENV_FILES, ("the repo folder", "one folder above the repo",
                                         "two folders above the repo (course workspace root)")))
    print(f".env used: {slots.get(config.ENV_USED, 'none found')}")
    if not config.key_is_set():
        print("PORTKEY_API_KEY: missing", file=sys.stderr)
        return 1
    print("PORTKEY_API_KEY: set")

    from pydantic_ai import Agent

    agent = Agent(config.build_model(), model_settings=config.MODEL_SETTINGS, defer_model_check=True)
    start = time.perf_counter()
    try:
        result = agent.run_sync(PROMPT)
    except Exception as exc:  # report the cause in one line, never a raw traceback
        print(f"Model call failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    seconds = round(time.perf_counter() - start, 2)
    usage = result.usage  # a property in pydantic-ai 2.x
    answered_by = result.response.model_name or "unknown"
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_requested": config.MODEL,
        "model_answered": answered_by,
        "answer": str(result.output).strip(),
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": usage.cache_read_tokens,
        "output_tokens": usage.output_tokens,
        "reasoning_tokens": usage.details.get("reasoning_tokens", 0),
        "fresh_answer_forced": config.FORCE_FRESH_ANSWERS,
        "reasoning_effort": config.REASONING_EFFORT,
        "requests": usage.requests,
        "seconds": seconds,
    }
    for key, value in report.items():
        print(f"{key}: {value}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not answered_by.startswith(config.MODEL):
        print(f"WARNING: asked for {config.MODEL} but {answered_by} answered", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
