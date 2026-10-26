# LinkedIn
> Use when a student wants LinkedIn connections or messages in the app; LinkedIn lets no app read them, so it is an export.

1. **Targets first.** Only connections at organisations the student tracks are kept, and only conversations with their people, about their targets or about recruiting. Add targets before uploading.
2. On a computer: Me → Settings & Privacy → Data privacy → Download your data.
3. Pick Connections and Messages → Request archive. It arrives by email, usually within minutes.
4. Setup tab → "LinkedIn connections and messages" card → upload `Connections.csv`, then `messages.csv` (one file per upload, .csv).

What the app does, in code, before any agent reads it:
- Connections: keeps rows whose company matches a tracked organisation (name, company, position, connected-on date only; profile URLs and email columns are dropped). Network intelligence files at most 15 people per upload as "To contact", and the Action plan shows one card to review them.
- Messages: keeps the relevant conversations, newest first; profile URLs never reach the model.

If the result says "no connections at tracked organisations" or "nothing relevant": add the missing targets or people, then upload again.

Do not:
- ask for the LinkedIn password or suggest browser extensions or scraping tools;
- read LinkedIn Jobs automatically: postings are copied and pasted (skill `job-postings`).
