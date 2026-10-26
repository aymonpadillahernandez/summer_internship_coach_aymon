"""Tokenomics from the app's own log: every model call is a model_runs row (agent, input, cached input, output,
reasoning tokens as the model reported them). Groups calls into requests (agent_runs.kind), and prints the median and
range per kind of request, with cost at the list price in backend/config.py. Read-only.

  backend/.venv/bin/python scripts/token_report.py                    # the local SQLite database
  DATABASE_URL=postgres://… backend/.venv/bin/python scripts/token_report.py --json out.json   # e.g. the live database
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402
from store import connect, is_postgres  # noqa: E402


def cost(i: int, c: int, o: int) -> float:
    return config.cost_usd(i, c, o) or 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="write the summary here")
    args = ap.parse_args()
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT a.run_id, a.kind, a.status AS run_status, a.started_at, m.agent, m.requests, m.input_tokens, m.cached_tokens, "
            "m.output_tokens, m.reasoning_tokens, m.seconds, m.status FROM agent_runs a JOIN model_runs m ON m.run_id = a.run_id")]
    runs: dict[str, dict] = {}
    for r in rows:
        x = runs.setdefault(r["run_id"], {"kind": r["kind"], "ok": r["run_status"] == "ok", "requests": 0, "input": 0, "cached": 0,
                                          "output": 0, "reasoning": 0, "agents": set(), "started": str(r["started_at"])[:16]})
        for k, col in (("requests", "requests"), ("input", "input_tokens"), ("cached", "cached_tokens"), ("output", "output_tokens"),
                       ("reasoning", "reasoning_tokens")):
            x[k] += r[col] or 0
        x["agents"].add(r["agent"])
    ok = [r for r in runs.values() if r["ok"] and r["input"] > 0]
    summary = {"database": "postgres" if is_postgres() else "sqlite", "model": config.MODEL,
               "prices_per_1m": {"input": config.PRICE_INPUT_PER_M, "cached_input": config.PRICE_CACHED_INPUT_PER_M,
                                 "output": config.PRICE_OUTPUT_PER_M, "source": config.PRICE_SOURCE},
               "model_calls": len(rows), "requests_total": len(runs), "requests_ok": len(ok), "by_kind": {}}
    print(f"{summary['database']}: {len(rows)} model calls in {len(runs)} requests ({len(ok)} completed with tokens)\n")
    print(f"{'kind':10} {'n':>4} {'med in':>8} {'med cached':>10} {'med out':>8} {'med reqs':>8} {'med $':>9} {'min $':>9} {'max $':>9}")
    for kind in sorted({r["kind"] for r in ok}):
        xs = [r for r in ok if r["kind"] == kind]
        med = lambda k: statistics.median(r[k] for r in xs)  # noqa: E731
        costs = sorted(cost(r["input"], r["cached"], r["output"]) for r in xs)
        k = {"n": len(xs), "median_input": med("input"), "median_cached": med("cached"), "median_output": med("output"),
             "median_reasoning": med("reasoning"), "median_requests": med("requests"), "median_cost_usd": statistics.median(costs),
             "min_cost_usd": costs[0], "max_cost_usd": costs[-1], "cached_share": round(sum(r["cached"] for r in xs) / max(1, sum(r["input"] for r in xs)), 3),
             "agents": sorted(set().union(*(r["agents"] for r in xs)))}
        summary["by_kind"][kind] = k
        print(f"{kind:10} {k['n']:>4} {k['median_input']:>8.0f} {k['median_cached']:>10.0f} {k['median_output']:>8.0f} "
              f"{k['median_requests']:>8.0f} {k['median_cost_usd']:>9.5f} {k['min_cost_usd']:>9.5f} {k['max_cost_usd']:>9.5f}")
    tot = {k: sum(r[k] for r in ok) for k in ("input", "cached", "output", "reasoning")}
    summary["totals_ok"] = {**tot, "cost_usd": cost(tot["input"], tot["cached"], tot["output"])}
    print(f"\nall completed requests: {tot['input']:,} input ({tot['cached']:,} cached) · {tot['output']:,} output "
          f"({tot['reasoning']:,} reasoning) · ${summary['totals_ok']['cost_usd']:.4f}")
    if args.json:
        Path(args.json).write_text(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
