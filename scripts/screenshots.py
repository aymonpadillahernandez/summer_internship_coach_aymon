"""Evidence screenshots: drive the real app through one full demo session and save PNGs for the report.

    backend/.venv/bin/python -m pip install playwright      (dev tool, uses the installed Google Chrome)
    backend/.venv/bin/python scripts/screenshots.py --base http://127.0.0.1:8020
    backend/.venv/bin/python scripts/screenshots.py --base https://summer-internship-coach.onrender.com --name 2026-10-26_live

Uses "Try the demo" (a fresh private sandbox with the fictional student's data). Every AI step is a real gpt-6-luna
run: Setup guide, plan, two attacks, a target list, a job-board search, two chats and "Who can open the door".
Files go to docs/evidence/screenshots/<name>/ (default <date>_<base>), numbered in the order a user would see them,
plus runs.json: run id, kind, status, seconds, tokens and agents of every AI run, read from the API itself.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
AI_TIMEOUT = 150_000  # ms: a plan takes ~15-20 s, longer on a cold free-tier server
SEARCH_TIMEOUT = 240_000  # a job-board search may take up to the server's 120 s limit
VIEW = {"width": 1440, "height": 900}
# Screenshot-only layout: let the page grow and unpin the top bar, so a tall panel or board column is captured whole.
# Sheets are see-through with a blur in the app; element screenshots don't render the blur, so make them opaque.
GROW_CSS = ("html,body,#root{height:auto} .app{height:auto;min-height:100vh} .today{overflow:visible} "
            ".topbar{position:static} .board{flex:none} .column-body{overflow:visible} "
            ".sheet{background:var(--surface)!important} .guide-chat,.draft-body{max-height:none;overflow:visible} "
            "*{animation:none!important;transition:none!important}")

TARGET_NAMES = "My target list for next summer: Robinhood, Duolingo"  # names only: no role is stated
# The app's own target-list template (Today → "Use a target-list template"), one line per organisation and role.
TARGETS = ("My target list for next summer (organisation — role — deadline or status — city):\n"
           "1. Robinhood — MBA summer internship\n2. Duolingo — MBA summer internship")
THANK_YOU = "Draft a short thank-you note to Maya Chen for our coffee chat"
CALL_PREP = "Prepare my call with Maya Chen"
GUIDE_Q = "How do I bring in my WhatsApp chats?"
DOOR_CARD = "Northbridge Sports Group"


class Shots:
    def __init__(self, out: Path):
        self.out = out
        self.files: list[str] = []
        self.runs: list[dict[str, Any]] = []

    def save(self, page: Page, name: str, selector: str | None = None, full: bool = False) -> None:
        page.wait_for_timeout(600)  # let rendering settle
        path = self.out / f"{name}.png"
        if selector:
            page.locator(selector).first.screenshot(path=str(path))
        else:
            page.screenshot(path=str(path), full_page=full)
        self.files.append(path.name)
        print(f"  {path.relative_to(ROOT)}", flush=True)

    def save_union(self, page: Page, name: str, selectors: list[str], pad: int = 12, fixed: bool = False) -> None:
        """One crop around several elements (e.g. a trace plus its token line). fixed: they sit in a fixed sheet."""
        page.wait_for_timeout(600)
        boxes = []
        for sel in selectors:
            loc = page.locator(sel).first
            loc.scroll_into_view_if_needed()
            boxes.append(page.evaluate(
                "([el, fixed]) => { const r = el.getBoundingClientRect(); const sx = fixed ? 0 : scrollX, sy = fixed ? 0 : scrollY;"
                " return {x: r.left + sx, y: r.top + sy, w: r.width, h: r.height}; }",
                [loc.element_handle(), fixed]))
        x0 = max(0, min(b["x"] for b in boxes) - pad)
        y0 = max(0, min(b["y"] for b in boxes) - pad)
        x1 = max(b["x"] + b["w"] for b in boxes) + pad
        y1 = max(b["y"] + b["h"] for b in boxes) + pad
        path = self.out / f"{name}.png"
        page.screenshot(path=str(path), full_page=not fixed, clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0})
        self.files.append(path.name)
        print(f"  {path.relative_to(ROOT)}", flush=True)

    def save_tall(self, page: Page, name: str, selector: str) -> None:
        """A fixed side sheet scrolls inside itself: grow the window until nothing inside it scrolls, then capture it."""
        extra = page.evaluate(
            """sel => { const root = document.querySelector(sel); let m = 0;
                 for (const el of [root, ...root.querySelectorAll('*')]) {
                   const o = getComputedStyle(el).overflowY;
                   if ((o === 'auto' || o === 'scroll') && el.scrollHeight > el.clientHeight) m = Math.max(m, el.scrollHeight - el.clientHeight);
                 } return Math.ceil(m); }""", selector)
        size = page.viewport_size or VIEW
        if extra:
            page.set_viewport_size({"width": size["width"], "height": min(size["height"] + extra + 16, 7000)})
        try:
            self.save(page, name, selector)
        finally:
            page.set_viewport_size(size)

    def ai(self, page: Page, match: Callable[[str], bool], action: Callable[[], None], timeout: int = AI_TIMEOUT) -> dict:
        """Run one UI action that starts an AI run; keep the API's own answer (run id, status, tokens, trace)."""
        with page.expect_response(lambda r: r.request.method == "POST" and match(r.url), timeout=timeout) as info:
            action()
        resp = info.value
        data = resp.json() if resp.ok else {"http_status": resp.status, "error": resp.text()[:300]}
        self.runs.append({"endpoint": re.sub(r"^https?://[^/]+", "", resp.url), "response": data})
        if not resp.ok:
            print(f"  ! {resp.url} answered {resp.status}: {data['error']}", flush=True)
        return data


def trace_agents(trace: list[dict]) -> list[str]:
    seen: list[str] = []
    for s in trace:
        for a in (s.get("agent"), s.get("to")):
            if a and a not in seen:
                seen.append(a)
    return seen


def write_runs(page: Page, base: str, shots: Shots) -> None:
    rows = []
    for r in shots.runs:
        d = r["response"]
        rid = d.get("run_id")
        row: dict[str, Any] = {"endpoint": r["endpoint"], "run_id": rid}
        if rid:
            detail = page.request.get(f"{base}/api/runs/{rid}")
            det = detail.json() if detail.ok else {}
            row.update({
                "kind": det.get("kind"),
                "status": d.get("status"),
                "seconds": d.get("seconds"),
                "usage": {k: d.get("usage", {}).get(k) for k in ("input", "cached", "output", "requests", "cost_usd")},
                "agents_in_trace": trace_agents(d.get("trace", [])),
                "trace_events": [f"{s.get('agent')}:{s.get('event')}" + (f"->{s['to']}" if s.get("to") else "") for s in d.get("trace", [])],
                "per_agent": [{k: a.get(k) for k in ("agent", "model", "requests", "input_tokens", "cached_tokens", "output_tokens", "seconds", "status")}
                              for a in det.get("agents", [])],
            })
        else:
            row["error"] = d
        rows.append(row)
    usage = page.request.get(f"{base}/api/usage")
    prices = usage.json().get("prices") if usage.ok else None
    total = {k: sum((x.get("usage") or {}).get(k) or 0 for x in rows) for k in ("input", "cached", "output", "requests")}
    total["cost_usd"] = round(sum((x.get("usage") or {}).get("cost_usd") or 0 for x in rows), 6)
    doc = {"captured_at": datetime.now().astimezone().isoformat(timespec="seconds"), "base": base,
           "account": "Try the demo (fresh private sandbox, fictional student)", "prices": prices,
           "runs": rows, "total": total, "screenshots": shots.files}
    (shots.out / "runs.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"  {(shots.out / 'runs.json').relative_to(ROOT)}  ({len(rows)} runs)", flush=True)


def close_sheet(page: Page) -> None:
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    if page.locator(".scrim").count():  # close the sheet if Escape did not
        page.locator(".scrim").first.click(position={"x": 5, "y": 5})
        page.wait_for_timeout(300)


def tab(page: Page, name: str) -> None:
    page.locator(".view-switch button", has_text=name).click()
    page.wait_for_timeout(400)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8020")
    ap.add_argument("--name", help="folder name under docs/evidence/screenshots (default <date>_<base>)")
    ap.add_argument("--with-signup", action="store_true", help="also create (then delete) a throwaway account for the first-run guide")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    tag = re.sub(r"[^a-z0-9]+", "-", base.split("//")[-1].lower()).strip("-")
    out = ROOT / "docs" / "evidence" / "screenshots" / (args.name or f"{date.today().isoformat()}_{tag}")
    out.mkdir(parents=True, exist_ok=True)
    s = Shots(out)
    is_intake = lambda u: u.endswith("/api/intake")  # noqa: E731

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(base, wait_until="networkidle", timeout=120_000)
        s.save(page, "01_landing")
        page.locator(".demo-button").click()
        page.wait_for_selector(".coach-panel", timeout=60_000)
        page.add_style_tag(content=GROW_CSS)

        # Setup: the Setup guide's checklist and a real answer.
        tab(page, "Setup")
        page.wait_for_selector(".setup-progress", timeout=30_000)
        page.locator(".guide-input textarea").fill(GUIDE_Q)
        s.ai(page, lambda u: u.endswith("/api/guide"), lambda: page.locator(".guide-input .primary-btn").click())
        page.wait_for_selector(".guide-chat .chat-a", timeout=AI_TIMEOUT)
        page.locator(".guide-chat .how-decided summary").first.click()
        s.save(page, "02_setup_guide_whatsapp", ".guide-agent")
        s.save(page, "03_channels_overview", ".connect-head")

        # Today: the team, then the week's plan and how the coach decided.
        tab(page, "Today")
        page.wait_for_selector(".team-strip", timeout=30_000)
        s.save(page, "04_today_team", full=True)
        s.ai(page, lambda u: u.endswith("/api/plan"), lambda: page.locator(".coach-panel .primary-btn").click())
        page.wait_for_selector(".plan-actions", timeout=AI_TIMEOUT)
        page.wait_for_selector(".coach-panel .working", state="detached", timeout=AI_TIMEOUT)
        s.save(page, "05_plan_my_week", ".coach-panel")
        page.locator(".coach-panel .how-decided summary").click()
        s.save_union(page, "06_plan_trace", [".coach-panel .how-decided", ".coach-panel .usage-line"])

        # Two attacks: the shield at work.
        for chip, name in (("instructions in a posting", "07_attack_injected_instructions"),
                           ("hidden text in a web page", "08_attack_hidden_text")):
            page.locator(".sample-chip", has_text=chip).click()
            s.ai(page, is_intake, lambda: page.locator(".intake-panel .primary-btn").click())
            page.wait_for_selector(".intake-panel .intake-result", timeout=AI_TIMEOUT)
            s.save(page, name, ".intake-panel")

        # A target list, then the Opportunity scout searches those organisations' public job boards.
        # Names alone first: the Inbox organizer saves no card without a stated role (it never invents one).
        page.locator(".intake-text").fill(TARGET_NAMES)
        page.locator(".intake-bar .segmented button", has_text="Opportunity").click()
        r = s.ai(page, is_intake, lambda: page.locator(".intake-panel .primary-btn").click())
        page.wait_for_selector(".intake-panel .intake-result", timeout=AI_TIMEOUT)
        s.save(page, "18_target_names_only", ".intake-panel")
        if not (r.get("saved") or {}).get("opportunities_added"):
            page.locator(".intake-text").fill(TARGETS)
            page.locator(".intake-bar .segmented button", has_text="Opportunity").click()
            s.ai(page, is_intake, lambda: page.locator(".intake-panel .primary-btn").click())
            page.wait_for_selector(".intake-panel .intake-result", timeout=AI_TIMEOUT)
            s.save(page, "19_target_list_with_roles", ".intake-panel")
        s.ai(page, lambda u: u.endswith("/api/scout/discover"), lambda: page.locator(".discover .primary-btn").click(), SEARCH_TIMEOUT)
        page.wait_for_selector(".discover .intake-result", timeout=SEARCH_TIMEOUT)
        page.locator(".discover .how-decided summary").click()
        s.save(page, "09_find_openings", ".discover")

        tab(page, "Opportunities")
        page.wait_for_selector(".board .card", timeout=30_000)
        s.save(page, "10_opportunities", full=True)

        # Ask your coach: a draft that lands in the Outbox (never sent), then call prep in a new chat.
        tab(page, "Today")
        page.locator(".stat-ask").click()
        page.wait_for_selector(".chat", timeout=10_000)
        if page.locator(".chat-new").count():
            page.locator(".chat-new").click()
        page.locator(".chat-input textarea").fill(THANK_YOU)
        s.ai(page, lambda u: u.endswith("/api/chat"), lambda: page.locator(".chat-input textarea").press("Enter"))
        page.wait_for_selector(".chat-a .chat-meta", timeout=AI_TIMEOUT)
        page.locator(".chat-a .chat-meta summary").last.click()
        s.save_tall(page, "11_coach_thank_you_draft", ".chat")
        page.locator(".chat-head .icon-btn").click()
        page.wait_for_selector(".outbox .draft", timeout=30_000)
        s.save(page, "12_outbox", ".outbox")

        page.locator(".stat-ask").click()
        page.wait_for_selector(".chat", timeout=10_000)
        page.locator(".chat-new").click()
        page.locator(".chat-input textarea").fill(CALL_PREP)
        s.ai(page, lambda u: u.endswith("/api/chat"), lambda: page.locator(".chat-input textarea").press("Enter"))
        page.wait_for_selector(".chat-a .chat-meta", timeout=AI_TIMEOUT)
        s.save_tall(page, "13_call_prep", ".chat")
        page.locator(".chat-head .icon-btn").click()
        page.wait_for_timeout(400)

        # Who can open the door, on one opportunity card.
        tab(page, "Opportunities")
        page.locator(".card", has_text=DOOR_CARD).first.dblclick()  # one click folds a card open, two open its sheet
        page.wait_for_selector(".sheet .doors", timeout=10_000)
        s.ai(page, lambda u: u.endswith("/doors"), lambda: page.locator(".doors .toggle").click())
        page.wait_for_selector(".door-list li", timeout=AI_TIMEOUT)
        page.locator(".doors .how-decided summary").click()
        page.locator(".door-list details summary").first.click()
        size = page.viewport_size or VIEW
        page.set_viewport_size({"width": size["width"], "height": 3000})  # the whole sheet fits, nothing scrolls inside it
        page.wait_for_timeout(300)
        s.save_union(page, "14_who_can_open_the_door", [".sheet .doors"], pad=16, fixed=True)
        page.set_viewport_size(size)
        close_sheet(page)

        tab(page, "Networking")
        page.wait_for_selector(".board .card-company", timeout=30_000)
        s.save(page, "15_networking", full=True)

        page.locator(".account .toggle", has_text="Usage").click()
        page.wait_for_selector(".usage-table tbody tr", timeout=30_000)
        s.save_tall(page, "16_usage_costs", ".usage-sheet")
        page.keyboard.press("Escape")

        # The same account on a phone-width screen.
        phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True,
                                    has_touch=True, storage_state=ctx.storage_state())
        mp = phone.new_page()
        mp.goto(f"{base}/#today", wait_until="networkidle", timeout=120_000)
        mp.wait_for_selector(".coach-panel", timeout=60_000)
        s.save(mp, "17_mobile_today")
        phone.close()

        write_runs(page, base, s)

        if args.with_signup:  # a brand-new account: the first-run guide (the account is deleted at the end)
            fresh = browser.new_context(viewport=VIEW, device_scale_factor=2).new_page()
            fresh.goto(base, wait_until="networkidle", timeout=120_000)
            fresh.locator(".auth-switch button", has_text="Create account").click()
            fresh.fill("input[type=email]", f"screenshot-{secrets.token_hex(4)}@example.com")
            fresh.fill("input[type=password]", "a-long-password-1")
            fresh.locator(".auth-form .auth-button").click()
            fresh.wait_for_selector(".guide", timeout=60_000)
            s.save(fresh, "19_new_account_guide")
            fresh.locator(".account .toggle", has_text="Profile").click()
            fresh.locator(".danger-btn").click()
            fresh.locator(".danger-btn", has_text="Yes, delete everything").click()
            fresh.wait_for_selector(".landing", timeout=30_000)
        browser.close()
    print(f"Saved to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
