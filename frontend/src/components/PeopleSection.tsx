import { useState } from "react";
import { ApiError, findPeople, type PeopleResult } from "../api";
import type { Application } from "../types";
import AgentTrace, { UsageLine } from "./AgentTrace";

/** "Key people and alumni": Network intelligence searches the open web for the people worth knowing at this
 *  organisation, alumni of the student's school included. Each one is saved (To contact) only if their public page
 *  names them; the student reaches out themselves, through their network or the alumni directory. */
export default function PeopleSection({ app, onChanged }: { app: Application; onChanged?: () => void | Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PeopleResult | null>(null);

  async function find() {
    setBusy(true);
    setError(null);
    try {
      const r = await findPeople(app.id);
      if (r.status !== "ok") throw new ApiError(500, "Network intelligence could not search this time. Try again.");
      setResult(r);
      await onChanged?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="doors people-web">
      <div className="doors-head">
        <h4>Key people and alumni at {app.company}</h4>
        <button className="toggle" disabled={busy} onClick={find}>{busy ? "Searching the web…" : result ? "Search again" : "Find on the web"}</button>
      </div>
      {!result && !busy && <p className="muted small">Network intelligence searches public pages (the organisation's site, news, school pages) for the people behind
        this role and alumni of your school. Only people whose page names them are saved, to Networking as To contact. No contact details.</p>}
      {error && <p className="inline-error">{error}</p>}
      {result && (
        <>
          <ul className="people-list">
            {result.people.map((p) => (
              <li key={p.name}>
                <div><b>{p.name}</b>{p.alum && <span className="alum-badge">Alum of your school</span>}</div>
                <span className="muted small">{p.title}</span>
                <p className="small">{p.why}</p>
                <a className="lead-link" href={p.url} target="_blank" rel="noopener noreferrer">Source page ↗</a>
              </li>
            ))}
            {result.people.length === 0 && <li className="muted small">No one could be confirmed on a public page.</li>}
          </ul>
          {result.next_best && <p className="small"><b>Next best:</b> {result.next_best}</p>}
          {result.not_confirmed.length > 0 && <p className="muted small">Not confirmed (not saved): {result.not_confirmed.map((x) => x.item).join(", ")}.</p>}
          <details className="how-decided"><summary>What Network intelligence did</summary><AgentTrace trace={result.trace} onOpenRecord={() => {}} /></details>
          <UsageLine usage={result.usage} seconds={result.seconds} />
        </>
      )}
    </section>
  );
}
