"""Records keeper (code, not an AI agent: zero tokens, and the same result every time). It is the only part of the
app that writes the cards on the Opportunities, Networking and Action plan boards.

Agents only propose. The Inbox organizer and the Opportunity scout return typed reports; the keeper then
1. checks each item against its source (merge.validate_*): quotes must appear in the text, people's names must be in
   it, links must be in it, record ids must be the student's own. Anything else is rejected with its reason;
2. writes what survived with the merge rules from the author's tracker (merge.apply_*): one card per organisation +
   role and per person, newer evidence decides, older evidence never moves a card back, the student's own moves win,
   a fit is only re-judged by a posting or a page;
3. re-runs the data checks (checks.run) so a stage never disagrees with its own dates, and reports what needs attention.
The Action plan is derived from these records in code (frontend/src/actions.ts), so it always matches them.
"""

from __future__ import annotations

import checks
import merge
from agents.models import NetworkIntake, ScoutIntake
from agents.runtime import CoachRun

NAME = "keeper"


def keep(run: CoachRun, user_id: int, source: str, *, opportunities: ScoutIntake | None = None,
         people: NetworkIntake | None = None, origin_opportunities: str = "posting", origin_people: str = "chat",
         ref: str = "", label: str = "", page_url: str | None = None, refit: bool = False) -> dict:
    saved: dict = {}
    rejected: list[dict] = []
    not_found: list[str] = []
    if opportunities is not None:
        good, bad = merge.validate_scout(opportunities, source, user_id)
        if good.opportunities or good.leads:
            saved.update(merge.apply_scout(user_id, good, origin_opportunities, ref, label, page_url, refit=refit))
        rejected += bad
        not_found += good.fields_not_found
    if people is not None:
        good, bad = merge.validate_network(people, source, user_id)
        if good.contacts:
            saved.update(merge.apply_network(user_id, good, origin_people, ref, label))
        rejected += bad
        not_found += good.fields_not_found
    issues = checks.run(user_id)
    counts = {k: (len(v) if isinstance(v, list) else v) for k, v in saved.items()}
    wrote = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items() if v) or "nothing new"
    run.step(NAME, "kept", f"Checked and saved: {wrote}; {len(rejected)} rejected; {len(issues)} record(s) need attention",
             issues=len(issues))
    return {"saved": saved, "rejected": rejected, "fields_not_found": not_found}
