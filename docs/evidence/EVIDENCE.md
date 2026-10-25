# Evidence ledger

Every claim in `report.html` and `slides.html` must point to a row here. Rubric rule: a section without real evidence
gets at most half credit. Never fabricate; failed or imperfect runs are evidence too. Screenshots use demo data only.

| Date | Rubric section | What it shows | File |
|---|---|---|---|
| 2026-10-25 01:06 | Tokenomics (setup) | Setup check: one gpt-6-luna call through Portkey; the model answered as `gpt-6-luna-global`, 13 input / 0 cached input / 15 output tokens, 0.98 s | `docs/evidence/runs/2026-10-25_setup_check.json` |
| 2026-10-25 01:22 | Tokenomics (setup) | Same check with Portkey's response cache bypassed (`x-portkey-cache-force-refresh`) and reasoning effort low: `gpt-6-luna-global`, 13 input / 0 cached input / 5 output tokens (0 reasoning), 2.17 s. The earlier 0.98 s call was probably a cache replay | `docs/evidence/runs/2026-10-25_setup_check_fresh.json` |
| 2026-10-25 01:40 | Agent design · Tokenomics | First real intake runs on the demo (fictional) data: posting → scout added Riverside Arena Group (1,565 in / 0 cached / 380 out, 4.9 s); email → scout + network in parallel added Elena Petrova as *call booked* (3,324 / 0 / 1,210, 5.3 s); WhatsApp export → network (1,770 / **1,029 cached** / 1,134); LinkedIn CSV → network kept 3 of 6 rows (1,776 / **1,029 cached** / 949) | `docs/evidence/runs/2026-10-25_first_backend_runs.json` |
| 2026-10-25 01:40 | Safety (live) | Both attack samples on gpt-6-luna: the injected line was quarantined before the scout ran and Granite Peak was saved as *not started* (no fake recruiter); the hidden white text was removed and Cobalt City FC was saved as *not started*, not as an offer | same file (runs 3–4) |
| 2026-10-25 01:41 | Agent design · Tokenomics | First plan run, strategist delegating to both specialists in parallel: 6 model calls, 14,047 in / 5,870 cached / 4,229 out, **63.4 s**. It said the Meridian interview date was unknown | same file (plan run 1) |
| 2026-10-25 01:45 | Tokenomics (optimization) | Same plan after removing length limits from the output schemas (validation retries were re-running whole answers) and adding people's next dates to opportunity records: 4 model calls, **7,514 in** / 1,605 cached / **2,773 out**, **17.6 s**, and the plan now cites the interview date. Input −47%, output −34%, time −72% | same file (plan run 2) |
| 2026-10-25 01:53 | Safety (test) | 9 pytest safety tests pass with no key: injection quarantined and unable to act, hidden text removed, invented quotes and people rejected, cross-student 404s, delegation cap, invented action refused, model substitution rejected, oversized input 422 with 0 tokens, daily budget 429, tool loop stopped | `docs/evidence/runs/2026-10-25_safety_tests.txt` |
| 2026-10-25 01:58 | Look + feel · Agent design | In the browser: Plan my week answered in 14 s with 5 ranked actions; attack sample blocked with the Shield box; "Prepare my next call" routed to Network intelligence, 11 s, 2,039 tokens | screenshots to capture from the live site |
| 2026-10-25 02:02 | Staff can run it | Fresh clone from GitHub with `.env` one folder above the repo, following the README: health reports "one folder above the repo", demo seeds, site serves, a real intake works; 13 s setup with warm caches | `docs/evidence/runs/2026-10-25_fresh_clone.txt` |

## Still to collect

- [ ] Baseline (before): how a real user tracks the search and preps a call today — minutes, steps, misses
- [ ] Screenshots of a real end-to-end run with the agent trace (delegation), from the live site
- [x] Token usage per run (input / cached input / output) from the app's own log (above; repeat 3× per scenario for the report)
- [x] Prompt-injection attack stopped by a defense: test output (above); screenshot still to capture
- [ ] Real user test: task, time, outcome, quote (after)
- [ ] Key UI states for look + feel
- [ ] gpt-6-luna prices (source + date) to turn token counts into cost
