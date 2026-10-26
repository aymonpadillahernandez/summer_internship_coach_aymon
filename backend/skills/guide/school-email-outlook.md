# School Email (Outlook)
> Use when recruiting mail arrives in a school Outlook / Microsoft 365 account, which the app cannot read directly.

Why: school Microsoft 365 accounts do not let outside apps read mail without the school's approval (see docs/research/channels.md). Two free routes:

**Route A: automatic (recommended on a Mac)**
1. Forward school mail to a personal Gmail once: Outlook → Settings → Mail → Forwarding.
2. Connect that Gmail with the Coach Connector (skill `gmail`).
3. Check with `python3 ~/coach_connector.py run --dry-run`: it shows what would be shared and sends nothing.
4. If the Forwarding option is not available in their Outlook, use Route B.

**Route B: one email at a time**
1. Outlook: open the email → … → Save as (or drag it to the desktop) to get a .eml file.
2. Setup tab → "Any email (Gmail, Outlook, school mail)" card → upload the .eml.
3. Or copy the email's text and paste it on Today.

What happens to an uploaded .eml: the app keeps the sender's name (not the address), the date, the subject and the readable body; hidden HTML is removed before any agent reads it, and email addresses are never stored.

Do not:
- ask for the school password or any Microsoft sign-in;
- suggest third-party forwarding services (paid, and not used by the app).
