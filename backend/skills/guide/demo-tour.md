# Demo Tour
> Use when connection_status says demo is true, or someone asks how to try the channels without their own accounts.

The student is exploring the fictional demo (Jordan Rivera). Nothing they do reads a real account.

1. **Imports, one click each.** On the Setup tab, every channel card has **Try a sample file**: a WhatsApp chat (.zip), LinkedIn Connections.csv and messages.csv, an email (.eml), a calendar invite (.ics) and a Messages thread. Each runs the real import: the Inbox organizer reads it, the Records keeper checks every quote and saves the cards.
2. **The connector, end to end.** Setup tab step 1: create a connector key. Step 2: in Terminal, `curl -fsSL <site>/connector/coach_connector.py -o ~/coach_connector.py`, then `python3 ~/coach_connector.py setup` and paste the key (press Enter to skip Gmail, n for Messages and WhatsApp). Then `python3 ~/coach_connector.py demo`: it sends fictional Gmail, Messages and WhatsApp messages through the real connector path. The Gmail, Messages and WhatsApp cards turn to synced, and new people and opportunities appear on the boards.
3. **Then:** Today → Plan my week; Ask your coach → "Prepare my call with Maya Chen" or "Draft a thank-you note to Maya Chen" (the draft waits in the Outbox, never sent).

The demo command refuses to run with a real account's key, so fictional data never enters a real student's records.
