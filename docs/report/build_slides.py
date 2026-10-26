"""Build slides.html: one reveal.js deck (≤10 slides), every screenshot embedded, the same numbers as report.html.

Inputs (all in the repo):
  docs/report/slides_source.html   the slides, with {{CSS}}, {{SVG:architecture}} and {{V:name}} markers, and
                                   <img data-shot="file.png" data-width="px" [data-crop="top,bottom"]> for screenshots
  docs/report/slides.css           styles (same palette as report.css, indigo #5e5ce6)
  docs/report/architecture.svg     the report's delegation diagram (Figure 3); a {{SVG:architecture}} marker embeds it,
                                   but slide 4 now draws a full-width HTML version so its labels stay large
  docs/evidence/...                the numbers (never typed by hand): screenshots/2026-10-26_live/runs.json,
                                   runs/2026-10-26_tokenomics_live.json, runs/2026-10-26_cost_model.json, docs/research/competitors.json
  render.yaml                      the live daily token budgets (slide 7's caps, at the output price)

Only reveal.js itself comes from a CDN (reveal.css + reveal.js from jsdelivr, as the brief asks); nothing else is loaded.

Checks on every build: ≤10 slides; the repo URL (and "public") on the first slide and again on the last; no external
resource other than the two CDN files; and every number in the slides' text also appears in report.html (a list of
any that do not is printed, so the two deliverables cannot drift apart silently).

Usage:
  python3 docs/report/build_slides.py                  # build ../submission/slides.html next to the repo
  python3 docs/report/build_slides.py --out PATH
"""

from __future__ import annotations

import argparse
import base64
import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_report as br  # noqa: E402  (shared loaders, formatting, image encoding and constants)

DEFAULT_OUT = br.REPO.parent / "submission" / "slides.html"
REPORT = br.REPO.parent / "submission" / "report.html"
REPO_URL = "https://github.com/aymonpadillahernandez/summer_internship_coach_aymon"
LIVE_URL = "https://summer-internship-coach.onrender.com"
CDN = ("https://cdn.jsdelivr.net/npm/reveal.js@5.2.1/dist/reveal.css",  # pinned: the deck was tested on 5.2.1
       "https://cdn.jsdelivr.net/npm/reveal.js@5.2.1/dist/reveal.js")
MAX_SLIDES = 10
PLAN_RUN = "c469f1ee77fc"          # the walkthrough run, same as the report
CALLPREP_RUN = "2780889ce0f4"
DOORS_RUN = "affe3255c214"
DISCOVER_RUN = "924006932786"
MEDIAN_ORDER = [("plan", "Plan my week"), ("discover", "Find openings"), ("chat", "Chat, call prep"),
                ("doors", "Who can open the door"), ("guide", "Setup guide"), ("intake", "Add what's new")]


# ─── Values from the evidence files ────────────────────────────────────────────────────────────────────────────
def values() -> dict[str, str]:
    runs = br.load(br.SHOTS / "runs.json")
    live = br.load(br.RUNS / "2026-10-26_tokenomics_live.json")
    cost = br.load(br.RUNS / "2026-10-26_cost_model.json")
    research = br.load(br.RESEARCH / "competitors.json")
    by_id = {r["run_id"]: r for r in runs["runs"]}
    plan = by_id[PLAN_RUN]
    u = plan["usage"]
    p = live["prices_per_1m"]
    uncached = u["input"] - u["cached"]
    plan_cost = (uncached * p["input"] + u["cached"] * p["cached_input"] + u["output"] * p["output"]) / 1e6
    assert abs(plan_cost - u["cost_usd"]) < 1e-9, "plan cost does not match runs.json"
    agents = {a["agent"]: a for a in plan["per_agent"]}
    assert sum(a["requests"] for a in plan["per_agent"]) == u["requests"]
    assert sum(a["input_tokens"] for a in plan["per_agent"]) == u["input"]

    v = {
        "plan_run": PLAN_RUN,
        "plan_in": br.n(u["input"]), "plan_cached": br.n(u["cached"]), "plan_out": br.n(u["output"]),
        "plan_uncached": br.n(uncached), "plan_calls": str(u["requests"]), "plan_secs": f"{plan['seconds']:.1f}",
        "plan_cost4": f"${plan_cost:.4f}", "plan_cost5": br.usd(plan_cost),
        "out_cost_share": f"{u['output'] * p['output'] / 1e6 / plan_cost:.0%}",
        "out_token_share": f"{u['output'] / (u['input'] + u['output']):.0%}",
        "scout_in": br.n(agents["scout"]["input_tokens"]), "scout_out": br.n(agents["scout"]["output_tokens"]),
        "network_in": br.n(agents["network"]["input_tokens"]), "network_out": br.n(agents["network"]["output_tokens"]),
        "live_requests": str(live["requests_total"]), "live_calls": str(live["model_calls"]),
        "callprep_secs": f"{by_id[CALLPREP_RUN]['seconds']:.1f}", "doors_secs": f"{by_id[DOORS_RUN]['seconds']:.1f}",
        "discover_secs": f"{by_id[DISCOVER_RUN]['seconds']:.1f}",
        "day_cap": f"${cost['worst_case_per_user_day_usd']:.2f}",
    }
    # Both daily caps from render.yaml (the live settings) at the output price: the most a day can cost.
    yaml = (br.REPO / "render.yaml").read_text(encoding="utf-8")
    budget = {k: int(x) for k, x in re.findall(r'key:\s*(\w*DAILY_TOKEN_BUDGET)\s*\n\s*value:\s*"(\d+)"', yaml)}
    assert abs(budget["DAILY_TOKEN_BUDGET"] * p["output"] / 1e6 - cost["worst_case_per_user_day_usd"]) < 1e-9
    v["site_cap"] = f"${budget['GLOBAL_DAILY_TOKEN_BUDGET'] * p['output'] / 1e6:.2f}"
    intakes = [r["seconds"] for r in runs["runs"] if r["kind"] == "intake"]
    v["intake_min"], v["intake_max"] = f"{min(intakes):.1f}", f"{max(intakes):.1f}"

    v["median_chips"] = "".join(
        f"<span class='chip'>{html.escape(label)} <b>{br.usd(live['by_kind'][k]['median_cost_usd'])}</b></span>"
        for k, label in MEDIAN_ORDER)

    # Same arithmetic and checks as the report's scale table (build_report.table_scale).
    br.table_scale(cost, research)
    per = cost["cost_per_request_usd"]
    rows = []
    for name in ("typical", "heavy"):
        mix, s = cost["requests_per_month"][name], cost["scenarios"][name]
        calc = sum(mix[k] * per[k] for k in mix)
        assert abs(calc - s["per_user_month_usd"]) < 0.0001
        if name == "typical":
            sub = f"{s['requests']} requests: " + ", ".join(f"{mix[k]} {br.SHORT_KIND[k]}" for k in ("intake", "plan", "chat", "discover", "doors", "guide"))
        else:
            ratio = s["requests"] / cost["scenarios"]["typical"]["requests"]
            sub = f"{s['requests']} requests, about {ratio:.1f} times the typical student"
        rows.append(f"<tr><td><b>{name.capitalize()} student</b><span class='sub'>{html.escape(sub)}</span></td>"
                    f"<td class='num'><b class='v'>{br.usd(calc, 3)}</b></td><td class='num'><b class='v'>{br.usd(calc * 100, 2)}</b></td>"
                    f"<td class='num'><b class='v'>{br.usd(calc * 10_000, 0)}</b></td></tr>")
        if name == "typical":
            v["typical_10k_hosted"] = br.usd(calc * 10_000 + 75, 0)  # + Render Pro workspace, Standard instance, Supabase Pro
    v["scale_rows"] = "".join(rows)
    return v


# ─── Images ────────────────────────────────────────────────────────────────────────────────────────────────────
def encode(path: Path, width: int, crop: tuple[int, int] | None, tmp: Path) -> tuple[str, str]:
    """(mime, base64) of the screenshot: rows top..bottom (its own pixels) if cropped, scaled to at most `width` px."""
    if not crop:
        return br.encode_image(path, width, None, tmp)
    top, bottom = crop
    w, h = br.png_size(path)
    bottom = min(bottom, h)
    if not shutil.which("sips"):
        try:
            from PIL import Image  # optional
        except ImportError:
            raise SystemExit("Cropping needs macOS sips or Pillow.")
        im = Image.open(path).convert("RGB").crop((0, top, w, bottom))
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)))
        out = tmp / f"{path.stem}_{top}_{bottom}.jpg"
        im.save(out, "JPEG", quality=br.JPEG_QUALITY, optimize=True)
        return "image/jpeg", base64.b64encode(out.read_bytes()).decode()
    cropped = tmp / f"crop_{top}_{bottom}_{path.name}"
    # sips reads an offset of 0 as "not set" and centres the crop, so the top offset is at least 1 px
    subprocess.run(["sips", "--cropToHeightWidth", str(bottom - top), str(w), "--cropOffset", str(max(top, 1)), "0",
                    str(path), "--out", str(cropped)], check=True, capture_output=True)
    out = tmp / f"{path.stem}_{top}_{bottom}.jpg"
    cmd = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(br.JPEG_QUALITY)]
    if w > width:
        cmd += ["--resampleWidth", str(width)]
    subprocess.run(cmd + [str(cropped), "--out", str(out)], check=True, capture_output=True)
    return "image/jpeg", base64.b64encode(out.read_bytes()).decode()


def embed_images(doc: str, tmp: Path) -> tuple[str, list[str]]:
    used: list[str] = []

    def repl(m: re.Match) -> str:
        tag = m.group(0)
        name = re.search(r'data-shot="([^"]+)"', tag).group(1)
        width = int(re.search(r'data-width="(\d+)"', tag).group(1))
        crop_m = re.search(r'data-crop="(\d+),(\d+)"', tag)
        path = br.SHOTS / name
        if not path.is_file():
            raise SystemExit(f"Missing screenshot: {path}")
        mime, data = encode(path, width, (int(crop_m.group(1)), int(crop_m.group(2))) if crop_m else None, tmp)
        used.append(name)
        tag = re.sub(r'\sdata-(shot|width|crop)="[^"]*"', "", tag)
        return tag.replace("<img", f'<img src="data:{mime};base64,{data}"', 1)

    return re.sub(r"<img\b[^>]*\bdata-shot=\"[^\"]+\"[^>]*>", repl, doc), used


# ─── Checks ────────────────────────────────────────────────────────────────────────────────────────────────────
NUM = re.compile(r"(?<![\w.$])\$?\d[\d,]*(?:\.\d+)?%?")


def visible_text(doc: str) -> str:
    doc = re.sub(r"<(style|script)\b.*?</\1>", " ", doc, flags=re.S)
    doc = re.sub(r"<!--.*?-->", " ", doc, flags=re.S)
    doc = re.sub(r"data:[^\"']+", " ", doc)
    return html.unescape(re.sub(r"<[^>]+>", " ", doc))


def numbers(text: str) -> set[str]:
    return {m.rstrip(",") for m in NUM.findall(text)}


def check(doc: str) -> list[str]:
    sections = re.findall(r"<section\b.*?</section>", doc, flags=re.S)
    assert 1 <= len(sections) <= MAX_SLIDES, f"{len(sections)} slides; the brief allows at most {MAX_SLIDES}"
    assert REPO_URL in sections[0] and "public" in sections[0], "the repo URL and 'public' must be on the first slide"
    assert REPO_URL in sections[-1], "the repo URL should repeat on the last slide"
    assert LIVE_URL in sections[0]
    for url in re.findall(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", doc):
        assert url.startswith(("data:", "#")) or url in CDN or url in (REPO_URL, LIVE_URL), f"external resource: {url[:80]}"
    assert "@import" not in doc and "url(http" not in doc
    assert all(c in doc for c in CDN), "reveal.js must be loaded from the CDN"
    assert not re.search(r"\{\{[A-Z]+(?::[a-z_]+)?\}\}", doc), "unfilled marker"

    if not REPORT.is_file():
        return ["(report.html not found: numbers not cross-checked)"]
    report_nums = numbers(visible_text(REPORT.read_text(encoding="utf-8")))
    return sorted(numbers(visible_text(doc)) - report_nums)


def number_footers(doc: str) -> str:
    """Put "n / total" at the right end of each slide's footer (reveal's own slide number would sit under its arrows)."""
    total = len(re.findall(r"<section\b", doc))
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        sec = m.group(0)
        return re.sub(r'(<div class="foot">.*?)(</div>)', lambda f: f"{f.group(1)}<span class=\"pg\">{count} / {total}</span>{f.group(2)}",
                      sec, count=1, flags=re.S)

    return re.sub(r"<section\b.*?</section>", repl, doc, flags=re.S)


# ─── Build ─────────────────────────────────────────────────────────────────────────────────────────────────────
def build(out: Path) -> Path:
    doc = (HERE / "slides_source.html").read_text(encoding="utf-8")
    css = (HERE / "slides.css").read_text(encoding="utf-8")
    svg = (HERE / "architecture.svg").read_text(encoding="utf-8")
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S).strip()
    doc = re.sub(r"<!--(?!\s*\[).*?-->", "", doc, flags=re.S)  # source comments stay in the source
    doc = doc.replace("{{CSS}}", css).replace("{{SVG:architecture}}", svg)
    for key, val in values().items():
        doc = doc.replace("{{V:" + key + "}}", val)
    left = re.findall(r"\{\{[A-Z]+:[a-z_0-9]+\}\}", doc)
    if left:
        raise SystemExit(f"Unfilled markers: {left}")
    doc = number_footers(doc)

    with tempfile.TemporaryDirectory() as tmp:
        doc, used = embed_images(doc, Path(tmp))

    missing = check(doc)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    n_slides = len(re.findall(r"<section\b", doc))
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.2f} MB, {n_slides} slides, {len(used)} screenshots: {', '.join(used)})")
    if missing:
        print(f"Numbers in the slides that report.html does not contain: {', '.join(missing)}")
    else:
        print("Every number in the slides also appears in report.html.")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    build(ap.parse_args().out)


if __name__ == "__main__":
    main()
