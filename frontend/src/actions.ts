import type { DataCheck } from "./api";
import type { Application, Contact, Lead } from "./types";
import { followUp, formatDate, priorityRank, stakeholders } from "./format";

/** One to-do on the action plan. Derived from the data; only "done" is stored. */
export type Action = {
  key: string;
  area: "internships" | "networking";
  kind: "apply" | "prepare" | "recheck" | "interview" | "find" | "reach" | "nudge" | "schedule" | "call" | "next" | "checkin" | "event" | "review" | "check" | "followup";
  title: string;
  subtitle: string;
  due: Date | null;
  dueLabel: string;
  why: string; // how the date was chosen, shown on hover
  app?: Application;
  apps?: Application[]; // grouped action (e.g. several targets that all need a contact)
  contact?: Contact;
  lead?: Lead;
  rank: number; // priority of the linked row, for ordering within a column
};

export type Bucket = "overdue" | "week" | "soon" | "later";
export const BUCKETS: { key: Bucket; label: string; hint: string }[] = [
  { key: "overdue", label: "Overdue", hint: "Past their date" },
  { key: "week", label: "This week", hint: "Next 7 days" },
  { key: "soon", label: "Next 2 weeks", hint: "Days 8–21" },
  { key: "later", label: "Later", hint: "Further out or no fixed date" },
];

const DAY = 86_400_000;
const startOfToday = () => {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
};
/** True when a booked call's date is before today (a date without a time counts as noon). */
export const callPassed = (nextDate: string) =>
  new Date(nextDate.length === 10 ? `${nextDate}T12:00` : nextDate) < startOfToday();
/** When to follow up: the date agreed (next_date), but never later than two weeks after the last contact. */
export function followUpDue(c: Contact): Date {
  const parse = (d: string) => new Date(d.length === 10 ? `${d}T12:00` : d);
  const dates = [c.next_date ? parse(c.next_date) : null, c.last_contact ? new Date(parse(c.last_contact).getTime() + 14 * DAY) : null];
  const known = dates.filter((d): d is Date => !!d);
  return known.length ? new Date(Math.min(...known.map((d) => d.getTime()))) : startOfToday();
}
const inDays = (n: number) => new Date(startOfToday().getTime() + n * DAY);
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const todayIso = () => iso(startOfToday());

export function bucketOf(a: Action): Bucket {
  if (!a.due) return "later";
  const days = Math.round((a.due.getTime() - startOfToday().getTime()) / DAY);
  if (days < 0) return "overdue";
  if (days <= 7) return "week";
  if (days <= 21) return "soon";
  return "later";
}

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

/** Read a date out of tracker text: "Nov. 8, 2026", "Early Dec. 2026", "Applications open Nov. 2026", "Q1 2027". */
export function dateFromText(text: string): { date: Date; exact: boolean } | null {
  const t = text.toLowerCase();
  const m = t.match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),\s*(20\d\d)/);
  if (m) return { date: new Date(+m[3], MONTHS.indexOf(m[1]), +m[2]), exact: true };
  // European order: "30 Oct 2026", "27-29 Oct 2026" (first day of a range)
  const e = t.match(/\b(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(20\d\d)/);
  if (e) return { date: new Date(+e[3], MONTHS.indexOf(e[2]), +e[1]), exact: true };
  const mm = t.match(/\b(early|mid|late)?[\s-]*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(20\d\d)/);
  if (mm) return { date: new Date(+mm[3], MONTHS.indexOf(mm[2]), mm[1] === "mid" ? 15 : mm[1] === "late" ? 25 : 1), exact: false };
  const q = t.match(/\bq([1-4])\s+(20\d\d)/);
  if (q) return { date: new Date(+q[2], (+q[1] - 1) * 3, 1), exact: false };
  return null;
}

/** No fixed date: schedule by priority so the plan has a rhythm (A+ this week, A in two weeks). */
const byPriority = (rank: number) => (rank <= 0 ? inDays(5) : rank <= 1 ? inDays(12) : rank <= 3 ? inDays(20) : null);
const planLabel = (d: Date | null) => (d ? `By ${formatDate(iso(d), true)}` : "When you can");

export function internshipActions(apps: Application[]): Action[] {
  const out: Action[] = [];
  for (const app of apps) {
    if (app.not_interested_at) continue; // set aside: no to-dos
    const rank = priorityRank(app.priority);
    const sub = `${app.role} · ${app.priority || "unrated"}`;
    if (app.status === "interview") {
      out.push({ key: `app:interview:${app.id}`, area: "internships", kind: "interview", title: `Prepare for the ${app.company} interview`, subtitle: app.role,
        due: inDays(3), dueLabel: "This week", why: "You are in the interview stage", app, rank });
      continue;
    }
    if (app.status !== "not_started" && app.status !== "wip") continue;
    // The official page, when checked, beats the tracker's own wording.
    const checked = `Official page (checked ${app.verified_on}): ${app.verified_summary ?? ""}`;
    if (app.verified_status === "closed" || app.verified_fit === "no") continue;
    if (app.verified_status === "open") {
      const parsed = dateFromText(app.verified_deadline ?? "");
      const d = parsed && parsed.date >= startOfToday() ? parsed : null;
      const due = d?.date ?? byPriority(rank) ?? inDays(14);
      const fit = app.verified_fit === "check";
      out.push({ key: `app:${fit ? "fit" : "apply"}:${app.id}:${d ? iso(d.date) : "open"}`, area: "internships", kind: fit ? "recheck" : "apply",
        title: fit ? `Decide if ${app.company} fits you` : `Apply to ${app.company}`, subtitle: fit ? app.verified_summary ?? sub : sub,
        due, dueLabel: d ? formatDate(iso(d.date), false) : "Open now", why: checked, app, rank });
      continue;
    }
    if (app.verified_status === "opens_later" && !dateFromText(app.verified_opens ?? "") && !dateFromText(app.deadline)) {
      const due = byPriority(rank) ?? inDays(21);
      out.push({ key: `app:prepare:${app.id}:soon`, area: "internships", kind: "prepare", title: `Get your ${app.company} application ready`, subtitle: sub,
        due, dueLabel: "Opens soon", why: checked, app, rank });
      continue;
    }
    // Official dates count only for a program that is open or opening, and only if still ahead
    // (a "no posting yet" page usually quotes last cycle's dates).
    const live = app.verified_status === "opens_later" || app.verified_status === "rolling"; // "open" is handled above
    const ahead = (t: string | null) => { const d = t ? dateFromText(t) : null; return !!d && d.date >= startOfToday(); };
    const fromOfficial = live ? [app.verified_deadline, app.verified_opens].find((t) => ahead(t)) ?? undefined : undefined;
    const opensOfficially = !!fromOfficial && fromOfficial === app.verified_opens;
    const text = fromOfficial ?? app.deadline;
    const found = dateFromText(text);
    const low = text.toLowerCase();
    if (found && !low.startsWith("applied") && found.date >= new Date(startOfToday().getTime() - 60 * DAY)) {
      // "open through Nov 29" is a deadline; "applications open Nov" means get ready; "typically / expected" means check.
      const estimate = /typically|expected|prior cycle|tbd/.test(low);
      const opensLater = /\bopens?\b/.test(low) && !/through|until/.test(low);
      const kind = opensOfficially ? "prepare" : low.includes("recheck") || estimate ? "recheck" : opensLater ? "prepare" : "apply";
      const title = kind === "prepare" ? `Get your ${app.company} application ready` : kind === "recheck" ? `Check ${app.company} for openings` : `Apply to ${app.company}`;
      const due = kind === "prepare" ? new Date(found.date.getTime() - 7 * DAY) : found.date;
      out.push({ key: `app:${kind}:${app.id}:${iso(found.date)}`, area: "internships", kind, title, subtitle: sub, due,
        dueLabel: kind === "prepare" ? `Opens ${formatDate(iso(found.date), false)}` : `${found.exact ? "" : "~"}${formatDate(iso(found.date), false)}`,
        why: `${fromOfficial ? checked : `From your records: "${text}"`}${kind === "prepare" ? " (a week before it opens)" : ""}`, app, rank });
    }
    const hasPerson = stakeholders(app).people.length > 0;
    if (!hasPerson && rank <= 1 && app.status === "not_started") {
      const due = byPriority(rank);
      out.push({ key: `app:find:${app.id}`, area: "internships", kind: "find", title: `Find a contact at ${app.company}`, subtitle: sub,
        due, dueLabel: planLabel(due), why: `${app.priority} target with no named contact yet`, app, rank });
    }
  }
  return groupFinds(out);
}

/** Several same-priority targets that all need a contact become one card. */
function groupFinds(actions: Action[]): Action[] {
  const finds = actions.filter((a) => a.kind === "find");
  const rest = actions.filter((a) => a.kind !== "find");
  const byRank = new Map<number, Action[]>();
  for (const f of finds) byRank.set(f.rank, [...(byRank.get(f.rank) ?? []), f]);
  for (const [rank, group] of byRank) {
    if (group.length === 1) {
      rest.push(group[0]);
      continue;
    }
    const apps = group.map((g) => g.app!).sort((a, b) => a.company.localeCompare(b.company));
    const tier = apps[0].priority;
    rest.push({
      ...group[0],
      key: `app:find:group:${apps.map((a) => a.id).join("-")}`,
      title: `Find a contact at ${apps.length} ${tier}-priority targets`,
      subtitle: apps.map((a) => a.company).join(" · "),
      app: undefined,
      apps,
      rank,
    });
  }
  return rest;
}

const REFERRAL_STEP = /Referral path, step (\d+) of/;

export function networkingActions(contacts: Contact[], apps: Map<number, Application>): Action[] {
  const out: Action[] = [];
  // People from a LinkedIn export are doors you could open, not commitments: one card to review them all.
  const found = contacts.filter((c) => c.source === "linkedin" && c.status === "to_contact" && !c.not_interested_at);
  if (found.length) {
    out.push({ key: `net:review:linkedin:${found.length}`, area: "networking", kind: "review",
      title: `Review ${found.length} LinkedIn connections at your target organisations`,
      subtitle: found.map((c) => c.name).slice(0, 4).join(" · "),
      due: inDays(10), dueLabel: planLabel(inDays(10)), why: "From your LinkedIn export, kept only at organisations you track", rank: 1 });
  }
  for (const c of contacts) {
    if (c.not_interested_at || (c.source === "linkedin" && c.status === "to_contact")) continue;
    const linked = c.application_ids.map((id) => apps.get(id)).filter((a): a is Application => !!a);
    const rank = Math.min(99, ...(linked.length ? linked : c.network_ids.map((id) => apps.get(id)).filter((a): a is Application => !!a)).map((a) => priorityRank(a.priority)));
    const about = linked.length ? linked.map((a) => a.company).slice(0, 2).join(", ") : c.affiliation;
    const base = { area: "networking" as const, contact: c, rank, app: linked[0] };

    if (c.next_step && c.status !== "call_booked" && c.status !== "follow_up") {
      const due = c.next_date ? new Date(c.next_date) : inDays(4);
      out.push({ ...base, key: `net:next:${c.id}:${c.next_step.slice(0, 24).replace(/[^\w]+/g, "-")}`, kind: "next", title: c.next_step, subtitle: `${c.name} · ${c.affiliation}`,
        due, dueLabel: c.next_date ? formatDate(c.next_date) : planLabel(due), why: "The next step recorded for this person" });
      continue;
    }
    switch (c.status) {
      case "to_contact": {
        const step = c.notes.match(REFERRAL_STEP);
        if (step && +step[1] > 1) break; // later steps of a referral path wait for the first one
        const due = byPriority(rank);
        out.push({ ...base, key: `net:reach:${c.id}`, kind: "reach", title: `Reach out to ${c.name}`, subtitle: about,
          due, dueLabel: planLabel(due), why: step ? "First step of your referral path" : "Timed by the priority of the linked role" });
        break;
      }
      case "reached_out": {
        const f = c.last_contact ? followUp(c.last_contact) : null;
        out.push({ ...base, key: `net:nudge:${c.id}:${c.last_contact ?? "undated"}`, kind: "nudge", title: `Nudge ${c.name}`, subtitle: about,
          due: f ? f.due : null, dueLabel: f ? (f.overdue ? "Now" : f.label) : "When you can",
          why: c.last_contact ? `No reply since ${formatDate(c.last_contact, false)} (7-day rule)` : "Reached out, date not recorded" });
        break;
      }
      case "follow_up": {
        // The date agreed, or two weeks after the last contact, whichever comes first.
        const due = followUpDue(c);
        const overdue = due < startOfToday();
        out.push({ ...base, key: `net:follow:${c.id}:${iso(due)}`, kind: "followup",
          title: c.next_step ?? `Follow up with ${c.name}`, subtitle: `${c.name} · ${c.affiliation}`,
          due: overdue ? startOfToday() : due, dueLabel: overdue ? `Since ${formatDate(iso(due), false)}` : formatDate(iso(due), false),
          why: c.next_date ? "The date agreed, at most two weeks after your last contact" : "Two weeks after your last contact" });
        break;
      }
      case "call_booked":
        if (c.next_date) {
          const when = new Date(c.next_date.length === 10 ? `${c.next_date}T12:00` : c.next_date);
          const past = callPassed(c.next_date);
          out.push({ ...base, key: `net:call:${c.id}:${c.next_date}`, kind: "call",
            title: past ? `Log how it went with ${c.name}` : `Meet ${c.name}`,
            subtitle: past ? `Booked for ${formatDate(c.next_date)} · move them to Follow up` : c.next_step ?? c.affiliation,
            due: past ? startOfToday() : when, dueLabel: past ? "Today" : formatDate(c.next_date),
            why: past ? "The booked date has passed and nothing records how it went" : "Booked meeting" });
        }
        break;
      case "keep_warm": {
        if (!c.last_contact) break;
        const due = new Date(new Date(`${c.last_contact}T12:00`).getTime() + 60 * DAY);
        out.push({ ...base, key: `net:checkin:${c.id}:${c.last_contact}`, kind: "checkin", title: `Check in with ${c.name}`, subtitle: about,
          due: due < startOfToday() ? inDays(21 + (c.id % 7)) : due, dueLabel: "Keep warm", why: "Last touch more than two months ago; spread over the coming weeks" });
        break;
      }
    }
  }
  return out;
}

export const sortActions = (a: Action, b: Action) =>
  (a.due?.getTime() ?? Infinity) - (b.due?.getTime() ?? Infinity) || a.rank - b.rank || a.title.localeCompare(b.title);

/** "Oct. 28", "Oct 6 at 7pm", "through November 29" with no year: the next such date after it was posted. */
function dateNoYear(text: string, posted: string): Date | null {
  const withYear = dateFromText(text);
  if (withYear) return withYear.date;
  const m = text.toLowerCase().match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b/);
  if (!m) return null;
  const from = new Date(`${posted}T00:00`); // same day as the post is not "last year"
  const d = new Date(from.getFullYear(), MONTHS.indexOf(m[1]), +m[2]);
  if (d < from) d.setFullYear(d.getFullYear() + 1);
  return d;
}

const short = (text: string) => {
  const first = text.split(/(?<=\.)\s/)[0];
  return first.length > 90 ? `${first.slice(0, 88)}…` : first;
};

/** Dated, upcoming postings and events. Ones linked to an opportunity go under Opportunities. */
export function leadActions(leads: Lead[], apps: Map<number, Application>): Action[] {
  const out: Action[] = [];
  for (const l of leads) {
    if (l.kind === "tip" || l.kind === "intro") continue;
    // A posting on a tracked row is already covered by that row's own apply action.
    if (l.kind !== "event" && l.application_ids.length) continue;
    const due = dateNoYear(l.when_text, l.date);
    if (!due || due < startOfToday()) continue;
    if (l.application_ids.length && l.application_ids.every((id) => apps.get(id)?.not_interested_at)) continue;
    const app = l.application_ids.map((id) => apps.get(id)).find(Boolean);
    const isEvent = l.kind === "event";
    out.push({
      key: `lead:${isEvent ? "event" : "apply"}:${l.id}`,
      area: app || !isEvent ? "internships" : "networking",
      kind: isEvent ? "event" : "apply",
      title: short(l.summary),
      subtitle: [l.posted_by && `Posted by ${l.posted_by}`, l.source_subject].filter(Boolean).join(" · "),
      due, dueLabel: formatDate(iso(due), false), why: `From your records: "${l.when_text}"`, app, lead: l,
      rank: app ? priorityRank(app.priority) : 50,
    });
  }
  return out;
}

// Checks already covered by the call and scheduling items above.
const COVERED = new Set(["call_passed", "step_passed"]);

/** Data checks (backend/checks.py): cards whose status no longer matches their own dates or history. */
export function checkActions(checks: DataCheck[], apps: Map<number, Application>, contacts: Contact[]): Action[] {
  const byId = new Map(contacts.map((c) => [c.id, c]));
  return checks.filter((k) => !COVERED.has(k.rule)).map((k) => {
    const app = k.area === "internships" ? apps.get(k.id) : undefined;
    return {
      key: `check:${k.rule}:${k.id}`, area: k.area, kind: "check" as const, title: `Check ${k.name}`, subtitle: `${k.problem} ${k.fix}`,
      due: startOfToday(), dueLabel: "Today", why: "Data check: the card and its own dates or history disagree",
      app, contact: k.area === "networking" ? byId.get(k.id) : undefined, rank: app ? priorityRank(app.priority) : 0,
    };
  });
}
