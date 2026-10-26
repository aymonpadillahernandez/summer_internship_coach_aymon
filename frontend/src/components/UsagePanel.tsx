import { useEffect, useRef, useState } from "react";
import { fetchRun, fetchUsage, type TraceStep, type UsageReport } from "../api";
import AgentTrace, { AGENTS, fmt, money } from "./AgentTrace";
import { CloseIcon } from "./Icons";

const KIND: Record<string, string> = { intake: "Add what's new", plan: "Plan my week", chat: "Chat", doors: "Who can open the door",
  guide: "Setup guide", discover: "Find openings" };

/** Every AI run with the token counts the model reported, per agent, and today's budget. */
export default function UsagePanel({ onClose, onOpenRecord }: { onClose: () => void; onOpenRecord: (id: string) => void }) {
  const [report, setReport] = useState<UsageReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<{ id: string; trace: TraceStep[] } | null>(null);

  // Load once: the parent passes a new onClose on every render, which must not trigger a reload (it reset typed text).
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    fetchUsage().then(setReport).catch(() => setError("Couldn't load your usage."));
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeRef.current();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const pct = report ? Math.min(100, (report.today_tokens / report.daily_budget) * 100) : 0;
  const totals = report?.runs.reduce(
    (t, r) => ({ input: t.input + r.usage.input, cached: t.cached + r.usage.cached, output: t.output + r.usage.output, runs: t.runs + 1 }),
    { input: 0, cached: 0, output: 0, runs: 0 },
  );

  return (
    <div className="scrim" onClick={onClose}>
      <aside className="sheet usage-sheet" role="dialog" aria-label="AI usage" onClick={(e) => e.stopPropagation()}>
        <header className="sheet-head">
          <div>
            <h2>AI usage</h2>
            <p>Real token counts reported by {report?.model ?? "the model"} for every run, per agent.</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><CloseIcon /></button>
        </header>
        {error && <div className="inline-error">{error}</div>}
        {report && totals && (
          <>
            <section className="sheet-section">
              <h4>Today</h4>
              <div className="budget">
                <div className="budget-bar"><span style={{ width: `${pct}%` }} /></div>
                <p><b>{fmt(report.today_tokens)}</b> of {fmt(report.daily_budget)} tokens in today's budget. Over it, AI features pause until midnight UTC; everything else keeps working.</p>
              </div>
            </section>
            <section className="sheet-section">
              <h4>Last {totals.runs} runs</h4>
              <div className="usage-totals">
                <div><b>{fmt(totals.input)}</b><span>input tokens</span></div>
                <div><b>{fmt(totals.cached)}</b><span>of them cached</span></div>
                <div><b>{fmt(totals.output)}</b><span>output tokens</span></div>
              </div>
              {report.prices.input_per_m == null ? <p className="muted small">Cost is left blank until the model's price is set in backend/config.py; token counts are exact.</p>
                : <p className="muted small">Cost uses {report.model}'s list price per 1M tokens: ${report.prices.input_per_m} input, ${report.prices.cached_input_per_m} cached input, ${report.prices.output_per_m} output ({report.prices.source}).</p>}
              <table className="usage-table">
                <thead><tr><th>When</th><th>What</th><th>Agents</th><th>Input</th><th>Cached</th><th>Output</th><th>Time</th><th>Cost</th></tr></thead>
                <tbody>
                  {report.runs.map((r) => (
                    <tr key={r.run_id} className={open?.id === r.run_id ? "is-open" : ""} onClick={() =>
                      open?.id === r.run_id ? setOpen(null) : fetchRun(r.run_id).then((d) => setOpen({ id: r.run_id, trace: d.trace })).catch(() => {})}>
                      <td>{r.started_at.slice(5, 16)}</td>
                      <td title={r.summary}>{KIND[r.kind] ?? r.kind}{r.status !== "ok" && <em className="run-status"> · {r.status}</em>}</td>
                      <td>{[...new Set(r.agents.map((a) => AGENTS[a.agent]?.short ?? a.agent))].join(", ") || "—"}</td>
                      <td>{fmt(r.usage.input)}</td>
                      <td>{fmt(r.usage.cached)}</td>
                      <td>{fmt(r.usage.output)}</td>
                      <td>{r.seconds != null ? `${r.seconds.toFixed(1)} s` : "—"}</td>
                      <td>{r.usage.cost_usd == null ? "—" : money(r.usage.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {report.runs.length === 0 && <p className="muted">No AI runs yet. Plan your week or add something new.</p>}
              {open && (
                <div className="usage-trace">
                  <h4>Run {open.id}</h4>
                  <AgentTrace trace={open.trace} onOpenRecord={onOpenRecord} />
                </div>
              )}
            </section>
          </>
        )}
      </aside>
    </div>
  );
}
