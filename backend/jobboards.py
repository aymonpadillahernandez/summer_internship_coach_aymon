"""Public job-board APIs: how the Opportunity scout finds summer internships without scraping.

Companies publish their open roles through these read-only APIs precisely so that others can list them. No key and
no login are needed (Greenhouse documents that its GET endpoints need no authentication):
- Greenhouse Job Board API   GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
- Lever Postings API         GET https://api.lever.co/v0/postings/{site}?mode=json
- Ashby job posting API      GET https://api.ashbyhq.com/posting-api/job-board/{job_board_name}
- SmartRecruiters Posting API GET https://api.smartrecruiters.com/v1/companies/{companyIdentifier}/postings

Guardrails, all in code:
- requests go only to ALLOWED_HOSTS, over https, and redirects are never followed (a redirect is reported, not obeyed);
- a run has a Budget of MAX_REQUESTS_PER_RUN requests, each request has REQUEST_TIMEOUT_SECONDS in total and at most
  MAX_RESPONSE_BYTES are read (decoded bytes, so a compressed "zip bomb" is cut off too);
- board names are built by slugs() from letters, digits and hyphens only, so a company name cannot change the path;
- network errors, timeouts, 404s, oversized and invalid answers never raise: they are listed in "tried" and "error";
- posting text is what a person would see (hidden HTML text removed by safety.visible_text), email addresses and
  phone numbers are removed (safety.scrub), and every field is trimmed; links are kept only when plain http(s);
- answers are cached in memory for CACHE_SECONDS, keyed by (source, board name), so a board is not asked twice.
Everything returned is still untrusted data written by the employer: callers wrap it before any model reads it.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import httpx

import safety

ALLOWED_HOSTS = frozenset({
    "boards-api.greenhouse.io",
    "api.lever.co",
    "api.ashbyhq.com",
    "api.smartrecruiters.com",
})
MAX_REQUESTS_PER_RUN = 24
REQUEST_TIMEOUT_SECONDS = 6
MAX_RESPONSE_BYTES = 3_000_000
MAX_POSTINGS_PER_COMPANY = 10
CACHE_SECONDS = 6 * 3600

SOURCES = ("greenhouse", "lever", "ashby", "smartrecruiters")
USER_AGENT = ("SummerInternshipCoach/1.0 (reads public job-board APIs; "
              "+https://github.com/aymonpadillahernandez/summer_internship_coach_aymon)")
MAX_TEXT_CHARS = 1500
MAX_CACHE_ENTRIES = 256
_MAX_HTML_CHARS = 20_000  # per posting, before converting to text (the text is cut to 1500 characters anyway)
_MAX_POSTINGS_PARSED = 2000  # per board
# Lever's documented "commitment" filter (values are case-sensitive and OR'ed): used only when a board's full list is
# larger than MAX_RESPONSE_BYTES, so big employers still show their internships.
_LEVER_INTERN_COMMITMENTS = ("Intern", "Internship", "Summer Intern", "Summer Internship", "Co-op")


@dataclass
class Posting:
    source: str  # 'greenhouse' | 'lever' | 'ashby' | 'smartrecruiters'
    company: str
    title: str
    location: str
    url: str
    updated: str  # YYYY-MM-DD or ''
    text: str  # plain visible text, at most MAX_TEXT_CHARS
    id: str


class Budget:
    """Requests allowed in one run. take() spends one; it answers False once the cap is reached."""

    def __init__(self, limit: int = MAX_REQUESTS_PER_RUN):
        self.limit = max(0, min(int(limit), MAX_REQUESTS_PER_RUN))
        self.used = 0

    def take(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def __repr__(self) -> str:
        return f"Budget(used={self.used}, limit={self.limit})"


# ─── Board names from a company name ────────────────────────────────────
_LEADING = {"the"}
_SUFFIXES = {"inc", "incorporated", "llc", "llp", "lp", "ltd", "limited", "corp", "corporation", "co", "company",
             "plc", "gmbh", "ag", "sa", "nv", "bv", "group", "holdings", "partners", "&", "and"}


def slugs(company: str) -> list[str]:
    """At most 3 candidate board names, most likely first: 'Stripe, Inc.' -> ['stripe', 'stripeinc'];
    'The Boston Consulting Group' -> ['bostonconsulting', 'boston-consulting', 'bostonconsultinggroup']."""
    s = unicodedata.normalize("NFKD", str(company or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"['’.]", "", s)  # McDonald's -> mcdonalds, J.P. -> jp
    s = s.replace("&", " & ")
    tokens = [t for t in re.split(r"[^a-z0-9&]+", s) if t]
    while len(tokens) > 1 and tokens[0] in _LEADING:
        tokens = tokens[1:]
    full = [t for t in tokens if t != "&"]
    core = list(tokens)
    while len(core) > 1 and core[-1] in _SUFFIXES:
        core = core[:-1]
    core = [t for t in core if t != "&"]
    candidates = ["".join(core), "-".join(core), "".join(full)]
    out: list[str] = []
    for c in candidates:
        c = c.strip("-")[:60]
        if c and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", c) and c not in out:
            out.append(c)
    return out[:3]


# ─── Is it an internship? ───────────────────────────────────────────────
_INTERN_PATTERNS = [re.compile(p, re.I) for p in (
    r"\bintern(?:s|ship|ships)?\b",
    r"\bsummer\s+(?:associate|analyst)s?\b",
    r"\bmba\s+summer\b|\bsummer\s+mba\b",
    r"\bsummer\s+20\d\d\b.{0,30}?\b(?:associate|analyst)s?\b",
    r"\b(?:associate|analyst)s?\b.{0,30}?\bsummer\s+20\d\d\b",
    r"\bco-?ops?\b",
)]
# Staff roles that run internship programmes ("University Recruiter, Internships", "Internship Program Manager").
_STAFF_ROLE = re.compile(r"\b(?:recruiter|recruiting|coordinator|manager|director|lead|head)\b", re.I)
_STAFF_OBJECT = re.compile(r"\binternships\b|\b(?:intern(?:ship)?|co-?op)\s+program(?:me)?s?\b", re.I)


def _internship_score(title: str, text: str) -> int:
    """2 = the title says so, 1 = only the text does (twice, or in its first 200 characters), 0 = no."""
    title = title or ""
    if _STAFF_ROLE.search(title) and _STAFF_OBJECT.search(title):
        return 0
    if any(p.search(title) for p in _INTERN_PATTERNS):
        return 2
    starts = [m.start() for p in _INTERN_PATTERNS for m in p.finditer((text or "")[:6000])]
    return 1 if len(starts) >= 2 or any(s < 200 for s in starts) else 0


def is_internship(title: str, text: str) -> bool:
    """Intern, internship, summer associate/analyst, MBA summer, summer 20xx associate/analyst, co-op. A match in the
    title counts on its own; a match in the text counts only when repeated or at its very start."""
    return _internship_score(title, text) > 0


# ─── Small cleaners ─────────────────────────────────────────────────────
def _clean(value: Any, limit: int) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return " ".join(str(value).split())[:limit].strip()


def _text(value: str) -> str:
    t = " ".join(safety.scrub(value or "").split())
    if len(t) <= MAX_TEXT_CHARS:
        return t
    cut = t[: MAX_TEXT_CHARS - 1]
    return (cut.rsplit(" ", 1)[0] if " " in cut[-80:] else cut) + "…"


def _html_text(markup: Any, escaped: bool = False) -> str:
    """Visible text of an HTML fragment (Greenhouse sends its HTML escaped: unescape first)."""
    if not isinstance(markup, str) or not markup.strip():
        return ""
    if escaped:
        markup = html.unescape(markup)
    text, _hidden = safety.visible_text(markup[:_MAX_HTML_CHARS])
    return text


def _url(value: Any) -> str:
    u = _clean(value, 500)
    return u if re.fullmatch(r"https?://[^\s<>\"'`]+", u) else ""


def _date(value: Any) -> str:
    """YYYY-MM-DD from an ISO timestamp or from milliseconds since 1970 (Lever's createdAt); '' if neither."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        try:
            d = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return ""
        return d.date().isoformat() if 2000 <= d.year <= 2100 else ""
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2})", str(value or ""))
    if not m:
        return ""
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def _label(value: Any) -> str:
    if isinstance(value, dict):
        return _clean(value.get("label") or value.get("name"), 80)
    return _clean(value, 80)


def _facts(**pairs: str) -> str:
    """'Employment type: Intern. Team: Research.' from the structured fields the board itself returned."""
    return " ".join(f"{k.replace('_', ' ').capitalize()}: {v}." for k, v in pairs.items() if v)


def _posting(source: str, company: str, title: Any, location: Any, url: Any, updated: Any, text: str,
             pid: Any) -> Posting:
    return Posting(source=source, company=_clean(company, 120), title=_clean(title, 200),
                   location=_clean(location, 200), url=_url(url), updated=_date(updated), text=_text(text),
                   id=_clean(pid, 100))


# ─── One parser per source (field names from each API's documentation, checked against live answers) ──
def _parse_greenhouse(data: Any) -> tuple[list[Posting], str]:
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        raise ValueError("no jobs list")
    out, company = [], ""
    for j in jobs[:_MAX_POSTINGS_PARSED]:
        if not isinstance(j, dict):
            continue
        company = company or _clean(j.get("company_name"), 120)
        departments = ", ".join(_label(d) for d in (j.get("departments") or []) if isinstance(d, dict))[:120]
        text = " ".join(x for x in (_facts(department=departments), _html_text(j.get("content"), escaped=True)) if x)
        out.append(_posting("greenhouse", "", j.get("title"), (j.get("location") or {}).get("name")
                            if isinstance(j.get("location"), dict) else "", j.get("absolute_url"), j.get("updated_at"),
                            text, j.get("id")))
    return out, company


def _parse_lever(data: Any) -> tuple[list[Posting], str]:
    if not isinstance(data, list):
        raise ValueError("not a list of postings")
    out = []
    for j in data[:_MAX_POSTINGS_PARSED]:
        if not isinstance(j, dict):
            continue
        cats = j.get("categories") if isinstance(j.get("categories"), dict) else {}
        all_locations = cats.get("allLocations") if isinstance(cats.get("allLocations"), list) else []
        location = cats.get("location") or ", ".join(_clean(x, 60) for x in all_locations[:5] if _clean(x, 60))
        parts = [_facts(commitment=_clean(cats.get("commitment"), 80), team=_clean(cats.get("team"), 80)),
                 _html_text(j.get("description")) or _clean(j.get("descriptionPlain"), 6000)]
        for item in (j.get("lists") or [])[:10]:
            if isinstance(item, dict):
                parts += [_clean(item.get("text"), 200), _html_text(item.get("content"))]
        parts.append(_html_text(j.get("additional")) or _clean(j.get("additionalPlain"), 3000))
        out.append(_posting("lever", "", j.get("text"), location, j.get("hostedUrl"), j.get("createdAt"),
                            " ".join(p for p in parts if p), j.get("id")))
    return out, ""


def _parse_ashby(data: Any) -> tuple[list[Posting], str]:
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        raise ValueError("no jobs list")
    out = []
    for j in jobs[:_MAX_POSTINGS_PARSED]:
        if not isinstance(j, dict) or j.get("isListed") is False:
            continue
        facts = _facts(employment_type=_clean(j.get("employmentType"), 40), team=_clean(j.get("team"), 80))
        body = _html_text(j.get("descriptionHtml")) or _clean(j.get("descriptionPlain"), 6000)
        location = _clean(j.get("location"), 160) + (" (remote)" if j.get("isRemote") is True else "")
        out.append(_posting("ashby", "", j.get("title"), location, j.get("jobUrl"), j.get("publishedAt"),
                            " ".join(x for x in (facts, body) if x), j.get("id") or j.get("jobUrl")))
    return out, ""


def _parse_smartrecruiters(data: Any) -> tuple[list[Posting], str]:
    items = data.get("content") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("no content list")
    out, company = [], ""
    for j in items[:_MAX_POSTINGS_PARSED]:
        if not isinstance(j, dict):
            continue
        comp = j.get("company") if isinstance(j.get("company"), dict) else {}
        company = company or _clean(comp.get("name"), 120)
        loc = j.get("location") if isinstance(j.get("location"), dict) else {}
        location = loc.get("fullLocation") or ", ".join(
            _clean(loc.get(k), 60) for k in ("city", "region", "country") if loc.get(k))
        if loc.get("remote") is True:
            location = f"{location} (remote)".strip()
        # The list has no description (it is in the per-posting endpoint): the text is the structured fields.
        text = _facts(experience_level=_label(j.get("experienceLevel")), employment_type=_label(j.get("typeOfEmployment")),
                      function=_label(j.get("function")), department=_label(j.get("department")))
        # The API list has no public link; this is SmartRecruiters' public posting page for that company and id.
        ident, pid = _clean(comp.get("identifier"), 80), _clean(j.get("id"), 40)
        url = (f"https://jobs.smartrecruiters.com/{quote(ident, safe='')}/{quote(pid, safe='')}"
               if re.fullmatch(r"[\w-]+", ident) and re.fullmatch(r"[\w-]+", pid) else "")
        out.append(_posting("smartrecruiters", "", j.get("name"), location, url, j.get("releasedDate"), text,
                            j.get("id")))
    return out, company


_PARSERS = {"greenhouse": _parse_greenhouse, "lever": _parse_lever, "ashby": _parse_ashby,
            "smartrecruiters": _parse_smartrecruiters}


def _urls(source: str, slug: str) -> list[str]:
    """The request for a board, then a lighter one used only if the first answer is larger than MAX_RESPONSE_BYTES."""
    s = quote(slug, safe="-")
    if source == "greenhouse":
        base = f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs"
        return [f"{base}?content=true", base]  # without content: titles, places and links only (much smaller)
    if source == "lever":
        base = f"https://api.lever.co/v0/postings/{s}"
        return [f"{base}?mode=json",
                f"{base}?" + urlencode([("mode", "json")] + [("commitment", c) for c in _LEVER_INTERN_COMMITMENTS])]
    if source == "ashby":
        return [f"https://api.ashbyhq.com/posting-api/job-board/{s}"]
    if source == "smartrecruiters":
        return [f"https://api.smartrecruiters.com/v1/companies/{s}/postings"]
    raise ValueError(f"unknown source {source}")


# ─── HTTP: one guarded GET ──────────────────────────────────────────────
@dataclass
class _Reply:
    kind: str  # 'ok' | 'missing' (404) | 'too_big' | 'error' | 'budget'
    data: Any = None
    message: str = ""


async def _get_json(client: httpx.AsyncClient, url: str, budget: Budget) -> _Reply:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS or parts.port not in (None, 443):
        return _Reply("error", message="blocked: not one of the four job-board API hosts")
    if not budget.take():
        return _Reply("budget")
    body = bytearray()
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
            async with client.stream("GET", url, follow_redirects=False,
                                     headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                                     timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                if 300 <= resp.status_code < 400:
                    return _Reply("error", message=f"answered with a redirect (HTTP {resp.status_code}), not followed")
                if resp.status_code == 404:
                    return _Reply("missing")
                if resp.status_code != 200:
                    return _Reply("error", message=f"answered HTTP {resp.status_code}")
                declared = resp.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
                    return _Reply("too_big")
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        return _Reply("too_big")
    except (TimeoutError, httpx.TimeoutException):
        return _Reply("error", message=f"timed out after {REQUEST_TIMEOUT_SECONDS} s")
    except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError, OSError) as e:
        return _Reply("error", message=f"network error ({type(e).__name__})")
    try:
        return _Reply("ok", data=json.loads(bytes(body)))
    except (ValueError, UnicodeDecodeError, RecursionError):  # RecursionError: absurdly deep nesting ("[[[[…")
        return _Reply("error", message="answered with something that is not valid JSON")


# ─── Cache ──────────────────────────────────────────────────────────────
# (source, slug) -> (expires_at, kind, postings, company name the board reported). Only definite answers are cached
# ('ok', 'empty', 'missing', 'too_big'); timeouts and network errors are tried again next time.
_now = time.monotonic  # the cache clock (replaced in tests)
_CACHE: dict[tuple[str, str], tuple[float, str, list[Posting], str]] = {}
_BOARD_OF: dict[str, tuple[float, tuple[str, str]]] = {}  # company key -> (expires_at, (source, slug))


def clear_cache() -> None:
    _CACHE.clear()
    _BOARD_OF.clear()


def _remember(store: dict, key: Any, value: tuple) -> None:
    if len(store) >= MAX_CACHE_ENTRIES and key not in store:
        del store[min(store, key=lambda k: store[k][0])]
    store[key] = value


def _fresh(store: dict, key: Any) -> tuple | None:
    hit = store.get(key)
    if hit and hit[0] > _now():
        return hit
    store.pop(key, None)
    return None


async def _board(client: httpx.AsyncClient, source: str, slug: str, budget: Budget) -> _Reply:
    """One board: from the cache, or by asking the API (with the lighter request if the first answer is too big)."""
    hit = _fresh(_CACHE, (source, slug))
    if hit:
        return _Reply(hit[1], data=(hit[2], hit[3]))
    urls = _urls(source, slug)
    reply, used_lighter = _Reply("error"), False
    for i, url in enumerate(urls):
        reply, used_lighter = await _get_json(client, url, budget), i > 0
        if reply.kind == "too_big" and i + 1 < len(urls):
            continue
        break
    if reply.kind == "budget" and used_lighter:
        return _Reply("too_big")  # the full list was too big and no request is left for the lighter one (not cached)
    if reply.kind in ("budget", "error"):
        return reply
    postings: list[Posting] = []
    company = ""
    kind = reply.kind
    if kind == "ok":
        try:
            postings, company = await asyncio.to_thread(_PARSERS[source], reply.data)
        except Exception:  # untrusted data: any parsing failure (also html.parser's AssertionError on Python <= 3.13)
            return _Reply("error", message="answered in an unexpected format")
        # An empty board is treated as "no board here" so other sources are tried, except when the full list was too
        # big and the lighter (internships-only) request found nothing: that board exists but has no internship.
        if not postings and not used_lighter:
            kind = "empty"
    _remember(_CACHE, (source, slug), (_now() + CACHE_SECONDS, kind, postings, company))
    return _Reply(kind, data=(postings, company))


def _rank(postings: list[Posting]) -> list[Posting]:
    """Internship-like postings first (title matches before text-only matches), newest first within each group."""
    ordered = sorted(postings, key=lambda p: p.updated, reverse=True)
    ordered.sort(key=lambda p: -_internship_score(p.title, p.text))
    return ordered[:MAX_POSTINGS_PER_COMPANY]


def _company_key(company: str) -> str:
    return " ".join(company.lower().split())


# ─── The one entry point ────────────────────────────────────────────────
async def search(company: str, budget: Budget, client: httpx.AsyncClient | None = None) -> dict:
    """Find one organisation's public job board and return its postings, internship-like ones first.

    {"company", "board": "<source>:<slug>" or None, "postings": [Posting as dict], "tried": ["greenhouse:stripe", ...],
     "error": str or None}. Never raises for network problems: they become "tried" entries and the error text."""
    name = _clean(company, 120)
    result: dict[str, Any] = {"company": name, "board": None, "postings": [], "tried": [], "error": None}
    candidates = slugs(name)
    if not candidates:
        result["error"] = "No usable company name to look up."
        return result
    order = [(source, s) for s in candidates for source in SOURCES]
    known = _fresh(_BOARD_OF, _company_key(name))
    if known:  # the board found for this company last time is asked first
        order = [known[1]] + [o for o in order if o != known[1]]

    problems: list[str] = []
    out_of_budget = False
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(follow_redirects=False, timeout=REQUEST_TIMEOUT_SECONDS,
                                   headers={"User-Agent": USER_AGENT})
    try:
        for source, s in order:
            reply = await _board(client, source, s, budget)
            if reply.kind == "budget":
                out_of_budget = True
                break
            result["tried"].append(f"{source}:{s}")
            if reply.kind == "ok":
                postings, board_company = reply.data
                result["board"] = f"{source}:{s}"
                result["postings"] = [asdict(replace(p, company=board_company or name)) for p in _rank(postings)]
                _remember(_BOARD_OF, _company_key(name), (_now() + CACHE_SECONDS, (source, s)))
                return result
            if reply.kind == "too_big":
                problems.append(f"{source}:{s} answered with more than {MAX_RESPONSE_BYTES / 1_000_000:g} MB "
                                "and was skipped")
            elif reply.kind == "error":
                problems.append(f"{source}:{s} {reply.message}")
    finally:
        if own_client:
            await client.aclose()

    msg = (f"No public job board with open postings found for {name or 'this company'} "
           f"(checked {len(result['tried'])} of {len(order)} board names on Greenhouse, Lever, Ashby and SmartRecruiters).")
    if problems:
        msg += " Problems: " + "; ".join(problems[:6]) + "."
    if out_of_budget:
        msg += f" Stopped: the search budget for this run ({budget.limit} requests) is spent."
    result["error"] = msg
    return result
