"""Data checks: records whose stage no longer matches their own dates or history (zero tokens, plain code).

Copied from the author's tracker and scoped to one student. Every stage that depends on a date must carry it:
  - Call booked -> next_date is the call's date. Once it has passed: did it happen?
  - Reached out -> the date it happened (the 7-day nudge counts from it).
  - last_contact is the date of the latest recorded conversation.
Shown in the Action plan as "Check" items and given to the strategist through get_data_checks().
"""

from __future__ import annotations

import re
from datetime import date, datetime

import db

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
EARLIER_CYCLE = re.compile(r"\blast cycle\b|\bprevious\b|\b20\d\d cycle\b|\blast year\b", re.I)
STAGE_LABEL = {s["key"]: s["label"] for s in db.STAGES}


def to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:16]).date() if "T" in value else date.fromisoformat(value[:10])
    except ValueError:
        return None


def dates_in(text: str | None) -> list[date]:
    """Every date with an explicit year: 2026-11-08, Nov. 8, 2026, 8 November 2026, 02/10/2026."""
    found: list[tuple[int, int, int]] = []
    t = (text or "").lower()
    for y, m, d in re.findall(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t):
        found.append((int(y), int(m), int(d)))
    for mon, d, y in re.findall(rf"\b{_MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", t):
        found.append((int(y), MONTHS[mon[:3]], int(d)))
    for d, mon, y in re.findall(rf"\b(\d{{1,2}})\s+{_MON}\s+(20\d\d)\b", t):
        found.append((int(y), MONTHS[mon[:3]], int(d)))
    out = []
    for y, m, d in found:
        try:
            out.append(date(y, m, d))
        except ValueError:
            pass
    return out


def run(user_id: int, today: date | None = None) -> list[dict]:
    """All problems for one student, most urgent first. Each: rule, area, id, name, problem, fix."""
    today = today or date.today()
    issues: list[dict] = []

    def add(rule: str, area: str, row: dict, problem: str, fix: str) -> None:
        issues.append({"rule": rule, "area": area, "id": row["id"], "name": row.get("name") or row.get("company"),
                       "problem": problem, "fix": fix})

    for c in db.list_contacts(user_id):
        if c.get("not_interested_at"):
            continue
        nd, lc = to_date(c["next_date"]), to_date(c["last_contact"])
        latest = max((d for d in (to_date(e["date"]) for e in c["events"]) if d), default=None)
        if c["status"] == "call_booked":
            if nd is None:
                add("call_no_date", "networking", c, "Call booked, but no date is recorded.", "Record the call's date.")
            elif nd < today:
                add("call_passed", "networking", c, f"The call was booked for {nd:%b %-d} and that date has passed.",
                    "Did it happen? Move them to Follow up, or rebook it.")
        elif c["status"] != "follow_up" and nd and nd < today and c["next_step"]:
            add("step_passed", "networking", c, f"The next step \"{c['next_step']}\" was dated {nd:%b %-d}.",
                "Mark it done or give it a new date.")
        if c["status"] == "reached_out" and lc is None:
            add("reached_out_undated", "networking", c, "Reached out, but the date is not recorded.",
                "Record when you reached out (the nudge counts from it).")
        if latest and lc and latest > lc:
            add("last_contact_behind", "networking", c, f"Latest event is {latest:%b %-d}, but last contact says {lc:%b %-d}.",
                "Set last contact to the latest conversation.")
        if any(to_date(e["date"]) and to_date(e["date"]) > today for e in c["events"]):
            add("future_event", "networking", c, "An event is dated in the future.", "Events record what happened: fix its date.")

    for a in db.list_applications(user_id):
        if a.get("not_interested_at"):
            continue
        if a["status"] not in ("not_started", "wip"):
            if a["status"] in ("applied", "interview", "offer") and not a["last_contact"]:
                add("active_undated", "internships", a, f"{STAGE_LABEL[a['status']]}, but no date is recorded.",
                    "Record the date of the latest step.")
            continue
        found = dates_in(a["deadline"])
        if found and max(found) < today and not EARLIER_CYCLE.search(a["deadline"] or ""):
            add("deadline_passed", "internships", a, f"Deadline \"{a['deadline']}\" has passed.",
                "Check for a new date, or close the row.")

    order = ["call_passed", "step_passed", "deadline_passed", "call_no_date", "last_contact_behind", "future_event",
             "reached_out_undated", "active_undated"]
    return sorted(issues, key=lambda i: (order.index(i["rule"]), i["name"]))
