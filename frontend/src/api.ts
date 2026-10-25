import type { Application, Contact, Lead, Stage, SyncInfo } from "./types";

// The site and the API share one origin (dev: Vite proxy; production: FastAPI serves both).

/** The session is missing or expired: show the sign-in screen. */
export class AuthError extends Error {}

/** A readable message from an API error ({"detail": "..."}). */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let onSignedOut: () => void = () => {};
export const setSignedOutHandler = (fn: () => void) => {
  onSignedOut = fn;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    onSignedOut();
    throw new AuthError("Signed out");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? body.detail.map((d: { msg?: string }) => d.msg).join("; ") : body.detail;
    throw new ApiError(res.status, typeof detail === "string" && detail ? detail : `Error ${res.status}`);
  }
  return res.json() as Promise<T>;
}

const post = <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

// ─── Accounts ───────────────────────────────────────────────────────────
export type User = { id: number; email: string; name: string; is_demo: boolean };

export const fetchMe = () => request<{ user: User }>("/api/auth/me");
export const fetchAuthOptions = () => request<{ signup_code_required: boolean }>("/api/auth/options");
export const signIn = (email: string, password: string) => post<{ user: User }>("/api/auth/login", { email, password });
export const signUp = (email: string, name: string, password: string, code: string) =>
  post<{ user: User }>("/api/auth/signup", { email, name, password, code });
export const startDemo = () => post<{ user: User }>("/api/auth/demo");
export const signOut = () => post<{ ok: boolean }>("/api/auth/logout");
export const deleteAccount = () => request<{ ok: boolean }>("/api/account", { method: "DELETE" });
export const fetchProfile = () => request<{ text: string }>("/api/profile");
export const saveProfile = (text: string) => request<{ text: string }>("/api/profile", { method: "PUT", body: JSON.stringify({ text }) });

// ─── Records ────────────────────────────────────────────────────────────
export const fetchBoard = () => request<{ stages: Stage[]; applications: Application[] }>("/api/applications");
export const fetchNetwork = () => request<{ stages: Stage[]; contacts: Contact[]; sync: SyncInfo }>("/api/network");
export const moveContact = (id: number, status: string) =>
  request<Contact>(`/api/contacts/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
export const updateContact = (id: number, patch: { status?: string; last_contact?: string }) =>
  request<Contact>(`/api/contacts/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
export const fetchLeads = () => request<{ leads: Lead[] }>("/api/leads");

export type DataCheck = { rule: string; area: "internships" | "networking"; id: number; name: string; problem: string; fix: string };
export const fetchChecks = () => request<{ checks: DataCheck[] }>("/api/checks");
export const fetchDone = () => request<{ done: string[] }>("/api/actions/done");
export const markAction = (key: string, done: boolean) =>
  request<{ key: string; done: boolean }>(`/api/actions/${key}`, { method: "PUT", body: JSON.stringify({ done }) });
export const setAppInterest = (id: number, notInterested: boolean) =>
  request<Application>(`/api/applications/${id}/interest`, { method: "PUT", body: JSON.stringify({ not_interested: notInterested }) });
export const setContactInterest = (id: number, notInterested: boolean) =>
  request<Contact>(`/api/contacts/${id}/interest`, { method: "PUT", body: JSON.stringify({ not_interested: notInterested }) });
export const moveApplication = (id: number, status: string) =>
  request<Application>(`/api/applications/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });

// ─── AI runs: every response carries the agent trace and real token usage ──
export type TraceStep = {
  t: number;
  agent: string; // strategist | scout | network | shield | router
  event: string;
  detail: string;
  to?: string;
  seconds?: number;
  tokens?: { input: number; cached: number; output: number };
  records?: string[];
  lines?: { line: number; text: string }[];
  hidden?: string[];
  items?: { item: string; reason: string }[];
};
export type Usage = { requests: number; input: number; cached: number; output: number; reasoning?: number; cost_usd: number | null };
export type RunResult = { run_id: string; status: string; seconds: number; trace: TraceStep[]; usage: Usage };

export type Sample = { id: string; title: string; kind: "auto" | "opportunity" | "conversation"; attack: boolean; description: string; text: string };
export const fetchSamples = () => request<{ samples: Sample[] }>("/api/samples");

export type IntakeResult = RunResult & {
  routes: string[];
  flagged: { line: number; text: string }[];
  hidden: string[];
  saved: {
    opportunities_added?: { id: number; company: string; role: string }[];
    opportunities_updated?: { id: number; company: string; role: string }[];
    leads_added?: number;
    contacts_added?: { id: number; name: string }[];
    contacts_updated?: { id: number; name: string }[];
    events_added?: number;
  };
  rejected: { item: string; reason: string }[];
  fields_not_found: string[];
};
export const runIntake = (text: string, kind: string, label: string) => post<IntakeResult>("/api/intake", { text, kind, label });

export type Candidate = { key: string; title: string; subtitle: string; due: string | null; why: string };
export type PlannedAction = { key: string; title: string; subtitle: string; due: string | null; why_now: string; how: string; record_ids: string[] };
export type CoachPlan = {
  headline: string;
  top_actions: PlannedAction[];
  can_wait: string[];
  watch_outs: string[];
  open_questions: string[];
};
export type SavedPlan = CoachPlan & { run_id: string; created_at: string; usage: Usage; seconds: number; trace: TraceStep[] };
export const runPlan = (candidates: Candidate[]) => post<RunResult & { plan: CoachPlan | null }>("/api/plan", { candidates });
export const fetchLatestPlan = () => request<{ plan: SavedPlan | null }>("/api/plan/latest");

export type ChatMessage = { role: "user" | "assistant"; content: string };
export const askCoach = (messages: ChatMessage[], candidates: Candidate[]) =>
  post<RunResult & { answer: string | null; agent: string | null; model?: string; person?: string | null }>("/api/chat", { messages, candidates });

export type AgentRow = { agent: string; model: string; requests: number; input_tokens: number; cached_tokens: number; output_tokens: number; reasoning_tokens: number; seconds: number; status: string };
export type RunRow = { run_id: string; kind: string; status: string; started_at: string; seconds: number | null; summary: string; agents: AgentRow[]; usage: Usage };
export type UsageReport = {
  runs: RunRow[];
  today_tokens: number;
  daily_budget: number;
  model: string;
  prices: { input_per_m: number | null; cached_input_per_m: number | null; output_per_m: number | null; source: string };
};
export const fetchUsage = () => request<UsageReport>("/api/usage");
export const fetchRun = (id: string) => request<{ run_id: string; kind: string; status: string; seconds: number; trace: TraceStep[]; agents: AgentRow[] }>(`/api/runs/${id}`);
