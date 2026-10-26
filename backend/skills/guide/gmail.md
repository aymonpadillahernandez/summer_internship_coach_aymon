# Gmail
> Use when a student wants Gmail to sync on its own through the Coach Connector, using a Gmail app password.

1. **Connector key:** Setup tab → "Create a connector key". It starts with `sic_`, is shown once and can be revoked there.
2. **Download and set up** (Terminal: Applications → Utilities). Copy the first line from the Setup tab, which fills in the site address:
   - `curl -fsSL <site>/connector/coach_connector.py -o ~/coach_connector.py`
   - `python3 ~/coach_connector.py setup`
3. Setup asks for the coach address (Enter keeps the default), the connector key (hidden), then "Gmail address to connect".
4. **App password:** Google Account → Security → turn on 2-Step Verification → App passwords → create one called "Summer Internship Coach" (https://myaccount.google.com/apppasswords). Paste the 16-character password into setup only, never into the chat.
5. It is saved in the Mac's Keychain (without a Keychain: `~/.coach_connector/config.json`, readable only by the student).
6. **Check, then sync:**
   - `python3 ~/coach_connector.py run --dry-run` (shows what would be shared, sends nothing)
   - `python3 ~/coach_connector.py run`
7. **Auto-sync:** `python3 ~/coach_connector.py schedule` (every 30 minutes while the Mac is awake). Gmail does not need Full Disk Access.

What to tell the student: IMAP, read-only; emails stay unread; only emails matching their organisations, people or recruiting words leave the Mac. The first run looks back 30 days. Gmail only: `python3 ~/coach_connector.py gmail --since YYYY-MM-DD`.
