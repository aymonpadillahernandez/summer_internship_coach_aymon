import { useState } from "react";
import { ApiError, findDoors, type TraceStep, type Usage } from "../api";
import type { Application, Contact, DoorPaths } from "../types";
import { formatDate } from "../format";
import AgentTrace, { UsageLine } from "./AgentTrace";

/** "Who can open the door": Network intelligence looks at the people your records connect to this opportunity and
 *  suggests up to 3 ways in, each with the ask and a first message you could send yourself. Saved on the card. */
export default function DoorsSection({ app, findContact, onOpenContact, onUpdated }: {
  app: Application;
  findContact: (name: string) => Contact | undefined;
  onOpenContact: (c: Contact) => void;
  onUpdated: (card: Application) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<{ trace: TraceStep[]; usage: Usage; seconds: number } | null>(null);
  const doors: DoorPaths | null = app.door_paths;

  async function find() {
    setBusy(true);
    setError(null);
    try {
      const r = await findDoors(app.id);
      if (!r.doors || !r.card) throw new ApiError(500, "Network intelligence could not answer this time. Try again.");
      setRun({ trace: r.trace, usage: r.usage, seconds: r.seconds });
      onUpdated(r.card);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="sheet-section doors">
      <div className="doors-head">
        <h4>Who can open the door · Network intelligence</h4>
        <button className="toggle" onClick={find} disabled={busy}>{busy ? "Looking…" : doors ? "Look again" : "Find who can help"}</button>
      </div>
      {busy && <div className="working"><span className="pulse" />Checking the people your records connect to {app.company}…</div>}
      {error && <div className="inline-error">{error}</div>}
      {!doors && !busy && <p className="muted small">Finds the realistic ways in from people you already know, with what to ask each one. Nothing is sent.</p>}
      {doors && (
        <>
          {doors.paths.length === 0 && <p className="doors-none">No real way in yet. {doors.next_best}</p>}
          <ol className="door-list">
            {doors.paths.map((p) => {
              const c = findContact(p.name);
              return (
                <li key={p.contact_id}>
                  <div className="door-top">
                    {c ? <button className="person-link" onClick={() => onOpenContact(c)}>{p.name}</button> : <b>{p.name}</b>}
                    <span className={`strength strength-${p.strength}`}>{p.strength}</span>
                  </div>
                  <p>{p.why_them}</p>
                  <p><span className="plan-label">Ask</span>{p.ask}</p>
                  <details>
                    <summary>First message (send it yourself)</summary>
                    <blockquote>{p.first_message}</blockquote>
                  </details>
                </li>
              );
            })}
          </ol>
          {doors.paths.length > 0 && doors.next_best && <p className="muted small">{doors.next_best}</p>}
          <p className="muted small">
            Checked {doors.checked} people{app.door_paths_at && ` · ${formatDate(app.door_paths_at.slice(0, 10), false)}`}
            {doors.usage && ` · ${(doors.usage.input + doors.usage.output).toLocaleString()} tokens`}
          </p>
        </>
      )}
      {run && (
        <details className="how-decided">
          <summary>What the agent did</summary>
          <AgentTrace trace={run.trace} />
          <UsageLine usage={run.usage} seconds={run.seconds} />
        </details>
      )}
    </section>
  );
}
