# Coach Connector Troubleshooting
> Use when a Coach Connector command fails, or the Setup tab shows Check, Not yet or an auto-sync warning.

Match the message to its fix:
- **"can't be read: this needs Full Disk Access … turn on Terminal"** (run by hand): System Settings → Privacy & Security → Full Disk Access → turn on Terminal, quit and reopen it.
- **Same message naming Python and a path** (auto-sync): Full Disk Access → + → Cmd+Shift+G → paste the path printed by `python3 ~/coach_connector.py schedule` → Open → turn it on, rerun `schedule`. It covers that Python for every script; skipping is fine: Gmail still auto-syncs, and `run` syncs Messages and WhatsApp by hand.
- **"Gmail refused the sign-in"** or **"No Gmail app password saved"**: check the address and 2-Step Verification, create a new app password, rerun `python3 ~/coach_connector.py setup`.
- **"WhatsApp Desktop is not on this Mac"**: install it, link the phone, rerun setup; or Export chat.
- **"Could not reach the coach … may be waking up"**: the free server is starting; retry in a minute.
- **"Unknown or revoked connector key"**, **"Not set up yet"** or **"does not look like a connector key"**: create a key on the Setup tab, rerun setup.
- **"Too many connector requests"**: wait a few minutes.
- **"Auto-sync hasn't checked since …"**: Mac asleep or off: `python3 ~/coach_connector.py status` (0 = fine; log `~/.coach_connector/sync.log`).
- **Stop auto-sync:** `python3 ~/coach_connector.py unschedule`.
