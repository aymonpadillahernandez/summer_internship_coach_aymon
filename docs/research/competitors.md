# What already exists: named alternatives (official sources, read Oct 26, 2026)

Every fact below comes from the vendor's own site, help center or pricing page. Search results were used only to find
those pages. Quotes are exact text from the page. "Not described" means the pages listed did not describe it, not that
the product cannot do it. Machine-readable version, with all URLs: `competitors.json`.

## The short answer

Parts of this app already exist. Trackers (Huntr, Teal) organise jobs and contacts you type in. Simplify matches Gmail
threads to tracked jobs and finds referral paths. Dex syncs WhatsApp, email and LinkedIn into one contact list. ChatGPT
Work can read Gmail on a schedule. None of the pages read combine the three things this app does together:

- **One memory across channels, tied to opportunities:** people and dated facts from Gmail, school mail, Messages,
  WhatsApp, LinkedIn exports, Slack and postings, each linked to the internship it concerns.
- **A weekly priority plan with evidence:** ranked actions with *why now* and *first step*, every fact backed by the
  exact quote it came from, checked in code.
- **Read-only by design:** the connector opens Gmail and the Messages and WhatsApp databases read-only, and no agent
  has a sending tool. Simplify, LinkedIn, Dex (mail merge) and ChatGPT can send or act for you.

## Named alternatives

| Product | What it does (official quote) | Overlap with us | What it does not do, compared with us | Price (official) |
|---|---|---|---|---|
| **Simplify** | "Simplify proactively matches better-fit roles, customize your resume, and applies for you." | **Highest.** Gmail threads matched to tracked jobs, suggested status updates, referral paths per company | Built to act: Autopilot submits applications, Gmail integration sends from the tracker. Network comes from professional-network data or imported contacts; WhatsApp, iMessage, Slack not mentioned. No weekly plan across opportunities and people, no quote behind each record | Free core; Simplify+ $19.99/week, $39.99/month, $89.99/3 months |
| **ChatGPT** (Work, connected apps) | "Work is an agent designed for longer, multi-step work and finished deliverables." | High for a motivated student: can read Gmail, run scheduled or Gmail-triggered tasks | No recruiting data model (pipelines, stages, deadlines, eligibility) that persists between chats; no facts checked against quotes; the student designs the workflow. Its Gmail app lists the `gmail.modify` scope and Work acts after approval | Free; Go $8/mo; Plus $20/mo; Pro from $100/mo |
| **Dex** (personal CRM) | "Dex brings together LinkedIn, email, and all your daily tools." | High on relationship memory: lists WhatsApp and Messaging sync | Organised around people for any purpose. Not described: links to internships, deadlines, job-board search, weekly recruiting plan, source quotes. Professional plan has mail merge | Premium $20/mo monthly ($12 annual); Professional $34 ($20 annual); MBA students 50% off for 2 years |
| **LinkedIn Premium Career** | "Assess your fit for a job and get personalized tips to stand out" | Job-fit insights, message proofreader | Sees only LinkedIn data; no Gmail, school mail, WhatsApp or iMessage; no cross-channel pipeline or weekly plan. Is itself a sending channel (5 InMails a month). We read its data export instead | From US$39.99/month or US$239.88/year |
| **Handshake** | "get tailored profile and resume tips for a specific job" | AI job ranking, conversational search, resume help | AI uses Handshake postings, your profile, resume and what you type. No outside conversations, relationship memory or weekly plan described | No student price on the pages read |
| **12twenty** (school platform) | "Show students relevant jobs based on their preferences and activity" | School job board and events | Built for the career office: no AI coach, no reading of a student's own mail or chats described. Complementary: postings can be pasted into the coach | Not public ("Get a Demo") |
| **Teal** | "One place to organize and manage your job search" | Job tracker, contacts per job, follow-up email templates | Contacts and follow-ups entered by hand; no reading of conversations, no evidence quotes, no weekly plan described. Strong on resumes, which we do not do | Free; Teal+ $13/7 days, $29/30 days, $79/90 days |
| **Huntr** | "Huntr keeps track of every detail about your job opportunities" | Job tracker, contact tracker | Contacts stored as typed details; no cross-channel reading, quotes or weekly plan described. Strong on resumes and autofill | Free (100 jobs); Pro $40/month, $90/3 months, $160/6 months |

Also read: **Careerflow** has a Networking Tracker that imports contacts from LinkedIn, email or CSV, with reminders and
AI insights (Premium $23.99/month, Premium Plus $44.99/month). It sits with Teal and Huntr. Clay now redirects to Mesh
(me.sh).

## Hosting at organisation scale (beyond tokens)

| Item | Plan | Price | Official quote or table |
|---|---|---|---|
| Render web service | Starter (512 MB, 0.5 CPU) | $7/month | Starter, $7/month, 512 MB, 0.5 |
| Render web service | Standard (2 GB, 1 CPU) | $25/month | Standard, $25/month, 2 GB, 1 |
| Render web service | Pro (4 GB, 2 CPU) | $85/month | Pro, $85/month, 4 GB, 2 |
| Render workspace | Pro (team seats, autoscaling) | $25/month + compute | "For teams deploying production-grade apps and agents." |
| Render workspace | Hobby + Free instance (today) | $0 + compute | "Render spins down a Free web service that goes 15 minutes without receiving any inbound traffic." |
| Supabase | Pro | From $25/month | "Paid plans include $10/mo in compute credits, enough to cover one Micro instance." |
| Supabase | Free (today) | $0 | "Free projects are paused after 1 week of inactivity." |

Supabase Pro includes 100,000 monthly active users (then $0.00325 each), 8 GB disk and 250 GB egress. Arithmetic from
these prices, not a vendor quote: the smallest always-on setup is Render Starter $7 + Supabase Pro $25 = **$32/month**;
a school-wide setup is Render Pro workspace $25 + Standard $25 + Supabase Pro $25 = **$75/month**, before model tokens.
The free tiers used today sleep after 15 idle minutes (Render) and pause after a week idle (Supabase).

## Sources (read Oct 26, 2026)

- Simplify: https://simplify.jobs/ · https://simplify.jobs/networking · https://help.simplify.jobs/articles/0236686-email-integration · https://help.simplify.jobs/articles/4158996-find-referral-connections-with-simplify · https://help.simplify.jobs/articles/5623502-whats-included-in-simplify-features-and-pricing
- ChatGPT: https://chatgpt.com/pricing/ · https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex · https://help.openai.com/en/articles/10408842-google-app-data-controls-faq
- Dex: https://getdex.com/ · https://getdex.com/pricing/
- LinkedIn: https://premium.linkedin.com/careers/career
- Handshake: https://joinhandshake.com/students/ · https://support.joinhandshake.com/hc/en-us/articles/38856960612631-About-AI-powered-features-in-Handshake-for-students
- 12twenty: https://12twenty.com/ · https://12twenty.com/csh
- Teal: https://www.tealhq.com/ · https://www.tealhq.com/tools/job-tracker · https://www.tealhq.com/pricing
- Huntr: https://huntr.co/ · https://huntr.co/pricing
- Careerflow: https://www.careerflow.ai/networking-tracker · https://www.careerflow.ai/premium
- Hosting: https://render.com/pricing · https://render.com/docs/free · https://supabase.com/pricing

Method: plain HTTP reads; Teal, Handshake's help center and ChatGPT's pages refused those and were read in a normal,
visible browser (no login, no forms). openai.com/chatgpt-work/ showed an error page and was not used.
