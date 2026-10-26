# Setup Order
> Use first with a new student to decide which channels to connect, in what order, and which ones need an export each time.

Follow `next_setup_step()`; its order is:
1. **Profile** (Profile, top right): target roles, industries, locations, timing.
2. **At least 3 targets:** paste a target list or a posting on Today. The filters keep only items matching the student's organisations and people, so an empty account keeps almost nothing.
3. **Connector key** on the Setup tab.
4. **Gmail** (skill `gmail`; school Outlook forwarded to it: skill `school-email-outlook`).
5. **Messages** (skill `messages-imessage`), then **WhatsApp** (skill `whatsapp`).
6. **LinkedIn** (skill `linkedin`): request the archive early, it arrives by email.
7. **Auto-sync:** `python3 ~/coach_connector.py schedule`.

**Updates on its own** (Mac, one-time Coach Connector setup): Gmail, school email via Gmail, iMessage / SMS, WhatsApp Desktop. Order: key → `setup` → Full Disk Access → `run --dry-run` → `run` → `schedule`.

**Export or paste each time:** LinkedIn, calendar invites (.ics), Slack and Android texts (copy and paste), WhatsApp without a Mac (Export chat), job postings.

**No Mac:** skip the connector; use the upload cards on Setup and paste on Today.

Rules:
- One step at a time; confirm it worked (Setup tab status, new cards on Opportunities or Networking).
- Passwords, app passwords and connector keys go only into Terminal setup prompts, never into the chat.
- The app never sends anything from their accounts.
- Failures: skill `connector-troubleshooting`.
