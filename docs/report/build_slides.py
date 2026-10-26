"""Build slides.html: one reveal.js deck (≤10 slides), every screenshot embedded, the same numbers as report.html.

The deck tells the report's story: the one-stop shop for an MBA summer-internship search, in the order a student meets
it (preferences → find → shortlist + people → stay current → act), then the agents, one real run, cost, safety, impact
and next steps.

Inputs (all in the repo):
  docs/report/slides_source.html   the slides, with {{CSS}} and {{V:name}} markers, and
                                   <img data-shot="file.png" data-width="px" [data-crop="top,bottom[,left,right]"]>
                                   for screenshots; a bare name is looked up like the report's (build_report.shot_path:
                                   2026-10-26_live, then 2026-10-26_live_web), or give "folder/file.png"
  docs/report/slides.css           styles (same palette as report.css, indigo #5e5ce6)
  docs/evidence/...                the numbers (never typed by hand): screenshots/2026-10-26_live/runs.json (morning
                                   session), screenshots/2026-10-26_live_web/runs.json (web features),
                                   runs/2026-10-26_tokenomics_live.json, runs/2026-10-26_cost_model.json (v2, web search
                                   fees included), docs/research/competitors.json (hosting prices)
  render.yaml, backend/config.py   the live daily caps: token budgets (at the output price) and web requests per day

Only reveal.js itself comes from a CDN (reveal.css + reveal.js from jsdelivr, as the brief asks); nothing else is loaded.

Checks on every build: ≤10 slides; the repo URL (and "public") on the first slide and again on the last; no external
resource other than the two CDN files; the cost model's daily worst case = token cap + web cap × most searches measured;
and every number in the slides' text also appears in report.html (a list of any that do not is printed, so the two
deliverables cannot drift apart silently).

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
WEB_SHORTLIST_RUN = "d1161ab12736"  # the web runs of the afternoon session (screenshots 23-25), as in the report
PEOPLE_RUN = "be2afd11acd4"
COACH_WEB_RUN = "692b493b6c59"
WEB_RUN_OF_KIND = {"web_shortlist": WEB_SHORTLIST_RUN, "key_people": PEOPLE_RUN, "chat_with_web": COACH_WEB_RUN}


# ─── Values from the evidence files ────────────────────────────────────────────────────────────────────────────
def values() -> dict[str, str]:
    runs = br.load(br.SHOTS / "runs.json")
    web = br.load(br.SHOTS_WEB / "runs.json")
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
        "plan_calls": str(u["requests"]), "plan_secs": f"{plan['seconds']:.1f}", "plan_cost4": f"${plan_cost:.4f}",
        "scout_in": br.n(agents["scout"]["input_tokens"]), "scout_out": br.n(agents["scout"]["output_tokens"]),
        "network_in": br.n(agents["network"]["input_tokens"]), "network_out": br.n(agents["network"]["output_tokens"]),
        "callprep_secs": f"{by_id[CALLPREP_RUN]['seconds']:.1f}", "doors_secs": f"{by_id[DOORS_RUN]['seconds']:.1f}",
        "discover_secs": f"{by_id[DISCOVER_RUN]['seconds']:.1f}",
    }
    intakes = [r["seconds"] for r in runs["runs"] if r["kind"] == "intake"]
    v["intake_min"], v["intake_max"] = f"{min(intakes):.1f}", f"{max(intakes):.1f}"

    # The web runs (screenshots 23-25): searches = (logged cost - token cost) / $0.01, as in the report's Table 2.
    wp = web["prices"]
    w_by_id = {r["run_id"]: r for r in web["runs"]}
    searches = {}
    for key, rid in (("web_short", WEB_SHORTLIST_RUN), ("people", PEOPLE_RUN), ("coach_web", COACH_WEB_RUN)):
        r = w_by_id[rid]
        searches[rid] = br.web_searches(r["usage"], wp)
        v[f"{key}_run"] = rid
        v[f"{key}_searches"] = str(searches[rid])
        v[f"{key}_secs"] = f"{r['seconds']:.1f}"
        v[f"{key}_cost"] = br.usd(r["usage"]["cost_usd"], 3)
    for kind, rid in WEB_RUN_OF_KIND.items():  # the cost model's per-request web costs are these runs
        assert abs(cost["cost_per_request_usd"][kind] - w_by_id[rid]["usage"]["cost_usd"]) < 1e-5, kind

    rows = [("Plan my week", PLAN_RUN, u, 0, f"${plan_cost:.4f}")]
    for label, rid in (("Whole-web shortlist", WEB_SHORTLIST_RUN), ("Key people and alumni", PEOPLE_RUN),
                       ("Coach answer, web", COACH_WEB_RUN)):
        wu = w_by_id[rid]["usage"]
        rows.append((label, rid, wu, searches[rid], br.usd(wu["cost_usd"], 3)))
    v["run_rows"] = "".join(
        f"<tr><td><b>{html.escape(label)}</b> <span class='rid'>{rid}</span></td><td class='num'>{br.n(x['input'])}</td>"
        f"<td class='num'>{br.n(x['cached'])}</td><td class='num'>{br.n(x['output'])}</td>"
        f"<td class='num'>{k or '–'}</td><td class='num c'>{c}</td></tr>" for label, rid, x, k, c in rows)

    # Same arithmetic and checks as the report's scale table (build_report.table_scale).
    br.table_scale(cost, research)
    per = cost["cost_per_request_usd"]
    rows = []
    for name in ("typical", "heavy"):
        mix, s = cost["requests_per_month"][name], cost["scenarios"][name]
        calc = sum(mix[k] * per[k] for k in mix)
        assert abs(calc - s["per_user_month_usd"]) < 0.0001
        web_cost = sum(mix[k] * per[k] for k in br.WEB_KINDS)
        web_n = sum(mix[k] for k in br.WEB_KINDS)
        sub = f"{s['requests']} requests, {web_n} of them web"
        rows.append(f"<tr><td><b>{name.capitalize()} student</b><span class='sub'>{html.escape(sub)}</span></td>"
                    f"<td class='num'><b class='v'>{br.usd(calc, 2)}</b></td><td class='num'>{web_cost / calc:.0%}</td>"
                    f"<td class='num'><b class='v'>{br.usd(calc * 100, 2)}</b></td>"
                    f"<td class='num'><b class='v'>{br.usd(calc * 10_000, 0)}</b></td></tr>")
        if name == "typical":
            fees = sum(mix[k] * searches[rid] * br.WEB_SEARCH_PRICE for k, rid in WEB_RUN_OF_KIND.items())
            v["typical_month"] = br.usd(calc, 2)
            v["fees_typical"] = br.usd(fees, 2)
            v["non_web_requests"] = str(s["requests"] - web_n)
            assert round((calc - web_cost) * 100) == 5, "the slide says the other requests cost about 5 cents"
            hosted = calc * 10_000 + 75  # + Render Pro workspace, Standard instance, Supabase Pro (report Table 4)
            v["typical_10k_hosted"], v["typical_10k_hosted_each"] = br.usd(hosted, 0), br.usd(hosted / 10_000, 2)
    v["scale_rows"] = "".join(rows)

    # Daily caps: the token budget (render.yaml, at the output price) + the web cap (config.py) x the most searches
    # measured in one request = the cost model's worst case per student per day.
    yaml = (br.REPO / "render.yaml").read_text(encoding="utf-8")
    budget = {k: int(x) for k, x in re.findall(r'key:\s*(\w*DAILY_TOKEN_BUDGET)\s*\n\s*value:\s*"(\d+)"', yaml)}
    token_cap = budget["DAILY_TOKEN_BUDGET"] * p["output"] / 1e6
    config = (br.REPO / "backend" / "config.py").read_text(encoding="utf-8")
    web_cap = int(re.search(r'MAX_WEB_RUNS_PER_DAY = int\(os\.getenv\("MAX_WEB_RUNS_PER_DAY", "(\d+)"\)\)', config).group(1))
    price = float(re.search(r"PRICE_WEB_SEARCH_PER_CALL = ([\d.]+)", config).group(1))
    assert price == br.WEB_SEARCH_PRICE
    worst = token_cap + web_cap * max(searches.values()) * price
    assert abs(worst - cost["worst_case_per_user_day_usd"]) < 1e-9, f"worst case {worst} != cost_model.json"
    v["day_token_cap"], v["web_cap"], v["day_worst"] = f"${token_cap:.2f}", str(web_cap), f"${worst:.2f}"
    return v


# ─── Images ────────────────────────────────────────────────────────────────────────────────────────────────────
def encode(path: Path, width: int, crop: tuple[int, ...] | None, tmp: Path) -> tuple[str, str]:
    """(mime, base64) of the screenshot: rows top..bottom (and columns left..right if given; its own pixels) if cropped,
    scaled to at most `width` px."""
    if not crop:
        return br.encode_image(path, width, None, tmp)
    w, h = br.png_size(path)
    top, bottom = crop[0], min(crop[1], h)
    left, right = (crop[2], min(crop[3], w)) if len(crop) == 4 else (0, w)
    cw = right - left
    tag = f"{top}_{bottom}_{left}_{right}"
    if not shutil.which("sips"):
        try:
            from PIL import Image  # optional
        except ImportError:
            raise SystemExit("Cropping needs macOS sips or Pillow.")
        im = Image.open(path).convert("RGB").crop((left, top, right, bottom))
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)))
        out = tmp / f"{path.stem}_{tag}.jpg"
        im.save(out, "JPEG", quality=br.JPEG_QUALITY, optimize=True)
        return "image/jpeg", base64.b64encode(out.read_bytes()).decode()
    cropped = tmp / f"crop_{tag}_{path.name}"
    # sips reads an offset of 0 as "not set" and centres the crop, so each offset is at least 1 px
    subprocess.run(["sips", "--cropToHeightWidth", str(bottom - top), str(cw), "--cropOffset", str(max(top, 1)),
                    str(max(left, 1)), str(path), "--out", str(cropped)], check=True, capture_output=True)
    out = tmp / f"{path.stem}_{tag}.jpg"
    cmd = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(br.JPEG_QUALITY)]
    if cw > width:
        cmd += ["--resampleWidth", str(width)]
    subprocess.run(cmd + [str(cropped), "--out", str(out)], check=True, capture_output=True)
    return "image/jpeg", base64.b64encode(out.read_bytes()).decode()


def embed_images(doc: str, tmp: Path) -> tuple[str, list[str]]:
    used: list[str] = []

    def repl(m: re.Match) -> str:
        tag = m.group(0)
        name = re.search(r'data-shot="([^"]+)"', tag).group(1)
        width = int(re.search(r'data-width="(\d+)"', tag).group(1))
        crop_m = re.search(r'data-crop="(\d+(?:,\d+){1,3})"', tag)
        crop = tuple(int(x) for x in crop_m.group(1).split(",")) if crop_m else None
        if crop and len(crop) not in (2, 4):
            raise SystemExit(f"data-crop needs top,bottom or top,bottom,left,right: {name}")
        path = br.shot_path(name)
        if not path.is_file():
            raise SystemExit(f"Missing screenshot: {path}")
        mime, data = encode(path, width, crop, tmp)
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
    doc = re.sub(r"<!--(?!\s*\[).*?-->", "", doc, flags=re.S)  # source comments stay in the source
    doc = doc.replace("{{CSS}}", css)
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
