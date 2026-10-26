import { useState } from "react";
import { ApiError, runDiscover, type DiscoverResult } from "../api";
import AgentTrace, { UsageLine } from "./AgentTrace";

/** The Opportunity scout looks for summer internships on the public job boards companies publish for this
 *  (Greenhouse, Lever, Ashby, SmartRecruiters) at the organisations you track. */
export default function DiscoverPanel({ onChanged, onOpenRecord }: { onChanged: () => Promise<void> | void; onOpenRecord: (id: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DiscoverResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await runDiscover();
      setResult(r);
      if (r.status !== "ok") setError("The scout stopped before finishing (a limit or an error); nothing was saved. Try fewer organisations.");
      await onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The scout could not search this time.");
    } finally {
      setBusy(false);
    }
  };
  const added = result?.saved.opportunities_added ?? [];
  const updated = result?.saved.opportunities_updated ?? [];

  return (
    <section className="panel discover" aria-label="Find openings">
      <header className="panel-head">
        <div>
          <h2>Find openings</h2>
          <p>The Opportunity scout checks the public job boards of the organisations you track for summer internships, and judges each against
            your profile. Only postings it really found are saved, with their link.</p>
        </div>
        <button className="primary-btn" disabled={busy} onClick={go}>{busy ? "Searching…" : "Search job boards"}</button>
      </header>
      {error && <p className="inline-error">{error}</p>}
      {result && (
        <div className="intake-result">
          <p><b>{added.length} new, {updated.length} updated</b>{result.companies ? ` · searched ${result.companies.join(", ")}` : ""}</p>
          <ul className="saved-list">
            {[...added, ...updated].map((o) => (
              <li key={o.id}><button className="link-btn" onClick={() => onOpenRecord(`OPP-${o.id}`)}>{o.company} — {o.role}</button></li>
            ))}
          </ul>
          {result.not_found.length > 0 && (
            <div className="not-found"><h4>No public posting found</h4><ul>{result.not_found.map((n) => <li key={n}>{n}</li>)}</ul></div>
          )}
          <details className="how-decided">
            <summary>What the scout did · run {result.run_id}</summary>
            <AgentTrace trace={result.trace} onOpenRecord={onOpenRecord} />
          </details>
          <UsageLine usage={result.usage} seconds={result.seconds} />
        </div>
      )}
    </section>
  );
}
