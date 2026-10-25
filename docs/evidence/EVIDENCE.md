# Evidence ledger

Every claim in `report.html` and `slides.html` must point to a row here. Rubric rule: a section without real evidence
gets at most half credit. Never fabricate; failed or imperfect runs are evidence too. Screenshots use demo data only.

| Date | Rubric section | What it shows | File |
|---|---|---|---|
| 2026-10-25 01:06 | Tokenomics (setup) | Setup check: one gpt-6-luna call through Portkey; the model answered as `gpt-6-luna-global`, 13 input / 0 cached input / 15 output tokens, 0.98 s | `docs/evidence/runs/2026-10-25_setup_check.json` |
| 2026-10-25 01:22 | Tokenomics (setup) | Same check with Portkey's response cache bypassed (`x-portkey-cache-force-refresh`) and reasoning effort low: `gpt-6-luna-global`, 13 input / 0 cached input / 5 output tokens (0 reasoning), 2.17 s. The earlier 0.98 s call was probably a cache replay | `docs/evidence/runs/2026-10-25_setup_check_fresh.json` |

## Still to collect

- [ ] Baseline (before): how a real user tracks the search and preps a call today — minutes, steps, misses
- [ ] One real end-to-end run with the agent trace (delegation) — screenshots
- [ ] Token usage per run (input / cached input / output) from the app's own log
- [ ] Prompt-injection attack stopped by a defense — test output + screenshot
- [ ] Real user test: task, time, outcome, quote (after)
- [ ] Key UI states for look + feel
