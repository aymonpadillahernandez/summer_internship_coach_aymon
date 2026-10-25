import type { TraceStep, Usage } from "../api";

export const AGENTS: Record<string, { name: string; short: string; tone: string; role: string }> = {
  strategist: { name: "Career strategist", short: "Strategist", tone: "ag-strategist", role: "Boss · ranks your week" },
  scout: { name: "Opportunity scout", short: "Scout", tone: "ag-scout", role: "Opportunities · fit · deadlines" },
  network: { name: "Network intelligence", short: "Network", tone: "ag-network", role: "People · relationships · call prep" },
  shield: { name: "Shield", short: "Shield", tone: "ag-shield", role: "Code: hidden text, injected instructions, unsupported facts" },
  router: { name: "Router", short: "Router", tone: "ag-router", role: "Code: sends each paste to the right specialist" },
};

const EVENT: Record<string, string> = {
  planning: "Started planning",
  thinking: "Read your question",
  delegated: "Asked",
  searching: "Searched your records",
  answered: "Answered",
  reading: "Read your paste",
  preparing: "Built the dossier",
  finished: "Done",
  checked_data: "Ran the data checks",
  routed: "Routed",
  export_filtered: "Filtered the export",
  hidden_text_removed: "Removed hidden text",
  html_cleaned: "Cleaned the page",
  instructions_quarantined: "Quarantined injected instructions",
  rejected_unsupported: "Rejected unsupported items",
  rejected_invented_action: "Rejected an invented action",
  ids_dropped: "Dropped ids it was not given",
  delegation_refused: "Delegation cap reached",
  usage_limit: "Stopped at the usage limit",
  timeout: "Timed out",
  error: "Failed",
  model_rejected: "Rejected a substituted model",
};

export const fmt = (n: number) => n.toLocaleString("en-US");
export const money = (v: number | null | undefined) => (v == null ? "cost: price not set" : v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(3)}`);

/** Totals for one run: the numbers the tokenomics section is built from. */
export function UsageLine({ usage, seconds }: { usage: Usage; seconds?: number }) {
  return (
    <div className="usage-line" title="Tokens reported by the model for this run (all agents)">
      <span><b>{fmt(usage.input)}</b> input</span>
      <span><b>{fmt(usage.cached)}</b> cached</span>
      <span><b>{fmt(usage.output)}</b> output</span>
      <span><b>{usage.requests}</b> model calls</span>
      {seconds != null && <span><b>{seconds.toFixed(1)}</b> s</span>}
      <span className="usage-cost">{money(usage.cost_usd)}</span>
    </div>
  );
}

/** "How I decided": the step-by-step trace of one run — who asked whom, what was read, what the shield stopped. */
export default function AgentTrace({ trace, onOpenRecord }: { trace: TraceStep[]; onOpenRecord?: (id: string) => void }) {
  return (
    <ol className="trace">
      {trace.map((s, i) => {
        const a = AGENTS[s.agent] ?? { name: s.agent, short: s.agent, tone: "ag-router", role: "" };
        const to = s.to ? AGENTS[s.to]?.name : null;
        const bad = ["error", "timeout", "usage_limit", "model_rejected"].includes(s.event);
        return (
          <li key={i} className={`trace-step${bad ? " is-bad" : ""}${s.agent === "shield" ? " is-shield" : ""}`}>
            <span className={`agent-chip ${a.tone}`} title={a.role}>{a.short}</span>
            <div className="trace-body">
              <div className="trace-head">
                <b>{EVENT[s.event] ?? s.event}{to ? ` ${to}` : ""}</b>
                <time>{s.t.toFixed(1)} s</time>
              </div>
              {s.detail && <p>{s.detail}</p>}
              {s.tokens && (
                <p className="trace-tokens">
                  {fmt(s.tokens.input)} in · {fmt(s.tokens.cached)} cached · {fmt(s.tokens.output)} out{s.seconds != null && ` · ${s.seconds.toFixed(1)} s`}
                </p>
              )}
              {s.records && s.records.length > 0 && (
                <p className="trace-records">
                  {s.records.map((r) => (
                    <button key={r} className="record-chip" onClick={() => onOpenRecord?.(r)}>{r}</button>
                  ))}
                </p>
              )}
              {s.lines && s.lines.map((l) => <blockquote key={l.line} className="shield-quote">Line {l.line}: “{l.text}”</blockquote>)}
              {s.hidden && s.hidden.map((h, j) => <blockquote key={j} className="shield-quote">Hidden: “{h}”</blockquote>)}
              {s.items && s.items.map((it, j) => <p key={j} className="shield-item"><b>{it.item}</b> — {it.reason}</p>)}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
