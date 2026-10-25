"""Network intelligence: turns a pasted conversation / export into people, stages and dated, quoted events;
answers the strategist's questions about relationships; and prepares calls (the call-prep expert from the
author's tracker, generalised to any student).

Tools: none that reach outside. It reads only the pasted text, the BM25-retrieved records, or one person's dossier.
It never sends anything: the follow-up email it drafts is for the student to send.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from functools import lru_cache

from pydantic_ai import Agent, NativeOutput

import config
import db
import retrieval
import safety
from agents.models import DoorPlan, NetworkIntake, SpecialistAnswer, trim
from agents.runtime import CoachRun, prompt, run_agent
from agents.scout import checked_answer

NAME = "network"
NET_STAGE = {s["key"]: s["label"] for s in db.NETWORK_STAGES}

# English, Spanish and Catalan ways of asking for call prep (from the tracker): routed in code, zero tokens.
INTENT = re.compile(
    r"\b(prep|prepare|preparing|preparation|get ready|brief(ing)?|preparar|prepárame|preparame|prepara|preparació|ayúdame con)\b"
    r".{0,60}\b(call|chat|meeting|discussion|conversation|coffee|interview|zoom|catch[- ]?up|llamada|reunión|reunion|conversación|"
    r"conversa|trucada|reunió|café|entrevista)\b|\b(call|meeting|discussion|conversation|coffee chat)\s+prep\b",
    re.I,
)


@lru_cache(maxsize=1)
def intake_agent() -> Agent:
    return Agent(config.build_model(), output_type=NativeOutput(NetworkIntake), instructions=prompt("network_intake"),
                 model_settings=config.MODEL_SETTINGS, retries=config.OUTPUT_RETRIES, defer_model_check=True)


@lru_cache(maxsize=1)
def consult_agent() -> Agent:
    return Agent(config.build_model(), output_type=NativeOutput(SpecialistAnswer), instructions=prompt("network_consult"),
                 model_settings=config.MODEL_SETTINGS, retries=config.OUTPUT_RETRIES, defer_model_check=True)


@lru_cache(maxsize=1)
def doors_agent() -> Agent:
    return Agent(config.build_model(), output_type=NativeOutput(DoorPlan), instructions=prompt("network_doors"),
                 model_settings=config.MODEL_SETTINGS, retries=config.OUTPUT_RETRIES, defer_model_check=True)


@lru_cache(maxsize=1)
def call_prep_agent() -> Agent:
    return Agent(config.build_model(), output_type=str, instructions=prompt("call_prep"),
                 model_settings=config.MODEL_SETTINGS, retries=config.OUTPUT_RETRIES, defer_model_check=True)


def _profile(user_id: int) -> str:
    return db.get_profile(user_id)[:1200] or "(no profile yet)"


async def intake(run: CoachRun, user_id: int, text: str, label: str) -> NetworkIntake | None:
    apps = [f"{a['id']} · {a['company']} · {a['role']}" for a in db.list_applications(user_id)]
    people = [f"{c['id']} · {c['name']} · {c['affiliation']} · {NET_STAGE.get(c['status'], c['status'])}"
              for c in db.list_contacts(user_id)]
    user_prompt = (f"Today is {date.today():%A %Y-%m-%d}.\n\nStudent profile:\n{_profile(user_id)}\n\n"
                   "Opportunities:\n" + ("\n".join(apps) or "(none yet)") + "\n\nCurrent contacts:\n"
                   + ("\n".join(people) or "(none yet)") + "\n\n" + safety.wrap_untrusted(text, label))
    run.step(NAME, "reading", f"Reading “{label}” for people, stages and dated facts")
    return await run_agent(run, NAME, intake_agent(), user_prompt)


async def consult(run: CoachRun, user_id: int, question: str) -> dict:
    records = retrieval.contact_records(user_id)
    picked = retrieval.search(records, question, config.RETRIEVAL_TOP_K)
    allowed = {rid for rid, _ in picked} | {f"OPP-{a['id']}" for a in db.list_applications(user_id)}
    block = "\n".join(text for _, text in picked) or "(no contacts yet)"
    user_prompt = (f"Today is {date.today():%A %Y-%m-%d}.\nStudent profile:\n{_profile(user_id)}\n\n"
                   f"Question from the Career strategist: {question}\n\n"
                   + safety.wrap_untrusted(block, f"student records: {len(picked)} of {len(records)} contacts"))
    run.step(NAME, "searching", f"Read {len(picked)} of {len(records)} contact records (BM25)",
             records=[rid for rid, _ in picked])
    answer = await run_agent(run, NAME, consult_agent(), user_prompt, timeout=config.SPECIALIST_TIMEOUT_SECONDS)
    return checked_answer(answer, allowed)


# ─── Call prep ──────────────────────────────────────────────────────────
def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z ]", " ", s).split())


def find_person(text: str, contacts: list[dict]) -> dict | None:
    """A contact named in the text: full name first, then a first or last name that only one person has."""
    words = f" {_norm(text)} "
    full = [c for c in contacts if f" {_norm(c['name'])} " in words]
    if full:
        return max(full, key=lambda c: len(c["name"]))
    by_token: dict[str, list[dict]] = {}
    for c in contacts:
        for t in set(_norm(c["name"]).split()):
            if len(t) >= 4:
                by_token.setdefault(t, []).append(c)
    hits = {c["id"]: c for t, cs in by_token.items() if f" {t} " in words and len(cs) == 1 for c in cs}
    return next(iter(hits.values())) if len(hits) == 1 else None


def next_call(contacts: list[dict]) -> dict | None:
    now = datetime.now().strftime("%Y-%m-%d")
    booked = [c for c in contacts if c["status"] == "call_booked" and c["next_date"] and c["next_date"][:10] >= now]
    return min(booked, key=lambda c: c["next_date"]) if booked else None


def detect(user_id: int, messages: list[dict]) -> dict | None:
    """The person to prepare for, when this chat asks for call prep; otherwise None. Follow-ups stay with them."""
    contacts = [c for c in db.list_contacts(user_id) if not c.get("not_interested_at")]
    users = [m["content"] for m in messages if m["role"] == "user"]
    latest = users[-1]
    named = find_person(latest, contacts)
    if INTENT.search(latest):
        return named or next_call(contacts)
    for earlier in reversed(users[:-1]):
        if INTENT.search(earlier):
            return named or find_person(earlier, contacts) or next_call(contacts)
    return None


def dossier(user_id: int, c: dict) -> dict:
    apps = {a["id"]: a for a in db.list_applications(user_id)}
    keep = ["company", "role", "priority", "status", "deadline", "location", "context", "fit", "fit_reason"]
    orgs = [{k: apps[i][k] for k in keep if apps[i].get(k)} for i in c["application_ids"] + c["network_ids"] if i in apps]
    full = _norm(c["name"])
    introducers = []
    for o in db.list_contacts(user_id):
        if o["id"] == c["id"]:
            continue
        said = " ".join([o.get("how_met") or "", o.get("notes") or ""] + [e["text"] for e in o["events"]])
        if full and full in _norm(said):
            introducers.append({"name": o["name"], "organisation": o["affiliation"]})
    return {
        "person": {"id": f"CON-{c['id']}", "name": c["name"], "organisation": c["affiliation"],
                   "stage": NET_STAGE.get(c["status"], c["status"]), "how_met": c["how_met"],
                   "last_contact": c["last_contact"], "next_step": c["next_step"], "call_or_next_date": c["next_date"]},
        "history": [{"date": e["date"], "what": e["text"], "quote": e["evidence"]} for e in c["events"][:8]],
        "introduced_by": introducers[:3],
        "organisations_tracked": orgs[:4],
        "student_profile": _profile(user_id),
    }


async def call_prep(run: CoachRun, user_id: int, person: dict, messages: list[dict]) -> str | None:
    data = json.dumps(dossier(user_id, person), ensure_ascii=False, separators=(",", ":"))
    turns = "\n".join(f"{'Student' if m['role'] == 'user' else 'Coach'}: {m['content'][:1500]}" for m in messages[-4:])
    user_prompt = (f"Today is {date.today():%A %Y-%m-%d}.\n\n" + safety.wrap_untrusted(data, f"dossier on {person['name']}")
                   + f"\n\nConversation so far:\n{turns}")
    run.step(NAME, "preparing", f"Preparing the call with {person['name']} from their dossier (CON-{person['id']})")
    return await run_agent(run, NAME, call_prep_agent(), user_prompt)


# ─── Who can open the door ──────────────────────────────────────────────
def door_candidates(user_id: int, app: dict) -> list[tuple[str, str]]:
    """People who might be a way in (zero tokens): linked to this opportunity, naming its organisation, or the best
    BM25 matches for it. At most RETRIEVAL_TOP_K, linked people first."""
    records = dict(retrieval.contact_records(user_id))
    org = _norm(app["company"])
    linked, named = [], []
    for c in db.list_contacts(user_id):
        rid = f"CON-{c['id']}"
        if rid not in records:
            continue
        if app["id"] in c["application_ids"] or app["id"] in c["network_ids"]:
            linked.append(rid)
        elif org and org in _norm(" ".join([c["affiliation"], c["how_met"], c["notes"]] + [e["text"] for e in c["events"]])):
            named.append(rid)
    query = " ".join([app["company"], app["role"], app["location"], app.get("context") or ""])
    matched = [rid for rid, _ in retrieval.search(list(records.items()), query, config.RETRIEVAL_TOP_K)]
    order = list(dict.fromkeys(linked + named + matched))[: config.RETRIEVAL_TOP_K]
    return [(rid, records[rid]) for rid in order]


async def doors(run: CoachRun, user_id: int, app: dict) -> dict:
    opp = dict(retrieval.opportunity_records(user_id)).get(f"OPP-{app['id']}", f"[OPP-{app['id']}] {app['company']} — {app['role']}")
    people = door_candidates(user_id, app)
    run.step(NAME, "searching", f"Looked for ways into {app['company']}: {len(people)} people in your records could be connected",
             records=[rid for rid, _ in people])
    if not people:
        return {"paths": [], "next_best": "Nobody in your records is connected yet. Add a conversation or your LinkedIn export, "
                "or ask a strong contact who they know there.", "checked": 0}
    block = opp + "\n\n" + "\n".join(text for _, text in people)
    user_prompt = (f"Today is {date.today():%A %Y-%m-%d}.\nStudent profile:\n{_profile(user_id)}\n\n"
                   + safety.wrap_untrusted(block, f"opportunity {app['company']} and {len(people)} people"))
    plan = await run_agent(run, NAME, doors_agent(), user_prompt, timeout=config.SPECIALIST_TIMEOUT_SECONDS)
    if plan is None:
        return {}
    allowed = {rid for rid, _ in people}
    names = {f"CON-{c['id']}": c["name"] for c in db.list_contacts(user_id)}
    paths, dropped = [], []
    for p in plan.paths[:3]:
        if p.contact_id.strip() not in allowed:
            dropped.append(p.contact_id)
            continue
        paths.append({"contact_id": p.contact_id.strip(), "name": names[p.contact_id.strip()], "strength": p.strength,
                      "why_them": safety.scrub(trim(p.why_them, 240)), "ask": safety.scrub(trim(p.ask, 240)),
                      "first_message": safety.scrub(trim(p.first_message, 400))})
    if dropped:
        run.step(NAME, "ids_dropped", f"Removed people it was not given: {', '.join(dropped[:4])}")
    return {"paths": paths, "next_best": safety.scrub(trim(plan.next_best, 300)), "checked": len(people)}
