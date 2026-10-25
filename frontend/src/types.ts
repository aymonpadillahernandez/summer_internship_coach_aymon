export type Stage = { key: string; label: string };

export type Application = {
  id: number;
  company: string;
  role: string;
  not_interested_at: string | null; // set aside: folded at the bottom of its column
  formal_internship: string;
  mba_eligible: string;
  deadline: string;
  location: string;
  priority: string;
  context: string;
  stakeholders: string;
  status: string;
  last_contact: string | null;
  follow_up_days: number;
  notes: string;
  logo: string | null;
  origin: string; // demo | posting | chat | linkedin | manual
  fit: "strong" | "possible" | "weak" | "unknown" | null;
  fit_reason: string | null;
  source_url: string;
  added_on: string | null;
  // What the official careers page said when last checked (null if not checked or not verifiable)
  verified_status: "open" | "opens_later" | "closed" | "rolling" | "no_posting_yet" | "not_found" | null;
  verified_summary: string | null;
  verified_opens: string | null;
  verified_deadline: string | null;
  verified_url: string | null;
  verified_evidence: string | null;
  verified_on: string | null;
  verified_fit: "yes" | "check" | "no" | null;
  activity: Activity[];
  network: NetworkLink[];
  leads: Lead[];
  found: { id: number; name: string; affiliation: string; status: string; notes: string; url: string }[];
  created_at: string;
  updated_at: string;
};

export type Origin = "demo" | "posting" | "chat" | "email" | "linkedin" | "note" | "manual";

export type Activity = {
  id: number;
  date: string;
  text: string;
  evidence: string;
  source_subject: string;
  origin: Origin;
  contact: string | null;
  contact_status: string | null;
};

export type Lead = {
  id: number;
  application_ids: number[];
  kind: "posting" | "deadline" | "event" | "tip" | "intro";
  date: string;
  when_text: string;
  summary: string;
  posted_by: string;
  evidence: string;
  url: string;
  origin: Origin;
  source_subject: string;
};

export type NetworkLink = {
  id: number;
  name: string;
  affiliation: string;
  status: string;
  next_step: string | null;
  next_date: string | null;
  last_contact: string | null;
};

export type ContactEvent = Omit<Activity, "contact" | "contact_status">;

export type Contact = {
  id: number;
  name: string;
  affiliation: string;
  not_interested_at: string | null;
  status: string;
  last_contact: string | null;
  how_met: string;
  next_step: string | null;
  next_date: string | null;
  application_ids: number[];
  network_ids: number[];
  source: Origin;
  notes: string;
  events: ContactEvent[];
};

export type SyncInfo = { synced_on: string | null; emails_searched: number | null; emails_read: number | null };
