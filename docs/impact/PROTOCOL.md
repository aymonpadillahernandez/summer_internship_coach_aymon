# Before / after test protocol

A real MBA student does the same three recruiting chores twice with the same real material: first the way they
do them today, then in Summer Internship Coach. Time is measured with `timer.html` (in this folder), and quality
is judged by the tester against their own work. The numbers in the report's Impact section come only from these
sessions. Nothing is estimated unless it is labelled as an estimate.

## Who and when

- One tester per session, about 60 minutes in one sitting. The "before" tasks always come first.
- The tester uses their own account on the live app, with their real material. A tester who is also the builder
  is reported as such. If they already use a tracker of their own, that tracker counts as their "before" tools.

## Material (gather first, not timed)

1. **Six real recruiting items from the last two weeks**, each saved as plain text: 2 emails (recruiter, alumni or
   contact), 2 chat threads (WhatsApp, text or Slack: an introduction, a call being set up, a follow-up) and 2
   postings (a careers page or a posting someone sent).
2. **Your next networking call** (or the most recent one), plus whatever you would normally use to prepare.
3. **Optional:** your LinkedIn connections export (LinkedIn → Settings → Data privacy → Get a copy of your data
   → Connections). Code keeps only people at organisations you track before the AI reads it.
4. **Optional, for setup:** your current target list (up to 10 organisations and roles) as text.

## The session

| # | Task | How it is done | Timer stops when |
|---|---|---|---|
| B1 | **Capture** the 6 items | Today's way: into your tracker or `manual_capture_template.csv`, one row per opportunity or person (organisation, role, person, stage, deadline, next step, next-step date) | the last row is saved |
| B2 | **Decide the week** | Today's way, with everything you have (tracker, inbox, chats, notes): write the 3 most valuable actions for this week, each with *why now* and *first step* | the 3 actions are written |
| B3 | **Prepare the call** | Today's way: notes on who they are and your history, your goal, 5 questions, a follow-up email draft | the notes are ready to use |
| S0 | **Set up the coach** (one-off) | Create an account, write your profile, paste your target list (and the LinkedIn export, if you have it) | setup results are read |
| A1 | **Capture** the same 6 items | Paste each item into *Add what's new* | the last result is read |
| A2 | **Decide the week** | *Plan my week*, then read the plan | you have read the plan |
| A3 | **Prepare** the same call | *Ask your coach*: "Prepare my call with …" | the brief is read |

## What is recorded (in timer.html)

- **Time** for every task, with its start and stop timestamps.
- **A1 accuracy:** for each item, the fields the app got right, got wrong or missed, compared with your own B1
  rows. Also whether each Shield rejection was correct.
- **A2 value:** how many of the coach's actions you would really do this week (0–5), how many important actions it
  surfaced that your B2 list missed, and how many suggestions were wrong.
- **A3 value:** usefulness compared with your own notes (1–5), and the share of the brief you would use as it is.
- **Frequency:** new recruiting items, calls and planning sessions in a typical week. These turn the measured time
  saved per task into a weekly figure, labelled in the report as a projection.
- **Your words:** one or two sentences on what changed, and whether they may be quoted (named or anonymous).

## Privacy

- Real names, emails and messages never appear in the repo, the report or the slides. Only counts, times, ratings
  and the agreed quote do.
- Screenshots of a tester's account are not used. Token counts are taken from the Usage table, which shows no names.
- After the test, *Profile → Delete my account and data* removes everything the tester added.
