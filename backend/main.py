"""Summer Internship Coach: API + website in one service.

Local:  cd backend && .venv/bin/python -m uvicorn main:app --port 8020   (frontend dev server on :5190)
Render: see Dockerfile / render.yaml (serves the built frontend from frontend/dist on the same origin)

Every /api data route needs a signed-in user and only ever touches that user's rows. AI routes (intake, plan,
chat) check the user's and the site's daily token budget first, and return the agent trace and token usage.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import re
import time
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import auth
import checks
import config
import db
import demo
import files
import intake
import keeper
import merge
import safety
import signals
import web
from agents import guide, network, scout, strategist
from agents.models import ContactFound, NetworkIntake, OpportunityFound, ScoutIntake, trim
from urllib.parse import urlsplit as _urlsplit
from agents.runtime import CoachRun, ModelSubstituted
from store import connect, is_postgres

db.init_db()
auth.purge_old_demos()

app = FastAPI(title="Summer Internship Coach", version="1.0.0", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'",
        )
        immutable = request.url.path.startswith("/assets/")
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable" if immutable else "no-cache")
    return response


# ─── Request bodies (size limits refuse oversized input before any model call) ──
class SignupBody(BaseModel):
    email: str = Field(max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(default="", max_length=80)
    password: str = Field(max_length=200)
    code: str = Field(default="", max_length=100)


class LoginBody(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class StatusUpdate(BaseModel):
    status: str


class ContactUpdate(BaseModel):
    status: str | None = None
    last_contact: str | None = None


class ActionDone(BaseModel):
    done: bool = True


class InterestBody(BaseModel):
    not_interested: bool


class ProfileBody(BaseModel):
    text: str = Field(max_length=2000)


class IntakeBody(BaseModel):
    text: str = Field(min_length=20, max_length=config.MAX_EXPORT_CHARS)
    kind: Literal["auto", "opportunity", "conversation"] = "auto"
    label: str = Field(default="Pasted text", max_length=120)


class FileBody(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    data_b64: str = Field(min_length=4, max_length=7_000_000)  # ~5 MB file
    kind: Literal["auto", "opportunity", "conversation"] = "auto"


class KeyBody(BaseModel):
    label: str = Field(default="My computer", max_length=80)


class ConnectorIntakeBody(BaseModel):
    channel: Literal["gmail", "imessage", "whatsapp", "other"]
    text: str = Field(min_length=20, max_length=config.MAX_INPUT_CHARS)
    label: str = Field(default="", max_length=120)
    items: int = Field(default=1, ge=0, le=500)


CHECK_REASONS = {  # fixed wording: a connector reports a code, never free text that the page would show
    "full_disk_access": "Needs Full Disk Access on the Mac",
    "not_installed": "App not found on the Mac",
    "sign_in": "Gmail refused the sign-in: create a new app password",
    "server": "Could not reach the coach; the next run retries",
    "error": "Could not read this channel (see the connector's log)",
}


class ChannelCheck(BaseModel):
    ok: bool
    checked: int = Field(default=0, ge=0, le=1_000_000)
    sent: int = Field(default=0, ge=0, le=100_000)
    reason: Literal["full_disk_access", "not_installed", "sign_in", "server", "error"] | None = None


class ConnectorCheckBody(BaseModel):
    channels: dict[Literal["gmail", "imessage", "whatsapp"], ChannelCheck] = {}
    every_minutes: int | None = Field(default=None, ge=5, le=1440)  # set while auto-sync is on
    stopped: bool = False  # auto-sync was just turned off


class LinkBody(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    kind: Literal["auto", "opportunity", "conversation"] = "auto"


class Candidate(BaseModel):
    key: str = Field(max_length=200)
    title: str = Field(max_length=300)
    subtitle: str = Field(default="", max_length=300)
    due: str | None = Field(default=None, max_length=40)
    why: str = Field(default="", max_length=400)


class PlanBody(BaseModel):
    candidates: list[Candidate] = Field(min_length=1, max_length=config.MAX_CANDIDATES)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=config.MAX_CHAT_CHARS)


class GuideBody(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=40)


class DiscoverBody(BaseModel):
    companies: list[str] = Field(default_factory=list, max_length=config.MAX_DISCOVER_COMPANIES)


class PrefsBody(BaseModel):
    school: str = Field(default="", max_length=120)
    timing: str = Field(default="Summer 2027", max_length=60)
    industries: list[str] = Field(default_factory=list, max_length=15)
    roles: list[str] = Field(default_factory=list, max_length=15)
    companies: list[str] = Field(default_factory=list, max_length=40)
    cities: list[str] = Field(default_factory=list, max_length=12)
    notes: str = Field(default="", max_length=1000)


class WebSearchBody(BaseModel):
    focus: str = Field(default="", max_length=300)


class DraftDecision(BaseModel):
    status: Literal["approved", "discarded"]


class ChatBody(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=40)
    candidates: list[Candidate] = Field(default_factory=list, max_length=config.MAX_CANDIDATES)


def require_budget(user: dict) -> None:
    """Token overspending guard: the AI_PAUSED kill switch, then per student and for the whole site, per UTC day."""
    if config.AI_PAUSED:
        raise HTTPException(503, "The AI is paused on this server right now. Everything else still works.")
    used = db.tokens_today(user["id"])
    if used >= config.DAILY_TOKEN_BUDGET:
        raise HTTPException(429, f"You have used today's AI budget ({used:,} of {config.DAILY_TOKEN_BUDGET:,} tokens). "
                                 "It resets at midnight UTC; everything else still works.")
    if db.tokens_today() >= config.GLOBAL_DAILY_TOKEN_BUDGET:
        raise HTTPException(429, "The coach has reached today's site-wide AI budget. Try again tomorrow.")
    if not config.key_is_set():
        raise HTTPException(503, "The AI key is not configured on this server (PORTKEY_API_KEY).")


# ─── Health, auth ───────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    """Also touches the database: the keep-awake pings then count as activity, so a free Supabase project never
    pauses for inactivity. Always 200, so a database hiccup never makes the host restart the app."""
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        db_ok = True
    except Exception:  # noqa: BLE001 - reported, never raised
        db_ok = False
    return {"ok": True, "model": config.MODEL, "portkey_key_set": config.key_is_set(), "env_file": config.env_slot(),
            "database": "postgres" if is_postgres() else "sqlite", "db_ok": db_ok}


@app.get("/api/version")
def version():
    index = config.ROOT / "frontend" / "dist" / "index.html"
    found = re.search(r"assets/index-[^\"']+\.js", index.read_text()) if index.exists() else None
    return {"script": found.group(0) if found else ""}


@app.get("/api/auth/me")
def me(user: dict = Depends(auth.require_user)):
    return {"user": user, "signup_code_required": bool(config.SIGNUP_CODE)}


@app.get("/api/auth/options")
def auth_options():
    return {"signup_code_required": bool(config.SIGNUP_CODE)}


@app.post("/api/auth/signup")
def signup(body: SignupBody, request: Request, response: Response):
    auth.rate_limit(request, "signup", body.email)
    user, token = auth.signup(body.email, body.name, body.password, body.code)
    auth.set_session_cookie(request, response, token)
    return {"user": user}


@app.post("/api/auth/login")
def login(body: LoginBody, request: Request, response: Response):
    auth.rate_limit(request, "login", body.email)
    user, token = auth.login(body.email, body.password)
    auth.set_session_cookie(request, response, token)
    return {"user": user}


@app.post("/api/auth/demo")
def demo_login(request: Request, response: Response):
    auth.rate_limit(request, "demo")
    user, token = auth.create_demo()
    auth.set_session_cookie(request, response, token)
    return {"user": user}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    auth.logout(request.cookies.get(auth.SESSION_COOKIE))
    auth.clear_session_cookie(response)
    return {"ok": True}


@app.delete("/api/account")
def delete_account(response: Response, user: dict = Depends(auth.require_user)):
    """Delete the account and every record, run and token log that belongs to it."""
    db.delete_user_data(user["id"])
    auth.clear_session_cookie(response)
    return {"ok": True}


# ─── The student's records ──────────────────────────────────────────────
@app.get("/api/profile")
def get_profile(user: dict = Depends(auth.require_user)):
    return {"text": db.get_profile(user["id"])}


@app.put("/api/profile")
def put_profile(body: ProfileBody, user: dict = Depends(auth.require_user)):
    db.set_profile(user["id"], body.text.strip())
    return {"text": body.text.strip()}


@app.get("/api/applications")
def applications(user: dict = Depends(auth.require_user)):
    return {"stages": db.STAGES, "applications": db.board(user["id"])}


@app.get("/api/network")
def network_route(user: dict = Depends(auth.require_user)):
    return {"stages": db.NETWORK_STAGES, "contacts": db.list_contacts(user["id"]),
            "sync": {"synced_on": None, "emails_searched": None, "emails_read": None}}


@app.get("/api/leads")
def leads(user: dict = Depends(auth.require_user)):
    return {"leads": db.list_leads(user["id"])}


@app.get("/api/checks")
def data_checks(user: dict = Depends(auth.require_user)):
    return {"checks": checks.run(user["id"])}


@app.get("/api/actions/done")
def actions_done(user: dict = Depends(auth.require_user)):
    return {"done": db.done_actions(user["id"])}


@app.put("/api/actions/{key:path}")
def mark_action(key: str, body: ActionDone, user: dict = Depends(auth.require_user)):
    if not re.fullmatch(r"[a-z]+:[a-z_]+:[\w\-:.]+", key) or len(key) > 200:
        raise HTTPException(422, "Malformed action key")
    db.set_action_done(user["id"], key, body.done)
    return {"key": key, "done": body.done}


def _card(user_id: int, app_id: int) -> dict:
    row = next((a for a in db.board(user_id) if a["id"] == app_id), None)
    if row is None:
        raise HTTPException(404, "Opportunity not found")
    return row


@app.patch("/api/applications/{app_id}")
def move_application(app_id: int, body: StatusUpdate, user: dict = Depends(auth.require_user)):
    if body.status not in db.STAGE_KEYS:
        raise HTTPException(422, f"Unknown stage '{body.status}'")
    if db.update_status(user["id"], app_id, body.status) is None:
        raise HTTPException(404, "Opportunity not found")
    return _card(user["id"], app_id)


@app.put("/api/applications/{app_id}/interest")
def application_interest(app_id: int, body: InterestBody, user: dict = Depends(auth.require_user)):
    if not db.set_not_interested(user["id"], "applications", app_id, body.not_interested):
        raise HTTPException(404, "Opportunity not found")
    return _card(user["id"], app_id)


@app.patch("/api/contacts/{contact_id}")
def update_contact(contact_id: int, body: ContactUpdate, user: dict = Depends(auth.require_user)):
    if body.status is not None and body.status not in db.NETWORK_KEYS:
        raise HTTPException(422, f"Unknown networking stage '{body.status}'")
    if body.last_contact and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.last_contact):
        raise HTTPException(422, "last_contact must be YYYY-MM-DD")
    contact = db.update_contact(user["id"], contact_id, body.status, body.last_contact)
    if contact is None:
        raise HTTPException(404, "Contact not found")
    return contact


@app.put("/api/contacts/{contact_id}/interest")
def contact_interest(contact_id: int, body: InterestBody, user: dict = Depends(auth.require_user)):
    if not db.set_not_interested(user["id"], "contacts", contact_id, body.not_interested):
        raise HTTPException(404, "Contact not found")
    return db.get_contact(user["id"], contact_id)


@app.get("/api/samples")
def samples(user: dict = Depends(auth.require_user)):
    """Demo texts to paste (fictional), including two prompt-injection attacks: shown in demo accounts only, so a real
    student never pastes fictional data or attacks into their own records."""
    return {"samples": demo.samples() if user.get("is_demo") else []}


# ─── AI: intake, plan, chat ─────────────────────────────────────────────
@app.get("/api/demo-files/{name}")
def demo_file(name: str, user: dict = Depends(auth.require_user)):
    """A fictional export for one channel (WhatsApp zip, LinkedIn CSVs, .eml, .ics, a Messages thread), so anyone using
    Try the demo, graders included, can run every import without their own accounts. Demo accounts only."""
    if not user.get("is_demo"):
        raise HTTPException(403, "Sample files are for demo accounts only.")
    if name not in demo.SAMPLE_FILES:
        raise HTTPException(404, "No such sample")
    filename, data, media = demo.sample_file(name)
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/api/intake")
async def intake_route(body: IntakeBody, user: dict = Depends(auth.require_user)):
    if len(body.text) > config.MAX_INPUT_CHARS and not intake.is_linkedin_export(body.text):
        raise HTTPException(422, f"That text is too long ({len(body.text):,} characters). Paste at most "
                                 f"{config.MAX_INPUT_CHARS:,}, or upload a LinkedIn connections export.")
    require_budget(user)
    return await intake.process(user["id"], body.text, body.kind, body.label)


@app.post("/api/intake/file")
async def intake_file(body: FileBody, user: dict = Depends(auth.require_user)):
    """An uploaded file (WhatsApp export ZIP, PDF, .eml, .ics, LinkedIn CSV…) turned into text in code, then the intake."""
    try:
        text = files.extract(body.filename, base64.b64decode(body.data_b64, validate=True))
    except (binascii.Error, ValueError):
        raise HTTPException(422, "The file could not be decoded.") from None
    except files.FileError as e:
        raise HTTPException(422, str(e)) from None
    text = text.strip()
    if len(text) < 20:
        raise HTTPException(422, "That file has almost no text in it.")
    if len(text) > config.MAX_INPUT_CHARS and not intake.is_linkedin_export(text):
        raise HTTPException(422, f"That file has {len(text):,} characters of text; the limit is {config.MAX_INPUT_CHARS:,}. "
                                 "Export a shorter chat or paste the relevant part.")
    require_budget(user)
    return await intake.process(user["id"], text[: config.MAX_EXPORT_CHARS], body.kind, body.filename)


# ─── Coach Connector: a script the student runs on their own computer (Gmail, iMessage) ──
def connector_user(request: Request) -> dict:
    """The student behind a connector key (Authorization: Bearer sic_…); rate-limited per key."""
    header = request.headers.get("authorization", "")
    raw = header[7:].strip() if header.lower().startswith("bearer ") else ""
    found = db.user_for_connector_key(raw) if raw.startswith("sic_") else None
    if found is None:
        raise HTTPException(401, "Unknown or revoked connector key. Create a new one on the Setup page.")
    user, key_id = found
    if not auth._hit(f"connector:{key_id}", config.CONNECTOR_REQUESTS_PER_15_MIN, time.monotonic()):
        raise HTTPException(429, "Too many connector requests. Try again in a few minutes.")
    return auth.public(user)


@app.post("/api/connector/keys")
def create_connector_key(body: KeyBody, user: dict = Depends(auth.require_user)):
    raw, key_id = db.create_connector_key(user["id"], body.label)
    return {"id": key_id, "key": raw, "note": "Shown once. Paste it into the connector's setup; it can be revoked here."}


@app.get("/api/connector/keys")
def list_connector_keys(user: dict = Depends(auth.require_user)):
    return {"keys": db.list_connector_keys(user["id"])}


@app.delete("/api/connector/keys/{key_id}")
def revoke_connector_key(key_id: int, user: dict = Depends(auth.require_user)):
    if not db.revoke_connector_key(user["id"], key_id):
        raise HTTPException(404, "Key not found")
    return {"ok": True}


@app.get("/api/connector/status")
def connector_status(user: dict = Depends(auth.require_user)):
    return {"syncs": db.list_syncs(user["id"]), "keys": db.list_connector_keys(user["id"])}


@app.get("/api/connector/context")
def connector_context(user: dict = Depends(connector_user)):
    """The student's organisations, people and recruiting words, so the connector filters on their computer
    (and whether this is a demo account: the connector's demo mode only runs there)."""
    return {**signals.context(user["id"]), "demo": bool(user.get("is_demo"))}


@app.post("/api/connector/intake")
async def connector_intake(body: ConnectorIntakeBody, user: dict = Depends(connector_user)):
    """A batch the connector already filtered on the student's computer; same shield, agents and checks as a paste."""
    require_budget(user)
    label = body.label or {"gmail": "Gmail", "imessage": "Messages", "whatsapp": "WhatsApp"}.get(body.channel, "Connector")
    kind = "conversation" if body.channel in ("imessage", "whatsapp") else "auto"
    r = await intake.process(user["id"], body.text, kind, label)
    if r["status"] != "ok":  # paused or failed: answer non-2xx so the connector keeps these items for its next run
        raise HTTPException(503, "The coach could not read this batch right now; the connector will retry it on its next run.")
    counts = {k: (len(v) if isinstance(v, list) else v) for k, v in r["saved"].items()}
    db.record_sync(user["id"], body.channel, body.items, r["run_id"],
                   ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items() if v) or "nothing new")
    return {"status": r["status"], "run_id": r["run_id"], "saved": counts, "rejected": len(r["rejected"]),
            "shield": len(r["flagged"]) + len(r["hidden"]), "usage": r["usage"]}


@app.post("/api/connector/checked")
def connector_checked(body: ConnectorCheckBody, user: dict = Depends(connector_user)):
    """What one connector run checked, per channel: counts and a reason code only, no content, zero tokens.
    It lets the Setup page show that auto-sync is on and working (or that Messages still needs Full Disk Access)."""
    if body.stopped:
        db.stop_auto_sync(user["id"])
    for channel, c in body.channels.items():
        summary = f"{c.checked} checked, {c.sent} sent" if c.ok else CHECK_REASONS[c.reason or "error"]
        db.record_check(user["id"], channel, c.ok, c.sent, summary, body.every_minutes)
    return {"ok": True}


@app.get("/connector/coach_connector.py")
def connector_script():
    """The connector itself, so a student can download it with one command (it is also in the public repo)."""
    path = config.ROOT / "connector" / "coach_connector.py"
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/x-python; charset=utf-8")


@app.post("/api/intake/link")
async def intake_link(body: LinkBody, user: dict = Depends(auth.require_user)):
    """Read a careers page or posting from a link (web.py guardrails), then the same shield and scout as a paste."""
    require_budget(user)
    try:
        final_url, page = await asyncio.to_thread(web.fetch, body.url)
    except web.FetchError as e:
        raise HTTPException(422, str(e)) from None
    host = urlsplit(final_url).hostname or "linked page"
    return await intake.process(user["id"], page[: config.MAX_EXPORT_CHARS], body.kind, host, page_url=final_url)


@app.post("/api/applications/{app_id}/doors")
async def find_doors(app_id: int, user: dict = Depends(auth.require_user)):
    """Who can open the door at this opportunity: Network intelligence over the people your records connect to it."""
    row = db.get_application(user["id"], app_id)
    if row is None:
        raise HTTPException(404, "Opportunity not found")
    require_budget(user)
    run = CoachRun(user["id"], "doors")
    try:
        result = await network.doors(run, user["id"], row)
    except ModelSubstituted as e:
        return {**run.finish("model_rejected", str(e)), "doors": None}
    if not result:
        return {**run.finish("failed", "Network intelligence could not answer"), "doors": None}
    done = run.finish("ok", f"Doors into {row['company']}: {len(result['paths'])} path(s)")
    db.save_doors(user["id"], app_id, {**result, "run_id": run.run_id, "usage": done["usage"]})
    return {**done, "doors": result, "card": _card(user["id"], app_id)}


@app.get("/api/preferences")
def get_preferences(user: dict = Depends(auth.require_user)):
    return {"prefs": db.get_prefs(user["id"])}


@app.put("/api/preferences")
def put_preferences(body: PrefsBody, user: dict = Depends(auth.require_user)):
    """The first step of a new account: what the student wants. Feeds every agent (it opens the profile they read) and
    puts each target organisation on the board right away (code, zero tokens)."""
    clean = lambda xs, n: list(dict.fromkeys(x.strip()[:n] for x in xs if x.strip()))  # noqa: E731
    prefs = {"school": body.school.strip(), "timing": body.timing.strip(), "industries": clean(body.industries, 60),
             "roles": clean(body.roles, 60), "companies": clean(body.companies, 120), "cities": clean(body.cities, 60),
             "notes": body.notes.strip()}
    added = db.set_prefs(user["id"], prefs)
    return {"prefs": prefs, "added": added}


@app.post("/api/scout/web")
async def web_shortlist_route(body: WebSearchBody, user: dict = Depends(auth.require_user)):
    """The Opportunity scout searches the open web for internships that fit the student's profile. The Records keeper
    then reads each result's page and saves only those whose page contains the quoted sentence and the organisation."""
    require_budget(user)
    run = CoachRun(user["id"], "web")
    try:
        report = await scout.web_shortlist(run, user["id"], body.focus)
    except ModelSubstituted as e:
        return {**run.finish("model_rejected", str(e)), "saved": {}, "not_confirmed": [], "searched_for": []}
    if report is None:
        return {**run.finish("failed", "No answer"), "saved": {}, "not_confirmed": [], "searched_for": []}
    kept, not_confirmed = await keeper.verify_web(run, report.opportunities, must_contain=lambda o: [o.company])
    found = [OpportunityFound(company=o.company, role=o.role, deadline=o.deadline, location=o.location, mba_eligible=o.mba_eligible,
                              fit=o.fit, fit_reason=o.fit_reason, url=o.url, evidence=o.quote) for o, _ in kept]
    source = "\n\n".join(text for _, text in kept)
    saved = keeper.keep(run, user["id"], source, opportunities=ScoutIntake(opportunities=found), origin_opportunities="web",
                        ref=merge.source_ref(source or "web"), label="Open web", refit=True) if found else {"saved": {}, "rejected": []}
    counts = {k: (len(v) if isinstance(v, list) else v) for k, v in saved["saved"].items()}
    summary = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items() if v) or "nothing new"
    return {**run.finish("ok", f"Open-web search: {summary}"), "saved": saved["saved"],
            "not_confirmed": not_confirmed + saved["rejected"], "searched_for": report.searched_for[:6]}


@app.post("/api/applications/{app_id}/people")
async def find_people(app_id: int, user: dict = Depends(auth.require_user)):
    """Network intelligence looks on the open web for key people and alumni of the student's school at this
    organisation. Each person is saved (To contact, linked to this card) only if their public page names them."""
    row = db.get_application(user["id"], app_id)
    if row is None:
        raise HTTPException(404, "Opportunity not found")
    require_budget(user)
    run = CoachRun(user["id"], "people")
    try:
        report = await network.people(run, user["id"], row)
    except ModelSubstituted as e:
        return {**run.finish("model_rejected", str(e)), "people": [], "not_confirmed": [], "next_best": ""}
    if report is None:
        return {**run.finish("failed", "No answer"), "people": [], "not_confirmed": [], "next_best": ""}
    kept, not_confirmed = await keeper.verify_web(run, report.people, must_contain=lambda p: [p.name])
    school = "Yale alum" if "Yale" in network.school_of(user["id"]) else "alum of your school"
    contacts = [ContactFound(name=p.name, affiliation=f"{p.title} · {row['company']}"[:200], status="to_contact",
                             how_met=f"Found on {(_urlsplit(p.url).hostname or '').removeprefix('www.')}" + (f" · {school}" if p.alum == "yes" else ""),
                             next_step="Ask a mutual contact or the alumni directory for an introduction",
                             can_help_ids=[app_id]) for p, _ in kept]
    source = "\n\n".join(text for _, text in kept)
    saved = keeper.keep(run, user["id"], source, people=NetworkIntake(contacts=contacts), origin_people="web",
                        ref=merge.source_ref(source or "people"), label=f"Key people at {row['company']}") if contacts else {"saved": {}, "rejected": []}
    people = [{"name": p.name, "title": p.title, "why": safety.scrub(trim(p.why, 240)), "alum": p.alum == "yes", "url": p.url}
              for p, _ in kept]
    return {**run.finish("ok", f"Key people at {row['company']}: {len(people)} confirmed"), "people": people,
            "not_confirmed": not_confirmed + saved["rejected"], "next_best": safety.scrub(trim(report.next_best, 300)),
            "saved": saved["saved"]}


@app.get("/demo-pages/{name}")
def demo_page(name: str):
    """Fictional careers pages for the demo (one hides text aimed at AI agents), so a link can be tried live."""
    path = config.ROOT / "data" / "demo" / "pages" / name
    if not re.fullmatch(r"[a-z0-9-]+\.html", name) or not path.is_file():
        raise HTTPException(404, "Not found")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.post("/api/plan")
async def plan_route(body: PlanBody, user: dict = Depends(auth.require_user)):
    require_budget(user)
    run = CoachRun(user["id"], "plan")
    candidates = [c.model_dump() for c in body.candidates]
    try:
        plan = await strategist.plan(run, user["id"], candidates)
    except ModelSubstituted as e:
        return {**run.finish("model_rejected", str(e)), "plan": None}
    if not plan or not plan.get("top_actions"):
        return {**run.finish("failed", "The strategist could not produce a plan"), "plan": None}
    result = run.finish("ok", plan["headline"])
    db.save_plan(user["id"], run.run_id, {**plan, "usage": result["usage"], "seconds": result["seconds"], "trace": result["trace"]})
    return {**result, "plan": plan}


@app.get("/api/plan/latest")
def latest_plan(user: dict = Depends(auth.require_user)):
    return {"plan": db.latest_plan(user["id"])}


@app.post("/api/chat")
async def chat_route(body: ChatBody, user: dict = Depends(auth.require_user)):
    if body.messages[-1].role != "user":
        raise HTTPException(422, "The last message must be a question")
    require_budget(user)
    messages = [m.model_dump() for m in body.messages][-config.MAX_CHAT_TURNS:]
    run = CoachRun(user["id"], "chat")
    person = network.detect(user["id"], messages)  # call prep is routed in code (zero tokens)
    try:
        if person:
            answer = await network.call_prep(run, user["id"], person, messages)
            agent = "network"
        else:
            answer = await strategist.chat(run, user["id"], messages, [c.model_dump() for c in body.candidates])
            agent = "strategist"
    except ModelSubstituted as e:
        return {**run.finish("model_rejected", str(e)), "answer": None, "agent": None}
    if not answer:
        return {**run.finish("failed", "No answer"), "answer": None, "agent": agent}
    return {**run.finish("ok", answer.splitlines()[0][:200]), "answer": answer, "agent": agent, "model": config.MODEL,
            "person": person["name"] if person else None}


@app.post("/api/guide")
async def guide_route(body: GuideBody, user: dict = Depends(auth.require_user)):
    """The Setup guide (first step of a new account): one step at a time through every channel."""
    if body.messages[-1].role != "user":
        raise HTTPException(422, "The last message must be a question")
    require_budget(user)
    messages = [m.model_dump() for m in body.messages][-config.MAX_CHAT_TURNS:]
    run = CoachRun(user["id"], "guide")
    try:
        answer = await guide.ask(run, user["id"], messages)
    except ModelSubstituted as e:
        return {**run.finish("model_rejected", str(e)), "answer": None, "agent": "guide"}
    if not answer:
        return {**run.finish("failed", "No answer"), "answer": None, "agent": "guide"}
    return {**run.finish("ok", answer.splitlines()[0][:200]), "answer": answer, "agent": "guide", "model": config.MODEL}


@app.get("/api/setup")
def setup_status(user: dict = Depends(auth.require_user)):
    """The Setup page's checklist (code, zero tokens): what is connected and the recommended next step."""
    return {**guide.next_step(user["id"]), "status": guide.status(user["id"])}


@app.post("/api/scout/discover")
async def discover_route(body: DiscoverBody, user: dict = Depends(auth.require_user)):
    """The Opportunity scout looks for summer internships on public job boards at the student's organisations (or the
    ones given); the Records keeper checks every posting against what the tools returned before saving it."""
    require_budget(user)
    companies = [c.strip()[:80] for c in body.companies if c.strip()]
    if not companies:  # default: tracked organisations not applied to yet, most recently added first
        apps = [a for a in db.list_applications(user["id"]) if not a.get("not_interested_at")
                and a["status"] in ("not_started", "wip")]
        companies = list(dict.fromkeys(a["company"] for a in reversed(apps) if a["company"].strip()))
    companies = companies[: config.MAX_DISCOVER_COMPANIES]
    if not companies:
        raise HTTPException(422, "Add a few target organisations first (paste your target list on Today).")
    run = CoachRun(user["id"], "discover")
    try:
        report, source = await scout.discover(run, user["id"], companies)
    except ModelSubstituted as e:
        return {**run.finish("model_rejected", str(e)), "saved": {}, "rejected": [], "not_found": []}
    if report is None:
        return {**run.finish("failed", "No answer"), "saved": {}, "rejected": [], "not_found": []}
    kept = keeper.keep(run, user["id"], source, opportunities=ScoutIntake(opportunities=report.opportunities),
                       origin_opportunities="job_board", ref=merge.source_ref(source or "discover"),
                       label="Public job boards", refit=True)
    counts = {k: (len(v) if isinstance(v, list) else v) for k, v in kept["saved"].items()}
    summary = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items() if v) or "nothing new"
    return {**run.finish("ok", f"Discovery at {len(companies)} organisation(s): {summary}"), "companies": companies,
            "saved": kept["saved"], "rejected": kept["rejected"], "not_found": [trim(n, 200) for n in report.not_found[:8]]}


@app.get("/api/outbox")
def outbox(user: dict = Depends(auth.require_user)):
    """Drafts the coach wrote. The app never sends them."""
    return {"drafts": db.list_drafts(user["id"])}


@app.patch("/api/outbox/{draft_id}")
def decide_draft(draft_id: int, body: DraftDecision, user: dict = Depends(auth.require_user)):
    """Approve (the student then copies it or opens it in their own mail app) or discard. Never sends."""
    if not db.decide_draft(user["id"], draft_id, body.status):
        raise HTTPException(404, "Draft not found")
    return {"ok": True, "status": body.status}


# ─── Usage and run traces ───────────────────────────────────────────────
@app.get("/api/usage")
def usage(user: dict = Depends(auth.require_user)):
    runs = db.list_runs(user["id"])
    for r in runs:
        tot = {k: sum(a[f] for a in r["agents"]) for k, f in
               (("input", "input_tokens"), ("cached", "cached_tokens"), ("output", "output_tokens"), ("requests", "requests"),
                ("web_searches", "web_searches"))}
        r["usage"] = {**tot, "cost_usd": config.cost_usd(tot["input"], tot["cached"], tot["output"], tot["web_searches"])}
    return {"runs": runs, "today_tokens": db.tokens_today(user["id"]), "daily_budget": config.DAILY_TOKEN_BUDGET,
            "model": config.MODEL, "prices": {"input_per_m": config.PRICE_INPUT_PER_M,
                                              "cached_input_per_m": config.PRICE_CACHED_INPUT_PER_M,
                                              "output_per_m": config.PRICE_OUTPUT_PER_M, "source": config.PRICE_SOURCE}}


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str, user: dict = Depends(auth.require_user)):
    run = db.get_run(user["id"], run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_not_found(rest: str):
    raise HTTPException(404, "Not found")


# ─── Website (built frontend), same origin as the API ───────────────────
DIST = config.ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="site")
