import { useState } from "react";
import { ApiError, runDiscover, runWebShortlist, type DiscoverResult, type WebShortlistResult } from "../api";
import AgentTrace, { UsageLine } from "./AgentTrace";

/** The Opportunity scout looks for summer internships on the public job boards companies publish for this
 *  (Greenhouse, Lever, Ashby, SmartRecruiters) at the organisations you track. */
export default function DiscoverPanel({ onChanged, onOpenRecord }: { onChanged: () => Promise<void> | void; onOpenRecord: (id: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DiscoverResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState("");
  const [web, setWeb] = useState<WebShortlistResult | null>(null);

  const goWeb = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await runWebShortlist(focus);
      setWeb(r);
      if (r.status !== "ok") setError("The scout stopped before finishing; nothing was saved. Try again.");
      await onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The scout could not search this time.");
    } finally {
      setBusy(false);
    }
  };
  const webSaved = web ? [...(web.saved.opportunities_added ?? []), ...(web.saved.opportunities_updated ?? [])] : [];

  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      setWeb(null);
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
          <p>The Opportunity scout searches <b>the whole web</b> for internships that fit your profile, including organisations you don't track
            yet, or the public job boards of the ones you do. The app opens every result's page: only postings it confirms are saved, with their link.</p>
        </div>
      </header>
      <div className="discover-actions">
        <input value={focus} maxLength={300} placeholder="Optional focus, e.g. sports media strategy in New York" onChange={(e) => setFocus(e.target.value)} />
        <button className="primary-btn" disabled={busy} onClick={goWeb}>{busy ? "Searching…" : "Search the whole web"}</button>
        <button className="toggle" disabled={busy} onClick={go}>Search my organisations' job boards</button>
      </div>
      {web && (
        <div className="intake-result">
          <p><b>{webSaved.length} confirmed and saved</b>{web.searched_for.length ? ` · searched for: ${web.searched_for.join("; ")}` : ""}</p>
          <ul className="saved-list">
            {webSaved.map((o) => (
              <li key={o.id}><button className="link-btn" onClick={() => onOpenRecord(`OPP-${o.id}`)}>{o.company} — {o.role}</button></li>
            ))}
          </ul>
          {web.not_confirmed.length > 0 && (
            <div className="not-found"><h4>Found but not confirmed (not saved; open the link to check)</h4><ul>
              {web.not_confirmed.map((x) => <li key={x.item + (x.url ?? "")}>{x.url ? <a href={x.url} target="_blank" rel="noopener noreferrer">{x.item} ↗</a> : x.item} · {x.reason}</li>)}
            </ul></div>
          )}
          <details className="how-decided"><summary>What the scout did · run {web.run_id}</summary><AgentTrace trace={web.trace} onOpenRecord={onOpenRecord} /></details>
          <UsageLine usage={web.usage} seconds={web.seconds} />
        </div>
      )}
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
