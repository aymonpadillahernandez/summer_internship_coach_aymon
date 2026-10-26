"""Screenshots of the one-stop-shop additions on the live site (Oct 26): the preferences form, the whole-web search,
key people and alumni on a card, and a Career coach answer that uses the web. Demo account only.

  backend/.venv/bin/python scripts/screenshots_web.py --base https://summer-internship-coach.onrender.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screenshots as S  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

FOCUS = "strategy or business development in sports, media and entertainment"
QUESTION = "What does the NBA's 2027 summer internship program involve, and when do applications open? Please check the web."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://summer-internship-coach.onrender.com")
    args = ap.parse_args()
    out = S.ROOT / "docs" / "evidence" / "screenshots" / "2026-10-26_live_web"
    out.mkdir(parents=True, exist_ok=True)
    s = S.Shots(out)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_context(viewport=S.VIEW, device_scale_factor=2).new_page()
        page.goto(args.base, wait_until="networkidle", timeout=120_000)
        page.locator(".demo-button").click()
        page.wait_for_selector(".coach-panel", timeout=60_000)
        page.add_style_tag(content=S.GROW_CSS)

        S.tab(page, "Setup")
        page.locator(".prefs-summary .primary-btn").click()
        page.wait_for_selector(".prefs-form", timeout=20_000)
        s.save(page, "21_preferences_form", ".prefs-form")
        page.locator(".prefs-form .toggle").last.click()
        page.wait_for_timeout(400)
        s.save(page, "22_setup_with_preferences", ".prefs-summary")

        S.tab(page, "Today")
        page.wait_for_selector(".discover-actions", timeout=20_000)
        page.locator(".discover-actions input").fill(FOCUS)
        r = s.ai(page, lambda u: u.endswith("/api/scout/web"), lambda: page.locator(".discover-actions .primary-btn").click())
        page.wait_for_selector(".discover .intake-result", timeout=S.AI_TIMEOUT)
        page.locator(".discover .how-decided summary").click()
        page.wait_for_timeout(300)
        s.save_tall(page, "23_web_shortlist", ".discover")

        saved = (r.get("saved") or {}).get("opportunities_added", []) + (r.get("saved") or {}).get("opportunities_updated", [])
        if saved:
            S.tab(page, "Opportunities")
            page.locator(".card", has_text=saved[0]["company"]).first.dblclick()
            page.wait_for_selector(".sheet .people-web", timeout=15_000)
            s.ai(page, lambda u: u.endswith("/people"), lambda: page.locator(".people-web .toggle").click())
            page.wait_for_selector(".people-list li", timeout=S.AI_TIMEOUT)
            page.locator(".people-web .how-decided summary").click()
            size = page.viewport_size or S.VIEW
            page.set_viewport_size({"width": size["width"], "height": 3000})
            page.wait_for_timeout(300)
            s.save_union(page, "24_key_people_and_alumni", [".sheet .people-web"], pad=16, fixed=True)
            page.set_viewport_size(size)
            S.close_sheet(page)
        else:
            print("  (no web result was confirmed, so no card for key people)", flush=True)

        page.locator(".stat-ask").click()
        page.wait_for_selector(".chat", timeout=10_000)
        if page.locator(".chat-new").count():
            page.locator(".chat-new").click()
        page.locator(".chat-input textarea").fill(QUESTION)
        s.ai(page, lambda u: u.endswith("/api/chat"), lambda: page.locator(".chat-input textarea").press("Enter"))
        page.wait_for_selector(".chat-a .chat-meta", timeout=S.AI_TIMEOUT)
        s.save_tall(page, "25_coach_web_answer", ".chat")
        S.write_runs(page, args.base, s)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
