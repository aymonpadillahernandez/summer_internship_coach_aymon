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


# ─── Career coach (internal name: strategist) ───────────────────────────
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


# ─── Network intelligence: who can open the door at one opportunity ──────
class DoorPath(BaseModel):
    contact_id: str = Field(description="the CON- id of one person in the records given")
    strength: Literal["strong", "medium", "weak"]
    why_them: str = Field(description="one sentence from the records")
    ask: str = Field(description="the realistic ask, learning first")
    first_message: str = Field(description="one or two sentences the student could send themselves")


class DoorPlan(BaseModel):
    paths: list[DoorPath] = Field(default_factory=list, description="up to 3, best first")
    next_best: str = Field("", description="if there is no strong path: how to find one")


# ─── Inbox organizer: everything one text from any channel says (replaces the two intake modes) ──
class InboxReport(BaseModel):
    opportunities: list[OpportunityFound] = Field(default_factory=list)
    leads: list[LeadFound] = Field(default_factory=list)
    contacts: list[ContactFound] = Field(default_factory=list)
    fields_not_found: list[str] = Field(default_factory=list)

    def scout_part(self) -> ScoutIntake:
        return ScoutIntake(opportunities=self.opportunities, leads=self.leads, fields_not_found=self.fields_not_found)

    def network_part(self) -> NetworkIntake:
        return NetworkIntake(contacts=self.contacts, fields_not_found=[])


# ─── Opportunity scout: what it found on public job boards / careers pages ──
class DiscoveryReport(BaseModel):
    opportunities: list[OpportunityFound] = Field(default_factory=list,
                                                  description="internships a tool returned in this run, each with its url and an exact quote")
    not_found: list[str] = Field(default_factory=list, description="organisations with no public board or no internship posting")


# ─── Opportunity scout: a shortlist found on the open web ────────────────
class WebOpportunity(BaseModel):
    company: str
    role: str
    url: str = Field(description="the page of the posting itself, as found by web search")
    quote: str = Field(description="an exact sentence from that page that shows the role (checked against the page)")
    deadline: str = Field("", description="as written on the page, '' if none")
    location: str = Field("")
    mba_eligible: YesNo = "Not clear"
    fit: Literal["strong", "possible", "weak", "unknown"] = "unknown"
    fit_reason: str = Field("", description="one sentence against the student's profile")


class WebShortlist(BaseModel):
    opportunities: list[WebOpportunity] = Field(default_factory=list)
    searched_for: list[str] = Field(default_factory=list, description="what you searched for, in a few words each")


# ─── Network intelligence: key people and alumni at one organisation ────
class Stakeholder(BaseModel):
    name: str
    title: str = Field(description="their role at the organisation, as the page states it")
    why: str = Field(description="one sentence: why this person matters for this internship")
    alum: Literal["yes", "no_info"] = Field("no_info", description="'yes' only if the page says they studied at the student's school")
    url: str = Field(description="a public page about this person (company site, news, school or conference page)")
    quote: str = Field(description="an exact sentence from that page naming the person (checked against the page)")


class StakeholderReport(BaseModel):
    people: list[Stakeholder] = Field(default_factory=list)
    next_best: str = Field("", description="if few people are found: where else to look")
