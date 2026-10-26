"""Impact ESTIMATE: the manual recruiting chores the app replaces, chore by chore, and what it makes possible.

This is a labelled, reproducible ESTIMATE, not a user test (no before/after test with a real student has been run).
Every input below is a named constant with a LOW and a HIGH value and its source:
  - "measured": a logged run of the app (run id + file), read from the evidence files at run time;
  - "public":   a public source listed in docs/research/impact_sources.json (S1..S14), read on 2026-10-26;
  - "code":     a limit or schedule set in the app's own code;
  - "author":   an author assumption, with a one-line reason. No public source gives minutes per recruiting task.
Nothing was tuned to reach a target: the 40-hour comparison is printed as the numbers come out.

Run from the repo root (stdlib only):
  backend/.venv/bin/python scripts/impact_estimate.py
Writes docs/evidence/runs/2026-10-26_impact_estimate.json and prints a short table.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_LIVE = ROOT / "docs/evidence/screenshots/2026-10-26_live/runs.json"
RUNS_WEB = ROOT / "docs/evidence/screenshots/2026-10-26_live_web/runs.json"
COST_MODEL = ROOT / "docs/evidence/runs/2026-10-26_cost_model.json"
SOURCES = ROOT / "docs/research/impact_sources.json"
OUT = ROOT / "docs/evidence/runs/2026-10-26_impact_estimate.json"

WORK_WEEK_HOURS = 40  # the comparison the brief asks for; a convention, not a source


@dataclass(frozen=True)
class Input:
    low: float
    high: float
    unit: str
    kind: str  # measured | public | code | author | calculation
    source: str  # run id + file, S-id + URL, code location, or the reason for an author assumption


def _runs() -> dict:
    """Measured runs by id, from the two live screenshot sessions (the same files as the report's Table 2)."""
    out = {}
    for f in (RUNS_LIVE, RUNS_WEB):
        for r in json.loads(f.read_text())["runs"]:
            out[r["run_id"]] = {"seconds": r["seconds"], "kind": r["kind"], "file": str(f.relative_to(ROOT))}
    return out


RUNS = _runs()
_URL = {s["id"]: s["url"] for s in json.loads(SOURCES.read_text())["sources"]}


def run_secs(run_id: str) -> float:
    return RUNS[run_id]["seconds"]


def measured(*run_ids: str, unit: str = "seconds") -> Input:
    secs = [run_secs(r) for r in run_ids]
    files = sorted({RUNS[r]["file"] for r in run_ids})
    return Input(min(secs), max(secs), unit, "measured", f"run(s) {', '.join(run_ids)} in {', '.join(files)}")


def public(sid: str, note: str) -> str:
    return f"{sid} {_URL[sid]} ({note})"


# ------------------------------------------------------------------ measured app response times (live site, demo data)
APP_DISCOVER_SECS = measured("924006932786")  # job boards of 8 tracked organisations + 2 careers pages, one run
APP_WEB_SHORTLIST_SECS = measured("d1161ab12736")  # whole-web search: 4 candidates, 2 confirmed on their own page
APP_PEOPLE_SECS = measured("be2afd11acd4")  # key people + alumni at one organisation: 8 web searches, 1 confirmed
APP_DOORS_SECS = measured("affe3255c214")  # warm paths: 2 from 10 people
APP_INTAKE_SECS = measured("16bac70cde0d", "fa319fb53b37", "2bbe610b4159", "c9fea27d4495")  # one text, one call each
APP_PLAN_SECS = measured("c469f1ee77fc")  # Plan my week: 23 open actions -> 5 ranked moves
APP_CALL_BRIEF_SECS = measured("2780889ce0f4")  # call brief before a coffee chat
APP_WEB_ANSWER_SECS = measured("692b493b6c59")  # coach answer with web sources
APP_DRAFT_SECS = measured("6939e33cfb41")  # thank-you draft saved to the Outbox (not sent)

# ------------------------------------------------------------------ app limits and schedules, from the code
ORGS_PER_DISCOVER_RUN = Input(8, 8, "organisations/run", "code", "backend/config.py MAX_DISCOVER_COMPANIES = 8")
CAREERS_PAGES_PER_RUN = Input(3, 3, "pages/run", "code", "backend/config.py MAX_PAGES_PER_RUN = 3")
WEB_RUNS_PER_DAY_CAP = Input(20, 20, "web runs/student/day", "code", "backend/config.py MAX_WEB_RUNS_PER_DAY = 20")
PEOPLE_PER_ORG_CAP = Input(5, 5, "people/organisation", "code", "backend/config.py MAX_STAKEHOLDERS = 5")
VERIFY_PAGES_PER_RUN = Input(8, 8, "pages/run", "code", "backend/config.py MAX_VERIFY_PAGES = 8; backend/keeper.py verify_web")
SYNC_EVERY_MIN = Input(30, 30, "minutes", "code", "connector/coach_connector.py schedule --every default 30")
SYNC_CHANNELS = Input(3, 3, "channels", "code", "connector/coach_connector.py COMMAND_CHANNELS['run'] = gmail, imessage, whatsapp")
RETRIEVAL_TOP_K = Input(10, 10, "records/specialist", "code", "backend/config.py RETRIEVAL_TOP_K = 10")
DAILY_TOKEN_BUDGET = Input(300_000, 300_000, "tokens/student/day", "code", "backend/config.py DAILY_TOKEN_BUDGET")
DISCOVER_RUN_TOKENS = Input(12_900, 12_900, "tokens/run (input + output)", "measured", "run 924006932786 usage 12,071 in + 829 out, 2026-10-26_live/runs.json; the budget counts both (backend/db.py tokens_today)")
PEOPLE_RUN_TOKENS = Input(21_039, 21_039, "tokens/run (input + output)", "measured", "run be2afd11acd4 usage 20,634 in + 405 out, 2026-10-26_live_web/runs.json")
PEOPLE_RUN_COST = Input(0.0818, 0.0818, "USD/run", "measured", "run be2afd11acd4 cost_usd, 2026-10-26_live_web/runs.json")
OPEN_ACTIONS_DEMO = Input(23, 23, "open actions", "measured", "run c469f1ee77fc trace (report Section 4), demo account")

# ------------------------------------------------------------------ public inputs (docs/research/impact_sources.json)
TARGET_ORGS = Input(40, 40, "organisations", "public", public("S6", "Dalton's 2-Hour Job Search list of 40 target employers; a method, not a measured average"))
WIDE_ORGS = Input(272, 272, "organisations", "public", public("S7", "every employer of a Yale SOM Class of 2025 full-time hire or Class of 2026 intern, counted from the page"))
CHATS_PER_WEEK = Input(2, 3, "coffee chats/week", "public", public("S3", "Carlson road map: two, then two to three a week; advice, not observed"))
OUTREACH_EMAILS_PER_CHAT = Input(2.5, 2.5, "emails/chat", "public", public("S6", "about 2 replies per 5 emails, so 2.5 emails per conversation; rule of thumb"))
CHAT_LENGTH_MIN = Input(15, 30, "minutes/chat", "public", public("S13", "15-20 min") + "; " + public("S4", "up to 20-30 min"))
SEASON_WEEKS = Input(19.6, 19.6, "weeks", "calculation", public("S11", "mid-September start") + " to " + public("S12", "January 30 offer deadline") + ": 137 days")

# ------------------------------------------------------------------ author assumptions (no public source gives these)
CAREERS_PAGE_CHECK_MIN = Input(2, 5, "minutes/page", "author", "open a careers page, filter for intern/MBA, scan for new postings; no published timing")
CAREERS_CHECKS_PER_WEEK = Input(1, 1, "checks/page/week", "author", "one weekly sweep; postings roll in from late fall (S11); closing speed unknown")
BOARDS_USED = Input(3, 8, "job boards", "author", "a few of the 27+ boards the Yale CDO lists (S8), plus the school system and LinkedIn")
BOARD_SEARCH_MIN = Input(10, 20, "minutes/board/week", "author", "run saved searches, open and skim the new results")
UNREAD_BOARDS = Input(2, 2, "job boards", "author", "LinkedIn and the school system: the app never reads them (report Section 8), so the student still checks them")
CANDIDATES_PER_40_ORGS = Input(5, 10, "candidate postings/week", "author", "new postings worth a closer look in a 40-organisation sweep")
CONFIRM_MIN = Input(3, 5, "minutes/candidate", "author", "open the posting, check it is real, open, MBA-eligible, then save the link")
NEW_TARGETS_PER_WEEK = Input(3, 5, "organisations/week", "author", "the shortlist grows a few at a time; Dalton (S6) works on 5 companies at a time")
PEOPLE_SEARCH_MIN = Input(30, 60, "minutes/organisation", "author", "team pages, LinkedIn, the alumni directory (13,000+ SOM alumni, S9) for 2-5 names + a contact-map row (S5)")
MESSAGES_PER_CHAT = Input(5, 8, "messages to log/chat", "author", "outreach emails (2.5, S6), the reply, scheduling, the thank-you (S4) and a follow-up")
OTHER_ITEMS_PER_WEEK = Input(2, 5, "items/week", "author", "postings, application confirmations and recruiter emails outside the chats")
LOG_MIN_PER_ITEM = Input(2, 4, "minutes/item", "author", "copy 8 fields into the tracker (docs/impact/manual_capture_template.csv has 8 fields)")
PLAN_MIN_PER_ACTION = Input(1, 2, "minutes/open action", "author", "look up each open item across email, chats and the sheet, then rank")
OPEN_ACTIONS_PER_WEEK = Input(15, 30, "open actions", "author", "around the 23 the demo account held (OPEN_ACTIONS_DEMO)")
FOLLOWUP_CHECK_MIN_PER_DAY = Input(5, 10, "minutes/day", "author", "check who is owed a thank-you (24 h, S4) or a follow-up (7 business days, S5)")
FOLLOWUP_CHECK_DAYS = Input(5, 5, "days/week", "author", "weekdays")
OUTREACH_EMAIL_MIN = Input(5, 10, "minutes/email", "author", "a personalised first email to a stranger")
SCHEDULING_MIN = Input(5, 10, "minutes/chat", "author", "agree a time and send an invite; the app does not schedule")
PREP_MIN = Input(30, 60, "minutes/chat", "author", "the 4 prep steps the Yale CDO lists (S4) give no minutes")
THANK_YOU_MIN = Input(10, 15, "minutes/chat", "author", "a personalised note within 24 h (S4)")
FOLLOW_UP_EMAIL_MIN = Input(5, 10, "minutes/chat", "author", "a short follow-up a week later (S4, S5)")
FOLLOW_UPS_PER_CHAT = Input(0, 1, "drafts/chat", "author", "only when a reply or a next step is owed")
# reading and checking what the app produced: the student's own time in the app
APP_REVIEW_CARD_MIN = Input(1, 2, "minutes/saved posting", "author", "read the quote and open the link the app saved")
APP_REVIEW_TARGET_MIN = Input(3, 5, "minutes/organisation", "author", "read the people cards and their public pages")
APP_ALUMNI_DIRECTORY_MIN = Input(5, 10, "minutes/organisation", "author", "the app does not read the alumni directory or LinkedIn, so the student still looks there")
APP_REVIEW_ITEM_MIN = Input(0.5, 1, "minutes/item", "author", "glance at the updated card; paste the items from channels the connector does not read")
APP_PLAN_REVIEW_MIN = Input(5, 10, "minutes/week", "author", "read the 5 ranked moves and their evidence")
APP_PREP_REVIEW_MIN = Input(10, 20, "minutes/chat", "author", "read the brief and practise the story; the app cannot practise for the student")
APP_DRAFT_EDIT_MIN = Input(2, 4, "minutes/draft", "author", "edit and send it yourself from the Outbox (the app never sends)")
APP_DRAFT_SECS_SAME_AS_THANK_YOU = Input(1, 1, "x thank-you draft time", "author", "outreach and follow-up drafts use the same Outbox tool; only the thank-you was timed")
WEB_SHORTLISTS_PER_WEEK = Input(1, 3, "runs/week", "author", "4 a month (typical) to 12 (heavy) in runs/2026-10-26_cost_model.json, itself an estimate")

INPUTS = {k: v for k, v in dict(globals()).items() if isinstance(v, Input)}


# ------------------------------------------------------------------ model
def lo(x: Input) -> float:
    return x.low


def hi(x: Input) -> float:
    return x.high


def manual_minutes(end, orgs: Input) -> dict:
    """Manual minutes per week per chore at one end (lo or hi) of every input."""
    scale = end(orgs) / TARGET_ORGS.low  # candidates grow with the organisations swept
    chats = end(CHATS_PER_WEEK)
    return {
        "a_find_openings": end(orgs) * end(CAREERS_CHECKS_PER_WEEK) * end(CAREERS_PAGE_CHECK_MIN)
        + end(BOARDS_USED) * end(BOARD_SEARCH_MIN)
        + end(CANDIDATES_PER_40_ORGS) * scale * end(CONFIRM_MIN),
        "b_people_and_alumni": end(NEW_TARGETS_PER_WEEK) * end(PEOPLE_SEARCH_MIN),
        "c_keep_tracker_current": (end(MESSAGES_PER_CHAT) * chats + end(OTHER_ITEMS_PER_WEEK)) * end(LOG_MIN_PER_ITEM),
        "d_plan_the_week": end(OPEN_ACTIONS_PER_WEEK) * end(PLAN_MIN_PER_ACTION)
        + end(FOLLOWUP_CHECK_MIN_PER_DAY) * end(FOLLOWUP_CHECK_DAYS),
        "e_coffee_chats": chats * (end(OUTREACH_EMAILS_PER_CHAT) * end(OUTREACH_EMAIL_MIN) + end(SCHEDULING_MIN)
                                   + end(PREP_MIN) + end(THANK_YOU_MIN) + end(FOLLOW_UPS_PER_CHAT) * end(FOLLOW_UP_EMAIL_MIN)),
    }


def app_minutes(end, orgs: Input) -> dict:
    """Student minutes per week in the app: measured response time (waiting) + labelled reading and editing time."""
    scale = end(orgs) / TARGET_ORGS.low
    chats = end(CHATS_PER_WEEK)
    candidates = end(CANDIDATES_PER_40_ORGS) * scale
    discover_runs = math.ceil(end(orgs) / ORGS_PER_DISCOVER_RUN.low)
    items = end(MESSAGES_PER_CHAT) * chats + end(OTHER_ITEMS_PER_WEEK)
    drafts = end(OUTREACH_EMAILS_PER_CHAT) + 1 + end(FOLLOW_UPS_PER_CHAT)  # outreach + thank-you + follow-up
    return {
        "a_find_openings": (discover_runs * end(APP_DISCOVER_SECS) + end(WEB_SHORTLISTS_PER_WEEK) * end(APP_WEB_SHORTLIST_SECS)) / 60
        + candidates * end(APP_REVIEW_CARD_MIN)
        + end(UNREAD_BOARDS) * end(BOARD_SEARCH_MIN),  # boards the app cannot read stay manual
        "b_people_and_alumni": end(NEW_TARGETS_PER_WEEK) * ((end(APP_PEOPLE_SECS) + end(APP_DOORS_SECS)) / 60
                                                            + end(APP_REVIEW_TARGET_MIN) + end(APP_ALUMNI_DIRECTORY_MIN)),
        "c_keep_tracker_current": items * (end(APP_INTAKE_SECS) / 60 + end(APP_REVIEW_ITEM_MIN)),
        "d_plan_the_week": end(APP_PLAN_SECS) / 60 + end(APP_PLAN_REVIEW_MIN),
        "e_coffee_chats": chats * ((end(APP_CALL_BRIEF_SECS) + end(APP_WEB_ANSWER_SECS)
                                    + drafts * end(APP_DRAFT_SECS) * end(APP_DRAFT_SECS_SAME_AS_THANK_YOU)) / 60
                                   + end(APP_PREP_REVIEW_MIN) + drafts * end(APP_DRAFT_EDIT_MIN) + end(SCHEDULING_MIN)),
    }


def hours(d: dict) -> dict:
    return {k: round(v / 60, 2) for k, v in d.items()}


def scenario(orgs: Input) -> dict:
    m_lo, m_hi = hours(manual_minutes(lo, orgs)), hours(manual_minutes(hi, orgs))
    a_lo, a_hi = hours(app_minutes(lo, orgs)), hours(app_minutes(hi, orgs))
    chores = {k: {"manual_h_week": [m_lo[k], m_hi[k]], "app_h_week": [a_lo[k], a_hi[k]]} for k in m_lo}
    tm = [round(sum(m_lo.values()), 1), round(sum(m_hi.values()), 1)]
    ta = [round(sum(a_lo.values()), 1), round(sum(a_hi.values()), 1)]
    return {
        "organisations_swept_weekly": orgs.low,
        "chores": chores,
        "manual_total_h_week": tm,
        "app_total_h_week": ta,
        "by_hand_work_avoided_at_full_coverage_h_week": [round(tm[0] - ta[0], 1), round(tm[1] - ta[1], 1)],
        "share_of_40h_week_manual": [round(tm[0] / WORK_WEEK_HOURS, 2), round(tm[1] / WORK_WEEK_HOURS, 2)],
        "season_note": "only if every week of the season looked like this one (a constant week, winter break included)",
        "manual_total_h_season": [round(tm[0] * SEASON_WEEKS.low), round(tm[1] * SEASON_WEEKS.high)],
        "app_total_h_season": [round(ta[0] * SEASON_WEEKS.low), round(ta[1] * SEASON_WEEKS.high)],
        "not_replaced_h_week_chats_themselves": [round(lo(CHATS_PER_WEEK) * lo(CHAT_LENGTH_MIN) / 60, 1),
                                                  round(hi(CHATS_PER_WEEK) * hi(CHAT_LENGTH_MIN) / 60, 1)],
    }


def possibilities() -> list[dict]:
    """What the app does per run or per day, against what is feasible by hand. Each row: a measured number or the code."""
    wide_runs = math.ceil(WIDE_ORGS.low / ORGS_PER_DISCOVER_RUN.low)
    wide_tokens = wide_runs * DISCOVER_RUN_TOKENS.low
    # people searches a day: the 20-search cap or the token budget, whichever binds first (the check runs before each request)
    cap = min(WEB_RUNS_PER_DAY_CAP.low, math.ceil(DAILY_TOKEN_BUDGET.low / PEOPLE_RUN_TOKENS.low))
    syncs = 24 * 60 / SYNC_EVERY_MIN.low
    return [
        {"capability": "Job boards of 8 organisations (plus 2 careers pages) in one run",
         "app": f"{APP_DISCOVER_SECS.low} s (measured)",
         "by_hand": f"{8 * CAREERS_PAGE_CHECK_MIN.low:.0f}-{8 * CAREERS_PAGE_CHECK_MIN.high:.0f} min at 2-5 min a page (author)",
         "source": APP_DISCOVER_SECS.source},
        {"capability": f"A weekly sweep of all {WIDE_ORGS.low:.0f} organisations that hired Yale SOM MBAs (S7)",
         "app": f"ESTIMATE {wide_runs} runs x {APP_DISCOVER_SECS.low} s = {wide_runs * APP_DISCOVER_SECS.low / 60:.1f} min of run time; about {wide_tokens:,.0f} tokens (input + output), "
                f"above one day's {DAILY_TOKEN_BUDGET.low:,.0f}-token budget, so at least 2 days. NOT BUILT: the interface's button always searches the 8 most "
                f"recently added open targets (frontend DiscoverPanel.tsx runDiscover(); backend/main.py discover_route), so this needs a rotating list. Coverage is limited to boards on the 4 public APIs (Greenhouse, Lever, Ashby, "
                f"SmartRecruiters) and up to {CAREERS_PAGES_PER_RUN.low:.0f} careers pages per run that allow reading: the share of the {WIDE_ORGS.low:.0f} it reaches is NOT measured",
         "by_hand": f"{WIDE_ORGS.low * CAREERS_PAGE_CHECK_MIN.low / 60:.1f}-{WIDE_ORGS.low * CAREERS_PAGE_CHECK_MIN.high / 60:.1f} h a week for the careers pages alone (author minutes; with boards and checks see wide_272 a_find_openings)",
         "source": f"{APP_DISCOVER_SECS.source}; {ORGS_PER_DISCOVER_RUN.source}; {DAILY_TOKEN_BUDGET.source}; backend/jobboards.py"},
        {"capability": "Every web result confirmed on its own page before it is saved",
         "app": f"code reads up to {VERIFY_PAGES_PER_RUN.low:.0f} source pages per run and keeps only results the page confirms; measured: 4 candidates, 2 confirmed, 2 set aside, {APP_WEB_SHORTLIST_SECS.low} s",
         "by_hand": f"{CONFIRM_MIN.low:.0f}-{CONFIRM_MIN.high:.0f} min per candidate (author), usually skipped under time pressure (not measured)",
         "source": f"{APP_WEB_SHORTLIST_SECS.source}; {VERIFY_PAGES_PER_RUN.source}"},
        {"capability": "Key people and alumni at one organisation",
         "app": f"{APP_PEOPLE_SECS.low} s, 8 web searches, 1 person confirmed on a public page (up to {PEOPLE_PER_ORG_CAP.low:.0f} per organisation in code); "
                f"alumni only from public pages, the alumni directory is not read",
         "by_hand": f"{PEOPLE_SEARCH_MIN.low:.0f}-{PEOPLE_SEARCH_MIN.high:.0f} min (author) across team pages, LinkedIn and 13,000+ SOM / 190,000+ Yale alumni (S9, S10)",
         "source": f"{APP_PEOPLE_SECS.source}; {PEOPLE_PER_ORG_CAP.source}"},
        {"capability": f"People at about {cap:.0f} organisations in one day (the {DAILY_TOKEN_BUDGET.low:,.0f}-token daily budget binds before the {WEB_RUNS_PER_DAY_CAP.low:.0f}-search cap)",
         "app": f"ESTIMATE {cap:.0f} x the measured {APP_PEOPLE_SECS.low} s = {cap * APP_PEOPLE_SECS.low / 60:.1f} min of run time, about ${cap * PEOPLE_RUN_COST.low:.2f} at the measured cost per run, "
                f"if nothing else used the day's budget; plus {APP_REVIEW_TARGET_MIN.low + APP_ALUMNI_DIRECTORY_MIN.low:.0f}-{APP_REVIEW_TARGET_MIN.high + APP_ALUMNI_DIRECTORY_MIN.high:.0f} "
                f"min of the student's reading and alumni-directory time per organisation (author)",
         "by_hand": f"{cap * PEOPLE_SEARCH_MIN.low / 60:.1f}-{cap * PEOPLE_SEARCH_MIN.high / 60:.0f} h (author minutes)",
         "source": f"{WEB_RUNS_PER_DAY_CAP.source}; {DAILY_TOKEN_BUDGET.source}; {PEOPLE_RUN_TOKENS.source}; {PEOPLE_RUN_COST.source}; backend/main.py require_web_budget"},
        {"capability": "Warm paths into an organisation from the student's own people",
         "app": f"{APP_DOORS_SECS.low} s: 2 paths from 10 people",
         "by_hand": "not timed; the student must remember who knows whom",
         "source": APP_DOORS_SECS.source},
        {"capability": "A tracker that stays current on its own",
         "app": f"auto-sync every {SYNC_EVERY_MIN.low:.0f} min = up to {syncs:.0f} runs a day, each checking up to {SYNC_CHANNELS.low:.0f} channels "
                f"({syncs * SYNC_CHANNELS.low:.0f} channel checks) while the Mac is awake; seen mail is never re-read and only new messages that matter are sent. "
                f"Gmail verified under the scheduler; Messages and WhatsApp need Full Disk Access (a real grant not yet verified)",
         "by_hand": "a person checks a few times a day and retypes what matters (not measured)",
         "source": f"{SYNC_EVERY_MIN.source}; {SYNC_CHANNELS.source}; EVIDENCE.md rows of 2026-10-25 21:14 and 21:39"},
        {"capability": "Read everything, keep only what matters",
         "app": "the filter passed 29 of 150 Gmail emails (19%), 23 of 125 WhatsApp (18%) and 3 of 36 iMessage (8%) conversations on the author's accounts (counts only); its misses are not measured",
         "by_hand": "every message read to find them",
         "source": "EVIDENCE.md rows of 2026-10-25 20:43 and 21:38"},
        {"capability": "Decide the week from every open action",
         "app": f"{APP_PLAN_SECS.low} s from {OPEN_ACTIONS_DEMO.low:.0f} open actions to 5 ranked moves with evidence; each specialist reads the {RETRIEVAL_TOP_K.low:.0f} most relevant records",
         "by_hand": f"{OPEN_ACTIONS_DEMO.low * PLAN_MIN_PER_ACTION.low:.0f}-{OPEN_ACTIONS_DEMO.low * PLAN_MIN_PER_ACTION.high:.0f} min for the same {OPEN_ACTIONS_DEMO.low:.0f} actions (author minutes)",
         "source": f"{APP_PLAN_SECS.source}; {RETRIEVAL_TOP_K.source}"},
        {"capability": "Prepare and follow up one coffee chat",
         "app": f"call brief {APP_CALL_BRIEF_SECS.low} s, cited web answer {APP_WEB_ANSWER_SECS.low} s, thank-you draft {APP_DRAFT_SECS.low} s (in the Outbox, never sent)",
         "by_hand": f"{PREP_MIN.low + THANK_YOU_MIN.low:.0f}-{PREP_MIN.high + THANK_YOU_MIN.high:.0f} min of prep and thank-you (author)",
         "source": f"{APP_CALL_BRIEF_SECS.source}; {APP_WEB_ANSWER_SECS.source}; {APP_DRAFT_SECS.source}"},
    ]


WEEKS_PER_MONTH = 52 / 12


def usage_cost_month(end) -> float:
    """USD a month for the use Table 5 assumes, at the measured cost per request (cost_model.json cost_per_request_usd)."""
    c = json.loads(COST_MODEL.read_text())["cost_per_request_usd"]
    chats = end(CHATS_PER_WEEK)
    items = end(MESSAGES_PER_CHAT) * chats + end(OTHER_ITEMS_PER_WEEK)
    drafts = end(OUTREACH_EMAILS_PER_CHAT) + 1 + end(FOLLOW_UPS_PER_CHAT)
    week = (end(NEW_TARGETS_PER_WEEK) * (c["key_people"] + c["doors"]) + end(WEB_SHORTLISTS_PER_WEEK) * c["web_shortlist"]
            + chats * c["chat_with_web"] + math.ceil(TARGET_ORGS.low / ORGS_PER_DISCOVER_RUN.low) * c["discover"]
            + items * c["intake"] + c["plan"] + chats * (1 + drafts) * c["chat"])
    return round(week * WEEKS_PER_MONTH, 2)


def main() -> None:
    cost = json.loads(COST_MODEL.read_text())["scenarios"]["typical"]["per_user_month_usd"]
    focused, wide = scenario(TARGET_ORGS), scenario(WIDE_ORGS)
    result = {
        "label": "ESTIMATE, not a user test",
        "date": "2026-10-26",
        "what": "Manual minutes per unit x units per week, chore by chore along the app's five steps, against the app's measured "
                "response times plus a labelled reading and editing time. Two scenarios: a focused list of 40 organisations (S6) and "
                "a wide sweep of the 272 organisations that hired Yale SOM MBAs in 2025-26 (S7). Low = every input at its low value; high = every input at its high value.",
        "not_modelled": "applications and cover letters, interview and case preparation, info sessions and school events, the coffee chats themselves "
                        "(reported separately). These are inside the 15-25 h/week a career office advises (S1).",
        "sanity_checks": {
            "career_office_advice_h_week": [15, 25], "advice_source": f"S1 {_URL['S1']} (advice, 2022)",
            "students_self_report_h_week": [4, 9], "self_report_source": f"S2 {_URL['S2']} (66% of respondents, 2017, secondary)",
        },
        "cost_per_student_month_usd_typical_month": cost,
        "cost_source": "docs/evidence/runs/2026-10-26_cost_model.json (typical month of report Section 5, itself an estimate; NOT this scenario's use)",
        "cost_per_student_month_usd_this_usage_focused_40": [usage_cost_month(lo), usage_cost_month(hi)],
        "cost_this_usage_note": "the use assumed in the focused scenario (3-5 people searches, 1-3 web shortlists, one web answer per chat a week) "
                                "at the measured cost per request, 52/12 weeks a month; mostly people searches",
        "inputs": {k: asdict(v) for k, v in INPUTS.items()},
        "author_assumptions": [k for k, v in INPUTS.items() if v.kind == "author"],
        "author_assumptions_minutes": [k for k, v in INPUTS.items() if v.kind == "author" and "minutes" in v.unit],
        "author_assumptions_volumes": [k for k, v in INPUTS.items() if v.kind == "author" and "minutes" not in v.unit],
        "public_inputs": [k for k, v in INPUTS.items() if v.kind == "public"],
        "scenarios": {"focused_40": focused, "wide_272": wide},
        "app_coverage_caveat": "In the wide scenario the app's time covers only what it can reach: boards on 4 public APIs, up to 3 careers pages per run "
                               "that allow reading, and OpenAI web search. The share of the 272 organisations reached is NOT measured, so the two columns are not equal coverage.",
        "new_possibilities": possibilities(),
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

    names = {"a_find_openings": "a. Find openings", "b_people_and_alumni": "b. People + alumni",
             "c_keep_tracker_current": "c. Keep tracker current", "d_plan_the_week": "d. Plan the week",
             "e_coffee_chats": "e. Coffee chats (prep, emails)"}
    print("IMPACT ESTIMATE (not a user test): student hours per week, low-high\n")
    for title, s in (("Focused list, 40 organisations (S6)", focused), ("Wide sweep, 272 organisations (S7)", wide)):
        print(title)
        print(f"  {'chore':32} {'by hand':>13} {'in the app':>13}")
        for k, c in s["chores"].items():
            m, a = c["manual_h_week"], c["app_h_week"]
            print(f"  {names[k]:32} {m[0]:>5.1f} - {m[1]:<5.1f} {a[0]:>5.1f} - {a[1]:<5.1f}")
        tm, ta, sh = s["manual_total_h_week"], s["app_total_h_week"], s["share_of_40h_week_manual"]
        print(f"  {'TOTAL h/week':32} {tm[0]:>5.1f} - {tm[1]:<5.1f} {ta[0]:>5.1f} - {ta[1]:<5.1f}")
        av = s["by_hand_work_avoided_at_full_coverage_h_week"]
        print(f"  by-hand work avoided at full coverage, per week: {av[0]}-{av[1]}")
        print(f"  by hand = {sh[0]:.0%}-{sh[1]:.0%} of a 40-hour week; season (~{SEASON_WEEKS.low} weeks): "
              f"{s['manual_total_h_season'][0]}-{s['manual_total_h_season'][1]} h by hand vs "
              f"{s['app_total_h_season'][0]}-{s['app_total_h_season'][1]} h in the app")
        nr = s["not_replaced_h_week_chats_themselves"]
        print(f"  not replaced: the chats themselves, {nr[0]}-{nr[1]} h/week\n")
    print("Sanity checks: career-office advice 15-25 h/week (S1); students' self-report 4-9 h/week (S2).")
    print(f"Author assumptions: {len(result['author_assumptions'])} of {len(INPUTS)} inputs "
          f"({len(result['author_assumptions_minutes'])} minutes, {len(result['author_assumptions_volumes'])} volumes); "
          f"public: {len(result['public_inputs'])}. Wrote {OUT.relative_to(ROOT)}")
    c = result["cost_per_student_month_usd_this_usage_focused_40"]
    print(f"Cost of this use: ${c[0]:.2f}-${c[1]:.2f} a student a month (typical month of Section 5: ${cost:.2f})")
    print("People row:", result["new_possibilities"][4]["capability"], "|", result["new_possibilities"][4]["app"], "|", result["new_possibilities"][4]["by_hand"])


if __name__ == "__main__":
    main()
