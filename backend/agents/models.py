"""Structured outputs of the three agents. Categories are Literal enums (never free text the code must guess
at); every fact carries the exact quote it came from; record ids are checked against the student's own data in
code before anything is saved or shown.

Lengths are not enforced here: a validation failure makes the model redo its whole answer (measured: one retry added
~20 s), so text is trimmed in code instead (trim_* below). Enums and required fields stay strict."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

YesNo = Literal["Yes", "No", "Not clear"]


# ─── Opportunity scout: what a pasted posting / email / note says about opportunities ──
class OpportunityFound(BaseModel):
    match_id: int | None = Field(None, description="id of the student's existing opportunity this is about, from the list given; null if new")
    company: str = Field()
    role: str = Field()
    deadline: str = Field("", description="the deadline or opening date exactly as written, '' if not stated")
    location: str = Field("")
    formal_internship: YesNo = "Not clear"
    mba_eligible: YesNo = "Not clear"
    fit: Literal["strong", "possible", "weak", "unknown"] = "unknown"
    fit_reason: str = Field("", description="why, against the student's profile; one sentence")
    posting_status: Literal["open", "opens_later", "closed", "rolling", "no_posting_yet", "unknown"] = Field(
        "unknown", description="are applications open according to the text?")
    status_signal: Literal["none", "applied", "interview", "offer", "rejected"] = Field(
        "none", description="only if the text says the student applied, got an interview, an offer or a rejection")
    key_points: list[str] = Field(default_factory=list, description="up to 3 short things to keep in mind")
    url: str = Field("", description="a link to the posting, only if it is written in the text")
    evidence: str = Field(description="an exact quote from the text that supports this entry")


class LeadFound(BaseModel):
    kind: Literal["deadline", "event", "posting", "tip"]
    summary: str = Field()
    when: str = Field("", description="the date/time as written, '' if none")
    match_id: int | None = None
    evidence: str = Field()


class ScoutIntake(BaseModel):
    opportunities: list[OpportunityFound] = Field(default_factory=list)
    leads: list[LeadFound] = Field(default_factory=list)
    fields_not_found: list[str] = Field(default_factory=list,
                                        description="important facts the text does not state (e.g. 'deadline for X')")


# ─── Network intelligence: what a pasted conversation / export says about people ──
class EventFound(BaseModel):
    date: str = Field(description="YYYY-MM-DD when it happened (from the text); never a future date")
    text: str = Field(description="plain English, addressed to the student, e.g. 'She offered to intro you to …'")
    evidence: str = Field(description="an exact quote from the text")


class ContactFound(BaseModel):
    name: str = Field(description="the person's name exactly as written in the text")
    affiliation: str = Field("", description="role and organisation if stated")
    status: Literal["to_contact", "reached_out", "call_booked", "follow_up", "keep_warm"]
    last_contact: str | None = Field(None, description="YYYY-MM-DD of the latest real exchange with them, if any")
    how_met: str = Field("")
    next_step: str | None = Field(None)
    next_date: str | None = Field(None, description="YYYY-MM-DD or YYYY-MM-DDTHH:MM of the agreed next step / booked call")
    opportunity_ids: list[int] = Field(default_factory=list, description="ids of the student's opportunities this conversation is about")
    can_help_ids: list[int] = Field(default_factory=list, description="ids of opportunities where this person could open doors")
    events: list[EventFound] = Field(default_factory=list)


class NetworkIntake(BaseModel):
    contacts: list[ContactFound] = Field(default_factory=list)
    fields_not_found: list[str] = Field(default_factory=list)


# ─── Both specialists, when the strategist consults them ────────────────
class Finding(BaseModel):
    statement: str = Field()
    record_ids: list[str] = Field(description="ids of the records that support it, e.g. ['OPP-3', 'CON-7']")


class SpecialistAnswer(BaseModel):
    answer: str = Field()
    findings: list[Finding] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list, description="what the records do not say")


# ─── Career strategist ──────────────────────────────────────────────────
class PlannedAction(BaseModel):
    key: str = Field(description="the alias of one candidate action from the list given (A1, A2, …); never invent one")
    why_now: str = Field()
    how: str = Field(description="the concrete first step, naming the person to talk to when the records show one")
    record_ids: list[str] = Field(default_factory=list, description="OPP-/CON- ids the reasoning relies on")


class CoachPlan(BaseModel):
    headline: str = Field(description="one sentence: where to spend time this week and why")
    top_actions: list[PlannedAction] = Field(min_length=1)
    can_wait: list[str] = Field(default_factory=list, description="aliases of candidate actions that can safely wait")
    watch_outs: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


def trim(text: str | None, n: int) -> str:
    t = (text or "").strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"
