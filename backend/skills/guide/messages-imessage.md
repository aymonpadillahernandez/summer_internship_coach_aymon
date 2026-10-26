# Messages (iMessage / SMS)
> Use when a student wants iMessage or SMS threads on their Mac read by the Coach Connector, or uploaded without it.

**Automatic, on a Mac**
1. In `python3 ~/coach_connector.py setup`, answer Y to "Connect Messages (iMessage / SMS) on this Mac? [Y/n]".
2. System Settings → Privacy & Security → Full Disk Access → turn on Terminal, then quit and reopen Terminal.
3. `python3 ~/coach_connector.py messages --dry-run` (sends nothing), then `python3 ~/coach_connector.py run`.
4. Auto-sync: `python3 ~/coach_connector.py schedule`. macOS asks once more for Full Disk Access, this time for Python; the command prints the exact path and opens the settings page. That grant covers that Python for every script; if the student declines, Messages can still be synced by hand with `run`.

iPhone texts are included when they sync to the Mac's Messages app.

What is sent (filtered on the Mac): only chats with one of the student's people, a target organisation together with a recruiting word or an introduction, or a clear recruiting phrase. Phone numbers are masked, groups of more than 8 members are skipped, and new messages go with up to 10 earlier ones as context. The database `~/Library/Messages/chat.db` is opened read-only.

**Without the connector**
- Short threads: select the messages, copy, paste on Today.
- Long threads: Messages → select the conversation → File → Print → PDF → Save as PDF → upload on Setup ("iMessage / SMS without the connector", .pdf or .txt).
