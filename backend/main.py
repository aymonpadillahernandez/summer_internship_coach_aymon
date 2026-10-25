"""Summer Internship Coach: API + website in one service.

Local:  cd backend && .venv/bin/python -m uvicorn main:app --port 8020   (frontend dev server on :5190)
Render: see Dockerfile / render.yaml (serves the built frontend from frontend/dist on the same origin)

Every /api data route needs a signed-in user and only ever touches that user's rows. AI routes (intake, plan,
chat) check the user's and the site's daily token budget first, and return the agent trace and token usage.
"""

from __future__ import annotations

import asyncio
import re
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import auth
import checks
import config
import db
import demo
import intake
import web
from agents import network, strategist
from agents.runtime import CoachRun, ModelSubstituted
from store import is_postgres

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


class ChatBody(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=40)
    candidates: list[Candidate] = Field(default_factory=list, max_length=config.MAX_CANDIDATES)


def require_budget(user: dict) -> None:
    """Token overspending guard: per student and for the whole site, per UTC day."""
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
    return {"ok": True, "model": config.MODEL, "portkey_key_set": config.key_is_set(), "env_file": config.env_slot(),
            "database": "postgres" if is_postgres() else "sqlite"}


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
def samples(_: dict = Depends(auth.require_user)):
    """Demo texts to paste (fictional), including two prompt-injection attacks."""
    return {"samples": demo.samples()}


# ─── AI: intake, plan, chat ─────────────────────────────────────────────
@app.post("/api/intake")
async def intake_route(body: IntakeBody, user: dict = Depends(auth.require_user)):
    if len(body.text) > config.MAX_INPUT_CHARS and not intake.is_linkedin_export(body.text):
        raise HTTPException(422, f"That text is too long ({len(body.text):,} characters). Paste at most "
                                 f"{config.MAX_INPUT_CHARS:,}, or upload a LinkedIn connections export.")
    require_budget(user)
    return await intake.process(user["id"], body.text, body.kind, body.label)


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


# ─── Usage and run traces ───────────────────────────────────────────────
@app.get("/api/usage")
def usage(user: dict = Depends(auth.require_user)):
    runs = db.list_runs(user["id"])
    for r in runs:
        tot = {k: sum(a[f] for a in r["agents"]) for k, f in
               (("input", "input_tokens"), ("cached", "cached_tokens"), ("output", "output_tokens"), ("requests", "requests"))}
        r["usage"] = {**tot, "cost_usd": config.cost_usd(tot["input"], tot["cached"], tot["output"])}
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
