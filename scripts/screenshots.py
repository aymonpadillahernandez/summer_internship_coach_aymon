"""Evidence screenshots: drive the real app through one full demo session and save PNGs for the report.

    backend/.venv/bin/python -m pip install playwright      (dev tool, uses the installed Google Chrome)
    backend/.venv/bin/python scripts/screenshots.py --base http://127.0.0.1:8020
    backend/.venv/bin/python scripts/screenshots.py --base https://summer-internship-coach.onrender.com

Every AI step here is a real gpt-6-luna run (about 20K tokens in total). Files go to
docs/evidence/screenshots/<date>_<base>/, numbered in the order a new user would see them.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
AI_TIMEOUT = 120_000  # ms: a plan can take ~20 s, longer on a cold free-tier server


def shot(page: Page, out: Path, name: str, selector: str | None = None) -> None:
    page.wait_for_timeout(600)  # let transitions settle
    path = out / f"{name}.png"
    (page.locator(selector).first.screenshot(path=str(path)) if selector else page.screenshot(path=str(path)))
    print(f"  {path.relative_to(ROOT)}")


def intake(page: Page, sample: str) -> None:
    page.locator(".sample-chip", has_text=sample).click()
    page.locator(".intake-panel .primary-btn").click()
    page.wait_for_selector(".intake-result", timeout=AI_TIMEOUT)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8020")
    args = ap.parse_args()
    tag = re.sub(r"[^a-z0-9]+", "-", args.base.split("//")[-1].lower()).strip("-")
    out = ROOT / "docs" / "evidence" / "screenshots" / f"{date.today().isoformat()}_{tag}"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2).new_page()
        page.goto(args.base, wait_until="networkidle", timeout=120_000)
        shot(page, out, "01_landing")
        page.locator(".demo-button").click()
        page.wait_for_selector(".coach-panel", timeout=60_000)
        # Screenshot-only layout: let the page grow and unpin the top bar, so a tall panel is captured whole.
        page.add_style_tag(content=".app{height:auto} .today{overflow:visible} .topbar{position:static}")
        shot(page, out, "02_today")

        page.locator(".coach-panel .primary-btn").click()
        page.wait_for_selector(".plan-actions", timeout=AI_TIMEOUT)
        page.wait_for_selector(".working", state="detached", timeout=AI_TIMEOUT)
        shot(page, out, "03_plan")
        page.locator(".coach-panel .how-decided summary").click()
        shot(page, out, "04_plan_trace", ".coach-panel")

        intake(page, "instructions in a posting")
        shot(page, out, "05_attack_injected_instructions", ".intake-panel")
        page.locator(".intake-panel .how-decided summary").click()
        shot(page, out, "06_attack_injected_trace", ".intake-panel")
        intake(page, "hidden text in a web page")
        shot(page, out, "07_attack_hidden_text", ".intake-panel")
        intake(page, "An email thread")
        shot(page, out, "08_intake_email", ".intake-panel")

        for tab, name in (("Opportunities", "09_opportunities"), ("Networking", "10_networking"), ("Action plan", "11_action_plan")):
            page.locator(".view-switch button", has_text=tab).click()
            shot(page, out, name)

        page.locator(".account .toggle", has_text="Usage").click()
        page.wait_for_selector(".usage-table tbody tr", timeout=30_000)
        shot(page, out, "12_usage", ".usage-sheet")
        page.keyboard.press("Escape")

        page.locator(".stat-ask").click()
        page.locator(".chat-suggestions button", has_text="Prepare my next call").click()
        page.wait_for_selector(".chat-a .chat-meta", timeout=AI_TIMEOUT)
        shot(page, out, "13_call_prep", ".chat")
        browser.close()
    print(f"Saved to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
