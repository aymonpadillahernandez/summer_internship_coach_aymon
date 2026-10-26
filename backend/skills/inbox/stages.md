# Stages
> Use when choosing or checking the stage of an opportunity or a person; lists every stage key exactly as the app defines it.

**Opportunity stages** (`STAGES` in db.py, in order; only move forward)
- `not_started` "Not started": tracked, nothing done yet (the default).
- `wip` "WIP": application in progress. Set by the student; the intake never sets it.
- `applied` "Applied": the text says the student applied or submitted.
- `interview` "Interview": the student was invited to or had an interview.
- `offer` "Offer": the student got an offer.
- `rejected` "Rejected": the student was not selected.

Intake sets them through `status_signal` (`none`, `applied`, `interview`, `offer`, `rejected`). The evidence quote must contain a status word (such as applied, submitted, interview, offer, regret, unfortunately, not selected) or the signal is dropped and the stage does not change.

**Network stages** (`NETWORK_STAGES`, in order; exactly one)
- `to_contact` "To contact": named as someone to approach, no exchange yet.
- `reached_out` "Reached out": the student wrote, no reply yet. Nudge 7 days after `last_contact`.
- `call_booked` "Call booked": a call or meeting agreed with a date; `next_date` required, else saved as `follow_up`.
- `follow_up` "Follow up · 2 weeks": the student owes a next move (agree a time, thanks, send something, after a call). Due at the agreed date or 14 days after `last_contact`, whichever is first.
- `keep_warm` "Keep warm": done for now; stay in touch (check-in about 60 days after the last contact).
