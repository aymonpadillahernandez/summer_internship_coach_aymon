# Which channels can the coach connect to? (official sources, Oct 25, 2026)

Checked on the platforms' own developer docs, help pages and terms; each claim was re-read against the page it cites.
Only free routes are used in the app. "Automatic" means an app can read the channel without the student copying anything.

| Channel | Automatic? | Route in the app (Connect tab) | Official sources (first two of those checked) |
|---|---|---|---|
| LinkedIn | No | Upload Connections.csv and messages.csv from **Download your data**; messages filtered in code | https://www.linkedin.com/help/linkedin/answer/a1339364<br>https://www.linkedin.com/help/linkedin/answer/a1339364 |
| Slack | No (admin-approved apps only) | Copy and paste the DM or thread | https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps<br>https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps |
| Gmail | Yes, free | **Coach Connector**: IMAP with an app password, read-only, filtered on the student's Mac, auto-sync every 30 min. OAuth would need Google's restricted-scope review | https://developers.google.com/workspace/gmail/api/auth/scopes<br>https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification |
| Microsoft 365 | Not for school accounts | Forward school mail to a personal Gmail, then the Coach Connector; or upload .eml | https://learn.microsoft.com/en-us/graph/permissions-reference<br>https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0 |
| Email forwarding into the app | Paid services | Not used: inbound-parsing services need a paid plan or a custom domain | https://postmarkapp.com/developer/user-guide/inbound<br>https://postmarkapp.com/developer/user-guide/inbound/inbound-domain-forwarding |
| User-side auto-forwarding rules | Yes | Forward school Outlook to Gmail (used with the Coach Connector) | https://support.google.com/mail/answer/10957<br>https://support.google.com/mail/answer/10957 |
| WhatsApp | No API (terms forbid automated access) | **On a Mac:** the Coach Connector reads WhatsApp Desktop's own data read-only, with auto-sync, and never connects to WhatsApp (not a WhatsApp feature; setup asks first). **Otherwise:** upload WhatsApp's own **Export chat** .zip | https://faq.whatsapp.com/1180414079177245/?cms_platform=iphone<br>https://faq.whatsapp.com/1180414079177245/?cms_platform=iphone |
| Apple iMessage / SMS | No public API | **Coach Connector** reads the Mac's Messages database read-only (Full Disk Access), with auto-sync every 30 min; or print to PDF and upload | https://developer.apple.com/documentation/messageui/mfmessagecomposeviewcontroller<br>https://developer.apple.com/documentation/messages |
| Android SMS / Google Messages | No | Copy the thread from Google Messages for web and paste | https://support.google.com/messages/answer/6089066<br>https://support.google.com/googleplay/android-developer/answer/10208820?hl=en |
| Google Calendar API | Needs Google verification | Upload the invite's .ics instead | https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification<br>https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification |
| Microsoft Graph Calendars.Read / Calendars.ReadBasic | Not for school accounts | Upload the invite's .ics instead | https://learn.microsoft.com/en-us/graph/permissions-reference<br>https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/user-admin-consent-overview |
| .ics invite and calendar files | Yes | Upload .ics on the Connect tab | https://support.google.com/calendar/answer/37111?hl=en<br>https://support.google.com/calendar/answer/37111?hl=en |
| Greenhouse Job Board API | Yes (public API) | Possible next step for the Opportunity scout; today: paste the careers link | https://docs.greenhouse.io/job-board.html<br>https://docs.greenhouse.io/job-board.html |
| Lever Postings API | Yes (public API) | Same as Greenhouse | https://github.com/lever/postings-api/blob/master/README.md<br>https://github.com/lever/postings-api/blob/master/README.md |
| Ashby public Job Postings API | Yes (public API) | Same as Greenhouse | https://developers.ashbyhq.com/docs/public-job-posting-api<br>https://developers.ashbyhq.com/docs/public-job-posting-api |
| SmartRecruiters Posting API | Yes (public API) | Same as Greenhouse | https://developers.smartrecruiters.com/reference/v1listpostings<br>https://developers.smartrecruiters.com/reference/v1listpostings |
| LinkedIn Jobs | No (terms forbid scraping) | Copy the posting text and paste | https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access<br>https://learn.microsoft.com/en-us/linkedin/talent/job-postings/api/overview?view=li-lts-2026-04 |
| Handshake | No (terms forbid scraping) | Copy the posting text and paste | https://joinhandshake.com/legal/tos/<br>https://joinhandshake.com/legal/tos/ |
| 12twenty | No (terms forbid scraping) | Copy the posting text and paste | https://12twenty.com/terms-of-service<br>https://12twenty.com/terms-of-service |
| Symplicity CSM | No (partners only) | Copy the posting text and paste | https://www.symplicity.com/developer/csm/faq<br>https://www.symplicity.com/developer/csm/faq |
