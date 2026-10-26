# Reading a Calendar Invite
> Use when the text is an .ics calendar invite for a call or meeting, to record who it is with and when.

An .ics file arrives as raw text. Useful lines:
- `SUMMARY:` the title (often names the person or organisation).
- `DTSTART`: `YYYYMMDDTHHMMSS` with `;TZID=<zone>` is local time in that zone; a trailing `Z` means UTC; `;VALUE=DATE:YYYYMMDD` is a date only.
- `ORGANIZER` / `ATTENDEE`: the name is in `CN=`. Ignore the `mailto:` address entirely.
- `DESCRIPTION:` and `LOCATION:` may name the topic.
- `DTSTAMP` / `CREATED`: when the invite was made.

Steps:
1. The contact is the organizer or attendee who is not the student; `name` exactly as in `CN=` (an existing contact's exact name if the same person).
2. `status` = `call_booked`; `next_date` = `YYYY-MM-DDTHH:MM` from `DTSTART` (date only if no time). Without a date it is saved as `follow_up`, so read it carefully. Time in UTC and the student's zone unknown: keep it, note "call time is in UTC" in `fields_not_found`.
3. `next_step` = "Call: <SUMMARY>"; `affiliation` only if stated.
4. `opportunity_ids`: the opportunity the title or description names; else empty.
5. Events are past facts: never record the call itself as one. Optionally one event dated from `DTSTAMP` ("A call was booked") quoting the `SUMMARY` line exactly.
6. Several attendees: one contact per relevant person.

Never output email addresses or phone numbers.
