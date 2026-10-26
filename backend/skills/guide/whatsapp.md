# WhatsApp
> Use when a student wants WhatsApp chats in the app, through WhatsApp Desktop on a Mac or WhatsApp's own Export chat.

Say it honestly first: the connector reads WhatsApp Desktop's own data on the Mac, read-only, and never connects to WhatsApp. It is not a WhatsApp feature; Export chat is WhatsApp's official route.

**On a Mac (updates on its own)**
1. Install WhatsApp Desktop (whatsapp.com/download), link the phone, keep it open in the background.
2. Run `python3 ~/coach_connector.py setup` (again if WhatsApp was installed later). It asks "Connect WhatsApp Desktop on this Mac? [Y/n]" only when WhatsApp Desktop is found.
3. Full Disk Access for Terminal: System Settings → Privacy & Security → Full Disk Access → turn on Terminal, quit and reopen it.
4. `python3 ~/coach_connector.py whatsapp --dry-run`, then `python3 ~/coach_connector.py run`; auto-sync with `python3 ~/coach_connector.py schedule`.

Same filter as Messages: numbers masked, groups over 8 members skipped.

**Without a Mac (Export chat, each time)**
- iPhone: open the chat → tap the name at the top → Export chat → Without media → Save to Files.
- Android: open the chat → ⋮ → More → Export chat → Without media.
- Setup tab → "WhatsApp without a Mac" card → upload the .zip (or .txt). One chat at a time, recruiting chats only.

Errors: "WhatsApp Desktop is not on this Mac" → install, link, setup again, or Export chat. "stores chats differently" → Export chat for now.
