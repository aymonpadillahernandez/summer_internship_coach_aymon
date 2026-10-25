import type { Application } from "./types";

// Spreadsheet grades, best first. Anything unknown sorts last.
const PRIORITY_RANK: Record<string, number> = {
  "A+": 0, A: 1, "A−": 2, "B+/A−": 3, "B+": 4, B: 5, "B−": 6,
};

export const priorityRank = (p: string) => PRIORITY_RANK[p] ?? 99;
/** Split grades count by their best half: "B+/A−" sits in the A tier (it also sorts just below A−). */
export const priorityTier = (p: string) =>
  p.split("/").some((g) => g.trim().startsWith("A")) ? "A" : "B";

/** CSS modifier for the priority badge: A+ → aplus, B− → bminus, B+/A− → bplus. */
export function priorityClass(p: string) {
  const base = p.split("/")[0];
  const letter = base[0]?.toLowerCase() ?? "x";
  const mod = base.includes("+") ? "plus" : base.includes("−") || base.includes("-") ? "minus" : "";
  return `p-${letter}${mod}`;
}

export const concepts = (a: Application) =>
  a.context.split("·").map((c) => c.trim()).filter(Boolean);

const NONE = /^(none mapped|$)/i;
// Entries that name a group or a maybe, not a person ("Alumni network", "Case-specific").
const NOT_A_PERSON = /\bnetwork\b|potentially relevant|case-specific/i;

/**
 * Parse the Key stakeholders text. "A → B → C" is a referral path; "A · B" and
 * "A / B" are separate entries. In "X via Y", Y is the connector and counts too.
 * `people` holds only real names, which is what gets an avatar and the stat.
 */
export function stakeholders(a: Application) {
  const raw = a.stakeholders.trim();
  const isPath = raw.includes("→");
  const entries = NONE.test(raw)
    ? []
    : raw.split(isPath ? "→" : /·|\s\/\s/).map((s) => s.trim()).filter(Boolean)
        .map((text) => ({ text, person: !NOT_A_PERSON.test(text) }));
  const people = entries.filter((e) => e.person).flatMap((e) => e.text.split(/\svia\s/));
  return { raw, isPath, entries, people };
}

export const hasContacts = (a: Application) => stakeholders(a).people.length > 0;

export const byPriority = (x: Application, y: Application) =>
  priorityRank(x.priority) - priorityRank(y.priority) || x.company.localeCompare(y.company);

/** Tracker answers are Yes / No / Not clear. Unknowns stay "?" rather than a guess. */
export function yesNo(value: string): "Y" | "N" | "?" {
  const v = value.trim().toLowerCase();
  if (v === "yes" || v === "y") return "Y";
  if (v === "no" || v === "n") return "N";
  return "?";
}

/** Tile letters for organisations without a logo ("Project B" → "PB"). */
export const companyInitials = (company: string) =>
  company.split(/[\s/+—–-]+/).filter((w) => /^[\p{L}\d]/u.test(w)).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

/** First + last initial of the name part ("José Manuel Calderón" → "JC", "Derek Chang — adjacent…" → "DC"). */
export function initials(person: string) {
  const words = person.split(/\s[—–-]\s|\svia\s/)[0].split(/\s+/).filter(Boolean);
  const caps = words.filter((w) => /^\p{Lu}/u.test(w));
  const pick = caps.length ? caps : words;
  return (pick.length > 1 ? [pick[0], pick[pick.length - 1]] : pick).map((w) => w[0]).join("").toUpperCase();
}

// ─── Dates and follow-ups ────────────────────────────────────────────────
const parseDay = (iso: string) => new Date(iso.length === 10 ? `${iso}T12:00` : iso);

/** "Tue, Oct 6" (adds the time when the value has one: "Tue, Oct 6 · 2:45 PM"). */
export function formatDate(iso: string, withWeekday = true) {
  const d = parseDay(iso);
  const day = d.toLocaleDateString("en-US", { ...(withWeekday && { weekday: "short" }), month: "short", day: "numeric" });
  return iso.length > 10 ? `${day} · ${d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}` : day;
}

/** When to nudge a contact who hasn't replied: last contact + N days (7 by default). */
export function followUp(lastContact: string, days = 7) {
  const due = parseDay(lastContact);
  due.setDate(due.getDate() + days);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return { due, overdue: due <= today, label: due.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }) };
}

/** Official-page status, as shown on cards. */
export const OFFICIAL_STATUS: Record<string, string> = {
  open: "Open now",
  opens_later: "Opens later",
  closed: "Closed",
  rolling: "Rolling",
  no_posting_yet: "No posting yet",
  not_found: "No program page",
};

/** Label for the quote toggle under an event, by where it came from. */
export const FROM_LABEL: Record<string, string> = {
  email: "From the email",
  chat: "From the chat",
  linkedin: "From your LinkedIn export",
  posting: "From the posting",
  note: "From your notes",
  demo: "From the demo data",
};

/** Networking pipeline labels (the API sends the same list as `stages`). */
export const CONTACT_STATUS: Record<string, string> = {
  to_contact: "To contact",
  reached_out: "Reached out",
  call_booked: "Call booked",
  follow_up: "Follow up · 2 weeks",
  keep_warm: "Keep warm",
};

/** Links come from Slack, email and web pages (untrusted): only plain http(s) URLs are ever used as links. */
export const safeUrl = (url: string | null | undefined) => (url && /^https?:\/\/[^\s]+$/i.test(url.trim()) ? url.trim() : undefined);
