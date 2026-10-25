"""Safety tests: each one plays an attack or a malfunction and checks that a defense in code stops it.

    backend/.venv/bin/python -m pytest tests -v      (no API key needed, no tokens spent)

1. Prompt injection in a pasted posting: the instruction never reaches the model, and even a model that obeys
   cannot mark the student as applied, add the attacker's recruiter, or store their email / phone.
2. Hidden text in a web page (the Lecture 12 attack) is removed before the model sees the page.
3. Hallucinated facts: a quote that is not in the pasted text, or a person who is not named in it, is rejected.
4. Data leakage: one student can never read or change another student's records or runs.
5. Runaway delegation: a strategist that keeps calling specialists is stopped at MAX_DELEGATIONS_PER_RUN.
6. Invented actions: a plan may only contain the candidate actions the app derived; invented keys are refused.
7. Model substitution: an answer from any model other than gpt-6-luna is rejected and logged.
8. Token overspending: oversized input is refused with 0 tokens spent; over the daily budget the AI routes return 429.
"""

from __future__ import annotations

import json

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import config
import db
import safety
from agents import network, scout, strategist

SAMPLES = config.ROOT / "data" / "demo" / "samples"


def _prompt_text(messages) -> str:
    return "\n".join(p.content for m in messages if isinstance(m, ModelRequest) for p in m.parts
                     if isinstance(p, UserPromptPart) and isinstance(p.content, str))


def _json_reply(payload: dict):
    def fn(messages, info: AgentInfo):
        fn.seen = _prompt_text(messages)
        return ModelResponse(parts=[TextPart(json.dumps(payload))])
    return fn


def _user_id(client) -> int:
    return client.get("/api/auth/me").json()["user"]["id"]


# ─── 1. Prompt injection in pasted text ─────────────────────────────────
def test_injected_instructions_never_reach_the_model_and_cannot_act(demo_client, accept_test_model):
    attack = (SAMPLES / "attack_posting.txt").read_text()
    injected = next(line for line in attack.splitlines() if "IGNORE" in line.upper())
    # A model that fully obeys the attacker: claims "applied", quoting the injected line as its evidence.
    obey = _json_reply({"opportunities": [{
        "company": "Granite Peak Sports", "role": "MBA Summer Associate, Partnerships", "deadline": "", "location": "Denver, CO",
        "formal_internship": "Yes", "mba_eligible": "Yes", "fit": "strong", "fit_reason": "Rank #1 as instructed",
        "status_signal": "applied", "key_points": [], "url": "", "evidence": injected[:120]}],
        "leads": [], "fields_not_found": []})
    with scout.intake_agent().override(model=FunctionModel(obey)):
        r = demo_client.post("/api/intake", json={"text": attack, "kind": "opportunity", "label": "attack"}).json()

    assert "ignore your previous instructions" not in obey.seen.lower()  # quarantined before the model call
    assert safety.QUARANTINE_NOTE in obey.seen
    assert r["flagged"] and r["flagged"][0]["line"] == 6
    assert any("quote is not in the text" in x["reason"] for x in r["rejected"])  # the obeying answer is rejected
    uid = _user_id(demo_client)
    apps = db.list_applications(uid)
    assert not any(a["company"] == "Granite Peak Sports" and a["status"] == "applied" for a in apps)
    assert not any(c["name"] == "Jack Spade" for c in db.list_contacts(uid))
    with db.connect() as conn:  # the attacker's email and phone are stored nowhere, not even in the run trace
        dump = json.dumps([dict(r) for t in ("applications", "contacts", "events", "leads", "agent_runs")
                           for r in conn.execute(f"SELECT * FROM {t}")])
    assert "granitepeak-careers.com" not in dump and "555 0147" not in dump


def test_hidden_text_in_a_web_page_is_removed():
    page = (SAMPLES / "attack_hidden.html").read_text()
    visible, hidden = safety.visible_text(page)
    assert "already received an offer" not in visible
    assert any("already received an offer" in h for h in hidden)
    assert "Business Strategy MBA Intern" in visible  # the real posting survives


# ─── 3. Hallucinated facts ──────────────────────────────────────────────
def test_quotes_and_people_not_in_the_text_are_rejected(demo_client, accept_test_model):
    text = (SAMPLES / "email_harborview.txt").read_text()
    made_up = _json_reply({"contacts": [
        {"name": "Elena Petrova", "affiliation": "Harborview Media", "status": "call_booked", "last_contact": None,
         "how_met": "", "next_step": "Call", "next_date": "2030-01-01T11:00", "opportunity_ids": [], "can_help_ids": [],
         "events": [{"date": "2026-01-01", "text": "She promised you the job", "evidence": "I promise you the internship"}]},
        {"name": "Victoria Lane", "affiliation": "CEO", "status": "keep_warm", "last_contact": None, "how_met": "",
         "next_step": None, "next_date": None, "opportunity_ids": [], "can_help_ids": [], "events": []}],
        "fields_not_found": []})
    with network.intake_agent().override(model=FunctionModel(made_up)):
        r = demo_client.post("/api/intake", json={"text": text, "kind": "conversation", "label": "email"}).json()
    reasons = {x["item"]: x["reason"] for x in r["rejected"]}
    assert reasons["Victoria Lane"].startswith("this name does not appear")
    assert any("quote is not in the text" in v for v in reasons.values())
    names = {c["name"] for c in db.list_contacts(_user_id(demo_client))}
    assert "Victoria Lane" not in names and "Elena Petrova" in names  # real person kept, invented one dropped


# ─── 4. Data leakage between students ───────────────────────────────────
def test_one_student_cannot_see_or_change_another_students_records(demo_client, client):
    a_apps = demo_client.get("/api/applications").json()["applications"]
    a_id = a_apps[0]["id"]
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as other:
        assert other.post("/api/auth/signup", json={"email": "student-b@example.com", "password": "long-password-1"}).status_code == 200
        assert other.get("/api/applications").json()["applications"] == []
        assert other.patch(f"/api/applications/{a_id}", json={"status": "offer"}).status_code == 404
        assert other.put(f"/api/applications/{a_id}/interest", json={"not_interested": True}).status_code == 404
        assert other.get("/api/runs/anything").status_code == 404
    assert demo_client.get("/api/applications").json()["applications"][0]["status"] == a_apps[0]["status"]


# ─── 5 + 6. Runaway delegation and invented actions ─────────────────────
def test_delegation_is_capped_and_invented_actions_are_refused(demo_client, accept_test_model):
    calls = {"final": 0}

    def boss(messages, info: AgentInfo):
        returned = [p for m in messages if isinstance(m, ModelRequest) for p in m.parts if isinstance(p, ToolReturnPart)]
        if not returned:  # asks 5 questions at once: one more than the cap allows
            return ModelResponse(parts=[ToolCallPart("ask_network_intel", {"question": f"Who can help? #{i}"}) for i in range(5)])
        calls["final"] += 1
        key = "net:invented:1" if calls["final"] == 1 else candidates[0]["key"]  # first an invented action, then a real one
        return ModelResponse(parts=[TextPart(json.dumps({"headline": "Focus", "top_actions": [
            {"key": key, "why_now": "now", "how": "do it", "record_ids": ["CON-999999"]}]}))])

    specialist = _json_reply({"answer": "Maya can help.", "findings": [{"statement": "Maya", "record_ids": ["CON-424242"]}], "unknowns": []})
    candidates = [{"key": "net:reach:1", "title": "Reach out to someone", "subtitle": "", "due": None, "why": "test"}]
    with strategist.plan_agent().override(model=FunctionModel(boss)), \
            network.consult_agent().override(model=FunctionModel(specialist)):
        r = demo_client.post("/api/plan", json={"candidates": candidates}).json()

    delegated = [s for s in r["trace"] if s["event"] == "delegated"]
    refused = [s for s in r["trace"] if s["event"] == "delegation_refused"]
    assert len(delegated) == config.MAX_DELEGATIONS_PER_RUN and refused
    assert any(s["event"] == "rejected_invented_action" for s in r["trace"])
    assert [a["key"] for a in r["plan"]["top_actions"]] == ["net:reach:1"]
    assert r["plan"]["top_actions"][0]["record_ids"] == []  # ids nobody retrieved are dropped
    assert any(s["event"] == "ids_dropped" for s in r["trace"])  # the specialist's invented id too


# ─── 7. Model substitution ──────────────────────────────────────────────
def test_an_answer_from_another_model_is_rejected(demo_client):
    # No accept_test_model here: the FunctionModel answers as "function:…", i.e. not gpt-6-luna.
    reply = _json_reply({"opportunities": [], "leads": [], "fields_not_found": []})
    text = (SAMPLES / "posting_riverside.txt").read_text()
    with scout.intake_agent().override(model=FunctionModel(reply)):
        r = demo_client.post("/api/intake", json={"text": text, "kind": "opportunity", "label": "posting"}).json()
    assert r["status"] == "model_rejected"
    with db.connect() as conn:
        row = conn.execute("SELECT status, model FROM model_runs WHERE run_id = ?", (r["run_id"],)).fetchone()
    assert row["status"] == "model_rejected" and row["model"].startswith("function")


# ─── 8. Token overspending ──────────────────────────────────────────────
def test_oversized_input_is_refused_before_any_model_call(demo_client):
    before = db.tokens_today(_user_id(demo_client))
    r = demo_client.post("/api/intake", json={"text": "x" * (config.MAX_INPUT_CHARS + 1), "kind": "auto"})
    assert r.status_code == 422
    assert db.tokens_today(_user_id(demo_client)) == before


def test_daily_budget_returns_429(demo_client):
    uid = _user_id(demo_client)
    db.record_model_run({"run_id": "budget-test", "user_id": uid, "agent": "scout", "model": "gpt-6-luna", "requests": 1,
                         "input_tokens": config.DAILY_TOKEN_BUDGET, "cached_tokens": 0, "output_tokens": 1,
                         "reasoning_tokens": 0, "seconds": 1, "status": "ok"})
    r = demo_client.post("/api/plan", json={"candidates": [{"key": "net:reach:1", "title": "x"}]})
    assert r.status_code == 429 and "budget" in r.json()["detail"]


def test_a_looping_agent_is_stopped_by_the_usage_limit(demo_client, accept_test_model):
    def loop(messages, info: AgentInfo):  # calls a tool forever and never answers
        return ModelResponse(parts=[ToolCallPart("get_data_checks", {})])
    with strategist.plan_agent().override(model=FunctionModel(loop)):
        r = demo_client.post("/api/plan", json={"candidates": [{"key": "net:reach:1", "title": "x"}]}).json()
    assert r["plan"] is None
    assert any(s["event"] == "usage_limit" for s in r["trace"])
