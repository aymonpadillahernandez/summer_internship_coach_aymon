# Reading a LinkedIn Export
> Use when the text is a LinkedIn Connections.csv or messages.csv from LinkedIn's Download your data.

The code has already filtered the file before you see it.

**Connections.csv** (header `First Name,Last Name,Company,Position,Connected On`)
- Only rows at organisations among the student's opportunities remain.
- One contact per row that works at one of those organisations, at most 15.
- `name` = first and last name exactly as in the row; `affiliation` = position and company from the row.
- `status` = `to_contact`; `can_help_ids` = the id of the matching opportunity; `opportunity_ids` empty.
- `how_met` = "LinkedIn connection". Connecting is not a conversation: leave `last_contact` empty and add no events unless a real exchange is shown.
- Quote the row as evidence.

**messages.csv** (blocks starting `Conversation:`, lines `[date] From → To: subject content`)
- Only conversations with the student's people, about their targets or about recruiting remain, newest first.
- Read each block like a chat (skill `read-chat`): the student is usually one side; the other person is the contact.
- `last_contact` = date of the latest message from either side in a two-way exchange; `reached_out` when only the student wrote.
- Dates come from the bracketed date; events need an exact quote from the content.
- Recruiter InMail about a role: also fill the opportunity fields when organisation and role are stated.

Never output email addresses, phone numbers or profile URLs.
