"""Build report.html: one self-contained file, every screenshot embedded, no external resources.

Inputs (all in the repo):
  docs/report/report_source.html   the text of the report, with {{CSS}}, {{SVG:name}} and {{TABLE:name}} markers and
                                   <img data-shot="file.png" data-width="px" [data-crop="bottom" | "top,bottom"]> for
                                   screenshots; a bare file name is looked up in SHOT_DIRS (in order), or give
                                   "folder/file.png" relative to docs/evidence/screenshots/
  docs/report/report.css           styles (letter-size print)
  docs/report/architecture.svg     the delegation diagram, drawn from the code
  docs/evidence/...                the numbers behind the generated tables (never typed by hand):
    screenshots/2026-10-26_live/runs.json (morning session), screenshots/2026-10-26_live_web/runs.json (web features),
    runs/2026-10-26_tokenomics_live.json, runs/2026-10-26_cost_model.json (v2, web search fees included),
    docs/research/competitors.json (hosting prices)

Output: ../submission/report.html next to the repo (the Canvas file), or --out PATH.

Images: large PNGs are re-encoded as JPEG and scaled to the width they are printed at, using macOS's built-in `sips`
(or Pillow if installed); if neither exists the PNG is embedded as it is. Standard library only.

Usage:
  python3 docs/report/build_report.py                      # build
  python3 docs/report/build_report.py --pdf /tmp/r.pdf     # build, print with headless Chrome, count the pages
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SHOT_ROOT = REPO / "docs" / "evidence" / "screenshots"
SHOTS = SHOT_ROOT / "2026-10-26_live"  # the morning session (runs.json used by the report and the slides)
SHOTS_WEB = SHOT_ROOT / "2026-10-26_live_web"  # the afternoon session: preferences form and the web features
SHOT_DIRS = (SHOTS, SHOTS_WEB)
RUNS = REPO / "docs" / "evidence" / "runs"
RESEARCH = REPO / "docs" / "research"
DEFAULT_OUT = REPO.parent / "submission" / "report.html"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
JPEG_QUALITY = 80

# What each run of the screenshot session was (the run ids are printed on the screenshots and in runs.json).
RUN_LABELS = {
    "3057c579ec75": ("Setup guide", "WhatsApp question"),
    "c469f1ee77fc": ("Plan my week", "both specialists"),
    "fa319fb53b37": ("Add what's new", "injected instructions"),
    "2bbe610b4159": ("Add what's new", "hidden text"),
    "16bac70cde0d": ("Add what's new", "names only, nothing saved"),
    "c9fea27d4495": ("Add what's new", "target list with roles"),
    "924006932786": ("Find openings", "8 organisations"),
    "6939e33cfb41": ("Ask your coach", "thank-you draft"),
    "2780889ce0f4": ("Ask your coach", "call prep"),
    "affe3255c214": ("Who can open the door", "Northbridge"),
    "d1161ab12736": ("Search the whole web", "shortlist, 2 of 4 confirmed"),
    "be2afd11acd4": ("Key people and alumni", "DICK'S Sporting Goods"),
    "692b493b6c59": ("Ask your coach", "NBA internship, web"),
}
AGENT_SHORT = {"strategist": "Coach", "scout": "Scout", "network": "Network", "inbox": "Inbox", "guide": "Guide"}
KIND_LABELS = {
    "plan": "Plan my week", "discover": "Find openings (job boards)", "chat": "Ask your coach (chat, call prep)",
    "intake": "Add what's new (one text)", "doors": "Who can open the door", "guide": "Setup guide answer",
}
KIND_ORDER = ["plan", "discover", "chat", "intake", "doors", "guide"]
SHORT_KIND = {"intake": "items", "plan": "plans", "chat": "chats", "discover": "searches", "doors": "doors", "guide": "guide",
              "chat_with_web": "web chats", "web_shortlist": "web shortlists", "key_people": "people searches"}
SCALE_KIND = {"discover": "job-board searches", "guide": "Setup guide"}  # clearer labels in the report's scale table
WEB_KINDS = ("web_shortlist", "key_people", "chat_with_web")  # cost_model.json v2: the requests that search the web
CHAT_COST_RUN = "dbc5b7ad586f"  # cost_model.json "chat" ($0.000707) is this live-database run's cost, not a median (checked Oct 26)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def n(x: float) -> str:
    return f"{int(round(x)):,}"


def usd(x: float, digits: int = 5) -> str:
    return f"${x:,.{digits}f}"


def esc(s: str) -> str:
    return html.escape(s, quote=False)


# ─── Tables generated from the evidence files ──────────────────────────────────────────────────────────────────
def token_cost(u: dict, prices: dict) -> float:
    return ((u["input"] - u["cached"]) * prices["input_per_m"] + u["cached"] * prices["cached_input_per_m"]
            + u["output"] * prices["output_per_m"]) / 1e6


def web_searches(u: dict, prices: dict) -> int:
    """Searches in a run: (logged cost - token cost) / $0.01 per search (OpenAI's price), checked to be a whole number."""
    fee = u["cost_usd"] - token_cost(u, prices)
    k = round(fee / WEB_SEARCH_PRICE)
    assert abs(fee - k * WEB_SEARCH_PRICE) < 1e-6, f"cost does not split into tokens + whole searches: {u}"
    return k


WEB_SEARCH_PRICE = 0.01  # backend/config.py PRICE_WEB_SEARCH_PER_CALL: "$10.00 / 1k calls"


def table_runs(*sessions: tuple[str, dict]) -> str:
    """Every run of each session (runs.json files), totals checked against each file's own total."""
    rows, grand = [], {"input": 0, "cached": 0, "output": 0, "requests": 0, "web": 0, "cost": 0.0, "n": 0}
    for title, runs in sessions:
        prices = runs["prices"]
        rows.append(f"<tr class='group'><td colspan='9'>{esc(title)}</td></tr>")
        tot = {"input": 0, "cached": 0, "output": 0, "requests": 0}
        for r in runs["runs"]:
            what, detail = RUN_LABELS.get(r["run_id"], (r["kind"], ""))
            u = r["usage"]
            k = web_searches(u, prices)
            agents = ", ".join(f"{AGENT_SHORT.get(a['agent'], a['agent'])} ({a['requests']})" for a in r["per_agent"])
            code = [a for a in r["agents_in_trace"] if a in ("shield", "router", "keeper")]
            if code:
                agents += " · code: " + ", ".join(code)
            rows.append(
                f"<tr><td><b>{esc(what)}</b> · {esc(detail)}<span class='sub'>run {r['run_id']}</span></td>"
                f"<td>{esc(agents)}</td><td class='num'>{n(u['input'])}</td><td class='num'>{n(u['cached'])}</td>"
                f"<td class='num'>{n(u['output'])}</td><td class='num'>{u['requests']}</td><td class='num'>{k or '–'}</td>"
                f"<td class='num'>{r['seconds']:.1f}</td><td class='num'>{usd(u['cost_usd'], 5 if u['cost_usd'] < 0.01 else 3)}</td></tr>")
            for key in tot:
                tot[key] += u[key]
            grand["web"] += k
            grand["cost"] += u["cost_usd"]
            grand["n"] += 1
        t = runs["total"]
        assert all(tot[key] == t[key] for key in tot), "runs.json totals do not match the sum of its runs"
        for key in tot:
            grand[key] += tot[key]
    rows.append(f"<tr class='total'><td>Total, {grand['n']} requests</td><td></td><td class='num'>{n(grand['input'])}</td>"
                f"<td class='num'>{n(grand['cached'])}</td><td class='num'>{n(grand['output'])}</td><td class='num'>{grand['requests']}</td>"
                f"<td class='num'>{grand['web']}</td><td></td><td class='num'>{usd(grand['cost'], 3)}</td></tr>")
    head = ("<thead><tr><th style='width:31%'>Request</th><th style='width:23%'>AI agents (model calls)</th>"
            "<th class='num'>Input</th><th class='num'>Cached</th><th class='num'>Output</th><th class='num'>Calls</th>"
            "<th class='num'>Web searches</th><th class='num'>Seconds</th><th class='num'>Cost</th></tr></thead>")
    return f"<table class='compact runs'>{head}<tbody>{''.join(rows)}</tbody></table>"


def table_kinds(live: dict) -> str:
    rows = []
    for k in KIND_ORDER:
        v = live["by_kind"][k]
        rows.append(
            f"<tr><td><b>{esc(KIND_LABELS[k])}</b></td><td class='num'>{v['n']}</td><td class='num'>{n(v['median_input'])}</td>"
            f"<td class='num'>{n(v['median_cached'])}</td><td class='num'>{n(v['median_output'])}</td>"
            f"<td class='num'>{n(v['median_requests'])}</td><td class='num'>{usd(v['median_cost_usd'])}</td>"
            f"<td class='num'>{usd(v['min_cost_usd'])} – {usd(v['max_cost_usd'])}</td></tr>")
    t = live["totals_ok"]
    share = t["cached"] / t["input"]
    rows.append(f"<tr class='total'><td>All {live['requests_total']} requests ({live['model_calls']} model calls)</td><td class='num'>"
                f"{live['requests_total']}</td><td class='num'>{n(t['input'])}</td><td class='num'>{n(t['cached'])}</td>"
                f"<td class='num'>{n(t['output'])}</td><td></td><td class='num'>{usd(t['cost_usd'])}</td>"
                f"<td class='num'>{share:.0%} of input cached</td></tr>")
    head = ("<thead><tr><th style='width:30%'>Kind of request</th><th class='num'>Runs</th><th class='num'>Median input</th>"
            "<th class='num'>Median cached</th><th class='num'>Median output</th><th class='num'>Calls</th>"
            "<th class='num'>Median cost</th><th class='num'>Range</th></tr></thead>")
    return f"<table class='compact'>{head}<tbody>{''.join(rows)}</tbody></table>"


def table_scale(cost: dict, research: dict, live: dict | None = None) -> str:
    """Measured cost per request x an ESTIMATED month of use (cost_model.json), plus the paid-hosting arithmetic.
    Called by build_slides.py too, so its checks run on both builds."""
    per = cost["cost_per_request_usd"]
    if live:  # the non-web costs are Table 3's medians, except the coach chat (labelled in the note)
        for k in ("plan", "discover", "intake", "doors", "guide"):
            assert abs(per[k] - live["by_kind"][k]["median_cost_usd"]) < 1e-6, f"cost_model.json {k} is not Table 3's median"
    hosting = {h["plan"]: h for h in research["hosting"]}
    small = 7 + 25   # Render Starter + Supabase Pro (list prices in competitors.json "hosting")
    school = 25 + 25 + 25  # Render Pro workspace + Standard instance + Supabase Pro
    assert any("Starter" in p and h["price"].startswith("$7/") for p, h in hosting.items())
    assert any("Standard" in p and h["price"].startswith("$25/") for p, h in hosting.items())
    assert any(p.startswith("Workspace Pro") and h["price"].startswith("$25/") for p, h in hosting.items())
    assert any(h["name"] == "Supabase" and p == "Pro" and "$25/month" in h["price"] for p, h in hosting.items())
    rows = []
    for name in ("typical", "heavy"):
        mix = cost["requests_per_month"][name]
        s = cost["scenarios"][name]
        calc = sum(mix[k] * per[k] for k in mix)
        assert abs(calc - s["per_user_month_usd"]) < 0.0001, "cost_model.json scenario does not match its own inputs"
        assert sum(mix.values()) == s["requests"], "cost_model.json request count does not match its mix"
        web = sum(mix[k] * per[k] for k in WEB_KINDS if k in mix)
        if "web_share" in s:
            assert abs(web / calc - s["web_share"]) < 0.005, "cost_model.json web share does not match its inputs"
        mix_txt = " · ".join(f"{mix[k]} {SCALE_KIND.get(k, SHORT_KIND[k])}" for k in mix if mix[k])
        t100, t10k = calc * 100, calc * 10_000
        rows.append(
            f"<tr><td><b>{name.capitalize()} student</b> <span class='estimate'>estimate</span><span class='sub'>{s['requests']} requests a month "
            f"({esc(mix_txt)})</span></td><td class='num'>{usd(calc, 2)}</td><td class='num'>{web / calc:.0%}</td>"
            f"<td class='num'>{usd(t100, 2)}</td><td class='num'>{usd(t10k, 0)}</td>"
            f"<td class='num'>{usd(t100 + small, 2)}<span class='sub'>{usd((t100 + small) / 100, 2)} per student</span></td>"
            f"<td class='num'>{usd(t10k + school, 0)}<span class='sub'>{usd((t10k + school) / 10_000, 2)} per student</span></td></tr>")
    head = ("<thead><tr><th style='width:33%'>Scenario (measured cost per request × estimated use)</th>"
            "<th class='num' style='width:9%'>Per student / month</th><th class='num' style='width:8%'>Web share</th>"
            "<th class='num' style='width:10%'>100 students</th><th class='num' style='width:10%'>10,000 students</th>"
            "<th class='num' style='width:14%'>100 + hosting $32</th><th class='num' style='width:16%'>10,000 + hosting $75</th></tr></thead>")
    web_txt = ", ".join(f"{label} {usd(per[k], 3)}" for k, label in
                        (("web_shortlist", "web shortlist"), ("key_people", "key people"), ("chat_with_web", "chat that searched the web")) if k in per)
    note = (f"<p class='tablenote'><b>Table 4. Cost per month.</b> Per-request costs used (medians of logged live runs except the coach chat; web features: the measured runs of Table 2): "
            f"plan {usd(per['plan'])}, job-board search {usd(per['discover'])}, coach chat {usd(per['chat'])} (not a median: one logged coach "
            f"chat that consulted a specialist, run {CHAT_COST_RUN}" + (f"; Table 3's chat median, call prep included, is "
            f"{usd(live['by_kind']['chat']['median_cost_usd'])}" if live else "") + f"), intake {usd(per['intake'])}, "
            f"doors {usd(per['doors'])}, Setup guide {usd(per['guide'])}" + (f"; {web_txt}" if web_txt else "") +
            ". <i>Web share</i> = the share of the month spent on the three web features, search fees and their tokens. Portkey's fee is not included.</p>")
    return f"<table class='compact' style='table-layout:fixed'>{head}<tbody>{''.join(rows)}</tbody></table>{note}"


# ─── Images ────────────────────────────────────────────────────────────────────────────────────────────────────
def png_size(path: Path) -> tuple[int, int]:
    b = path.read_bytes()[:32]
    return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")


def shot_path(name: str) -> Path:
    """A screenshot by bare file name (searched in SHOT_DIRS, in order) or as "folder/file.png" under SHOT_ROOT."""
    if "/" in name:
        return SHOT_ROOT / name
    for d in SHOT_DIRS:
        if (d / name).is_file():
            return d / name
    return SHOTS / name


def encode_image(path: Path, width: int, crop: int | tuple[int, int] | None, tmp: Path) -> tuple[str, str]:
    """(mime, base64) of the screenshot, scaled to `width` px and optionally cropped: to its top `crop` px, or to the
    rows top..bottom when crop is a (top, bottom) pair."""
    w, h = png_size(path)
    top, bottom = (0, crop) if isinstance(crop, int) else (crop or (0, None))
    bottom = min(bottom or h, h)
    if shutil.which("sips"):
        src = path
        if crop and (top > 0 or bottom < h):
            src = tmp / f"crop_{top}_{bottom}_{path.name}"
            # sips treats an offset of 0 as "not set" and centres the crop; 1 px from the top keeps the top part
            subprocess.run(["sips", "--cropToHeightWidth", str(bottom - top), str(w), "--cropOffset", str(max(top, 1)), "0",
                            str(path), "--out", str(src)], check=True, capture_output=True)
        out = tmp / f"{path.stem}_{top}_{bottom}.jpg"
        cmd = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(JPEG_QUALITY)]
        if w > width:
            cmd += ["--resampleWidth", str(width)]
        subprocess.run(cmd + [str(src), "--out", str(out)], check=True, capture_output=True)
        return "image/jpeg", base64.b64encode(out.read_bytes()).decode()
    try:
        from PIL import Image  # optional
        im = Image.open(path).convert("RGB")
        if crop:
            im = im.crop((0, top, im.width, bottom))
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)))
        out = tmp / f"{path.stem}_{top}_{bottom}.jpg"
        im.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return "image/jpeg", base64.b64encode(out.read_bytes()).decode()
    except ImportError:
        return "image/png", base64.b64encode(path.read_bytes()).decode()  # embedded as it is (crop via CSS only)


def embed_images(doc: str, tmp: Path) -> tuple[str, list[str]]:
    used: list[str] = []

    def repl(m: re.Match) -> str:
        tag = m.group(0)
        name = re.search(r'data-shot="([^"]+)"', tag).group(1)
        width_m = re.search(r'data-width="(\d+)"', tag)
        width = int(width_m.group(1)) if width_m else 1400
        crop_m = re.search(r'data-crop="(\d+)(?:,(\d+))?"', tag)
        crop = None
        if crop_m:
            crop = (int(crop_m.group(1)), int(crop_m.group(2))) if crop_m.group(2) else int(crop_m.group(1))
        path = shot_path(name)
        if not path.is_file():
            raise SystemExit(f"Missing screenshot: {path}")
        mime, data = encode_image(path, width, crop, tmp)
        used.append(name)
        tag = re.sub(r'\sdata-(shot|width|crop)="[^"]*"', "", tag)
        return tag.replace("<img", f'<img src="data:{mime};base64,{data}"', 1)

    return re.sub(r"<img\b[^>]*\bdata-shot=\"[^\"]+\"[^>]*>", repl, doc), used


# ─── Build ─────────────────────────────────────────────────────────────────────────────────────────────────────
def build(out: Path) -> Path:
    doc = (HERE / "report_source.html").read_text(encoding="utf-8")
    css = (HERE / "report.css").read_text(encoding="utf-8")
    runs = load(SHOTS / "runs.json")
    web_runs = load(SHOTS_WEB / "runs.json")
    live = load(RUNS / "2026-10-26_tokenomics_live.json")
    cost = load(RUNS / "2026-10-26_cost_model.json")
    research = load(RESEARCH / "competitors.json")
    svg = (HERE / "architecture.svg").read_text(encoding="utf-8")
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S).strip()

    doc = re.sub(r"<!--(?!\s*\[).*?-->", "", doc, flags=re.S)  # source comments stay in the source
    tables = {"runs": table_runs(("Morning session, Oct 26 (screenshots 01–20): every agent", runs),
                                 ("Afternoon session, Oct 26 (screenshots 21–25): the web features", web_runs)),
              "kinds": table_kinds(live), "scale": table_scale(cost, research, live)}
    doc = doc.replace("{{CSS}}", css).replace("{{SVG:architecture}}", svg)
    for name, t in tables.items():
        doc = doc.replace("{{TABLE:" + name + "}}", t)
    left = re.findall(r"\{\{[A-Z]+(?::[a-z]+)?\}\}", doc)
    if left:
        raise SystemExit(f"Unfilled markers: {left}")

    with tempfile.TemporaryDirectory() as tmp:
        doc, used = embed_images(doc, Path(tmp))

    # Self-contained: no external stylesheet, script, font or image; links are only the two project URLs.
    assert not re.search(r"<(link|script)\b", doc, re.I), "external resource tag found"
    assert not re.search(r"""(src|href)\s*=\s*["'](?!data:|https://summer-internship-coach\.onrender\.com|https://github\.com/aymonpadillahernandez/summer_internship_coach_aymon|#)""", doc), \
        "a src/href points outside the file"
    assert "@import" not in doc and "url(http" not in doc
    for must in ("https://github.com/aymonpadillahernandez/summer_internship_coach_aymon",
                 "https://summer-internship-coach.onrender.com", "public"):
        assert must in doc, must

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.2f} MB, {len(used)} screenshots: {', '.join(used)})")
    return out


def count_pdf_pages(pdf: Path) -> int:
    try:
        from pypdf import PdfReader  # in the backend venv
        return len(PdfReader(str(pdf)).pages)
    except ImportError:
        return len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))


def print_pdf(report: Path, pdf: Path) -> int:
    if not Path(CHROME).is_file():
        raise SystemExit("Google Chrome not found: print preview the report by hand instead.")
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}",
                    report.resolve().as_uri()], check=True, capture_output=True, timeout=120)
    pages = count_pdf_pages(pdf)
    print(f"Printed {pdf}: {pages} letter pages")
    return pages


def section_words(report: Path) -> list[tuple[str, int]]:
    """Visible words per section (tables and captions included, embedded images and styles excluded)."""
    doc = report.read_text(encoding="utf-8")
    doc = re.sub(r"<style.*?</style>|<svg.*?</svg>", " ", doc, flags=re.S)
    out = []
    for sec in re.findall(r"<section\b.*?</section>", doc, flags=re.S):
        title = re.search(r"<h[12]\b[^>]*>(.*?)</h[12]>", sec, flags=re.S)
        text = html.unescape(re.sub(r"<[^>]+>", " ", sec))
        name = re.sub(r"<[^>]+>", " ", title.group(1)).strip() if title else "?"
        out.append((re.sub(r"\s+", " ", name), len(text.split())))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--pdf", type=Path, help="also print to this PDF with headless Chrome and count the pages")
    args = ap.parse_args()
    report = build(args.out)
    for name, words in section_words(report):
        print(f"  {words:5d} words  {name}")
    if args.pdf:
        pages = print_pdf(report, args.pdf)
        if not 10 <= pages <= 15:
            print(f"WARNING: {pages} pages; the brief asks for 10-15.", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
