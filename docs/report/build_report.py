"""Build report.html: one self-contained file, every screenshot embedded, no external resources.

Inputs (all in the repo):
  docs/report/report_source.html   the text of the report, with {{CSS}}, {{SVG:name}} and {{TABLE:name}} markers and
                                   <img data-shot="file.png" data-width="px" [data-crop="px"]> for screenshots
  docs/report/report.css           styles (letter-size print)
  docs/report/architecture.svg     the delegation diagram, drawn from the code
  docs/evidence/...                the numbers behind the generated tables (never typed by hand):
    screenshots/2026-10-26_live/runs.json, runs/2026-10-26_tokenomics_live.json, runs/2026-10-26_cost_model.json,
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
SHOTS = REPO / "docs" / "evidence" / "screenshots" / "2026-10-26_live"
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
}
AGENT_SHORT = {"strategist": "Coach", "scout": "Scout", "network": "Network", "inbox": "Inbox", "guide": "Guide"}
KIND_LABELS = {
    "plan": "Plan my week", "discover": "Find openings (job boards)", "chat": "Ask your coach (chat, call prep)",
    "intake": "Add what's new (one text)", "doors": "Who can open the door", "guide": "Setup guide answer",
}
KIND_ORDER = ["plan", "discover", "chat", "intake", "doors", "guide"]
SHORT_KIND = {"intake": "items", "plan": "plans", "chat": "chats", "discover": "searches", "doors": "doors", "guide": "guide"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def n(x: float) -> str:
    return f"{int(round(x)):,}"


def usd(x: float, digits: int = 5) -> str:
    return f"${x:,.{digits}f}"


def esc(s: str) -> str:
    return html.escape(s, quote=False)


# ─── Tables generated from the evidence files ──────────────────────────────────────────────────────────────────
def table_runs(runs: dict) -> str:
    rows, tot = [], {"input": 0, "cached": 0, "output": 0, "requests": 0, "cost": 0.0}
    for r in runs["runs"]:
        what, detail = RUN_LABELS.get(r["run_id"], (r["kind"], ""))
        u = r["usage"]
        agents = ", ".join(f"{AGENT_SHORT.get(a['agent'], a['agent'])} ({a['requests']})" for a in r["per_agent"])
        code = [a for a in r["agents_in_trace"] if a in ("shield", "router", "keeper")]
        if code:
            agents += " · code: " + ", ".join(code)
        rows.append(
            f"<tr><td><b>{esc(what)}</b> · {esc(detail)}<span class='sub'>run {r['run_id']}</span></td>"
            f"<td>{esc(agents)}</td><td class='num'>{n(u['input'])}</td><td class='num'>{n(u['cached'])}</td>"
            f"<td class='num'>{n(u['output'])}</td><td class='num'>{u['requests']}</td><td class='num'>{r['seconds']:.1f}</td>"
            f"<td class='num'>{usd(u['cost_usd'])}</td></tr>")
        for k in ("input", "cached", "output", "requests"):
            tot[k] += u[k]
        tot["cost"] += u["cost_usd"]
    t = runs["total"]
    assert (tot["input"], tot["cached"], tot["output"], tot["requests"]) == (t["input"], t["cached"], t["output"], t["requests"]), \
        "runs.json totals do not match the sum of its runs"
    rows.append(f"<tr class='total'><td>Total, {len(runs['runs'])} requests</td><td></td><td class='num'>{n(tot['input'])}</td>"
                f"<td class='num'>{n(tot['cached'])}</td><td class='num'>{n(tot['output'])}</td><td class='num'>{tot['requests']}</td>"
                f"<td></td><td class='num'>{usd(tot['cost'])}</td></tr>")
    head = ("<thead><tr><th style='width:34%'>Request</th><th style='width:24%'>AI agents (model calls)</th>"
            "<th class='num'>Input</th><th class='num'>Cached</th><th class='num'>Output</th><th class='num'>Calls</th>"
            "<th class='num'>Seconds</th><th class='num'>Cost</th></tr></thead>")
    return f"<table class='compact'>{head}<tbody>{''.join(rows)}</tbody></table>"


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


def table_scale(cost: dict, research: dict) -> str:
    per = cost["cost_per_request_usd"]
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
        mix_txt = " · ".join(f"{mix[k]} {SHORT_KIND[k]}" for k in ("intake", "plan", "chat", "discover", "doors", "guide"))
        t100, t10k = calc * 100, calc * 10_000
        rows.append(
            f"<tr><td><b>{name.capitalize()} student</b> <span class='estimate'>estimate</span><span class='sub'>{s['requests']} requests a month "
            f"({esc(mix_txt)})</span></td><td class='num'>{usd(calc, 3)}</td><td class='num'>{usd(t100, 2)}</td>"
            f"<td class='num'>{usd(t10k, 0)}</td><td class='num'>{usd(t100 + small, 2)}<span class='sub'>{usd((t100 + small) / 100, 2)} per student</span></td>"
            f"<td class='num'>{usd(t10k + school, 0)}<span class='sub'>{usd((t10k + school) / 10_000, 3)} per student</span></td></tr>")
    head = ("<thead><tr><th style='width:31%'>Scenario (measured cost per request × estimated use)</th>"
            "<th class='num' style='width:12%'>Per student / month</th><th class='num' style='width:11%'>100 students</th>"
            "<th class='num' style='width:12%'>10,000 students</th><th class='num' style='width:16%'>100 + hosting $32</th>"
            "<th class='num' style='width:18%'>10,000 + hosting $75</th></tr></thead>")
    note = (f"<p class='tablenote'>Per-request costs used: plan {usd(per['plan'])}, job-board search {usd(per['discover'])}, chat "
            f"{usd(per['chat'])}, intake {usd(per['intake'])}, doors {usd(per['doors'])}, Setup guide {usd(per['guide'])}. "
            "Hosting columns add the paid-plan arithmetic described below; Portkey's fee is not included.</p>")
    return f"<table class='compact' style='table-layout:fixed'>{head}<tbody>{''.join(rows)}</tbody></table>{note}"


# ─── Images ────────────────────────────────────────────────────────────────────────────────────────────────────
def png_size(path: Path) -> tuple[int, int]:
    b = path.read_bytes()[:32]
    return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")


def encode_image(path: Path, width: int, crop: int | None, tmp: Path) -> tuple[str, str]:
    """(mime, base64) of the screenshot, scaled to `width` px and optionally cropped to its top `crop` px."""
    w, h = png_size(path)
    if shutil.which("sips"):
        src = path
        if crop and crop < h:
            src = tmp / f"crop_{path.name}"
            # sips treats an offset of 0 as "not set" and centres the crop; 1 px from the top keeps the top part
            subprocess.run(["sips", "--cropToHeightWidth", str(crop), str(w), "--cropOffset", "1", "0", str(path),
                            "--out", str(src)], check=True, capture_output=True)
        out = tmp / (path.stem + ".jpg")
        cmd = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(JPEG_QUALITY)]
        if w > width:
            cmd += ["--resampleWidth", str(width)]
        subprocess.run(cmd + [str(src), "--out", str(out)], check=True, capture_output=True)
        return "image/jpeg", base64.b64encode(out.read_bytes()).decode()
    try:
        from PIL import Image  # optional
        im = Image.open(path).convert("RGB")
        if crop and crop < im.height:
            im = im.crop((0, 0, im.width, crop))
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)))
        out = tmp / (path.stem + ".jpg")
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
        crop_m = re.search(r'data-crop="(\d+)"', tag)
        path = SHOTS / name
        if not path.is_file():
            raise SystemExit(f"Missing screenshot: {path}")
        mime, data = encode_image(path, width, int(crop_m.group(1)) if crop_m else None, tmp)
        used.append(name)
        tag = re.sub(r'\sdata-(shot|width|crop)="[^"]*"', "", tag)
        return tag.replace("<img", f'<img src="data:{mime};base64,{data}"', 1)

    return re.sub(r"<img\b[^>]*\bdata-shot=\"[^\"]+\"[^>]*>", repl, doc), used


# ─── Build ─────────────────────────────────────────────────────────────────────────────────────────────────────
def build(out: Path) -> Path:
    doc = (HERE / "report_source.html").read_text(encoding="utf-8")
    css = (HERE / "report.css").read_text(encoding="utf-8")
    runs = load(SHOTS / "runs.json")
    live = load(RUNS / "2026-10-26_tokenomics_live.json")
    cost = load(RUNS / "2026-10-26_cost_model.json")
    research = load(RESEARCH / "competitors.json")
    svg = (HERE / "architecture.svg").read_text(encoding="utf-8")
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S).strip()

    doc = re.sub(r"<!--(?!\s*\[).*?-->", "", doc, flags=re.S)  # source comments stay in the source
    tables = {"runs": table_runs(runs), "kinds": table_kinds(live), "scale": table_scale(cost, research)}
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
