"""The link tool (backend/web.py): the only part of the app that reaches the internet. No real network is used:
DNS answers and web responses are scripted."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import config
import db
import web
from agents import inbox, scout

PAGE = (config.ROOT / "data" / "demo" / "pages" / "cobalt-careers.html").read_text()
FAKE_DNS = {"localhost": ["127.0.0.1"], "jobs.example.org": ["93.184.216.34"], "example.com": ["93.184.216.34"]}


@pytest.fixture
def scripted_web(monkeypatch):
    """Fake DNS plus a scripted web: the careers page, a redirect into a private address, and a bot-protected page."""
    monkeypatch.setattr(web, "resolve", lambda host: FAKE_DNS.get(host, [host]))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/careers":
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=PAGE)
        if request.url.path == "/sneaky":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:80/admin"})
        if request.url.path == "/protected":
            return httpx.Response(403)
        return httpx.Response(404)

    monkeypatch.setattr(web, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False))


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x", "http://localhost/api/health", "http://169.254.169.254/latest/meta-data/", "http://10.1.2.3/",
    "http://[::1]/", "file:///etc/passwd", "ftp://example.com/x", "http://user:pw@example.com/", "http://example.com:8080/",
])
def test_private_addresses_and_odd_links_are_never_fetched(url, scripted_web):
    with pytest.raises(web.FetchError):
        web.check_url(url)


def test_a_redirect_into_a_private_address_is_refused(scripted_web):
    with pytest.raises(web.FetchError, match="private or local"):
        web.fetch("https://jobs.example.org/sneaky")


def test_bot_protection_is_not_bypassed(scripted_web):
    with pytest.raises(web.FetchError, match="blocks automated reading"):
        web.fetch("https://jobs.example.org/protected")


def test_a_linked_page_is_read_without_its_hidden_text(demo_client, scripted_web, accept_test_model):
    seen = {}

    def model(messages, info: AgentInfo):
        seen["prompt"] = "\n".join(p.content for m in messages if isinstance(m, ModelRequest) for p in m.parts
                                   if isinstance(p, UserPromptPart) and isinstance(p.content, str))
        return ModelResponse(parts=[TextPart(json.dumps({"opportunities": [{
            "company": "Cobalt City FC", "role": "Business Strategy MBA Intern", "deadline": "November 20, 2026",
            "location": "Chicago, IL", "formal_internship": "Yes", "mba_eligible": "Yes", "posting_status": "open",
            "fit": "possible", "fit_reason": "Strategy role", "key_points": ["Applications open now"],
            "evidence": "Applications are open now."}], "leads": [], "fields_not_found": []}))])

    with inbox.agent().override(model=FunctionModel(model)):
        r = demo_client.post("/api/intake/link", json={"url": "https://jobs.example.org/careers"}).json()

    assert "already received an offer" not in seen["prompt"]  # the hidden text never reached the model
    events = {s["event"] for s in r["trace"]}
    assert {"page_fetched", "hidden_text_removed"} <= events
    uid = demo_client.get("/api/auth/me").json()["user"]["id"]
    card = next(a for a in db.list_applications(uid) if a["company"] == "Cobalt City FC")
    assert card["status"] == "not_started"  # not the "offer" the hidden text asked for
    assert card["verified_status"] == "open" and card["verified_url"] == "https://jobs.example.org/careers"
    assert card["source_url"] == "https://jobs.example.org/careers"


def test_link_errors_reach_the_student_as_plain_messages(demo_client, scripted_web):
    r = demo_client.post("/api/intake/link", json={"url": "http://localhost/api/health"})
    assert r.status_code == 422 and "private or local" in r.json()["detail"]
