import { useEffect, useState } from "react";
import { decideDraft, fetchOutbox, type Draft } from "../api";

/** Drafts the Career coach wrote. The app never sends anything: approving a draft lets you copy it or open it in
 *  your own mail app, where you choose the address and press send yourself. */
export default function OutboxPanel({ refreshKey = 0 }: { refreshKey?: number }) {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [copied, setCopied] = useState<number | null>(null);
  const load = () => fetchOutbox().then((r) => setDrafts(r.drafts)).catch(() => {});
  useEffect(() => {
    load();
  }, [refreshKey]);
  if (!drafts.length) return null;

  const approve = async (d: Draft) => {
    if (d.status !== "approved") await decideDraft(d.id, "approved");
    load();
  };
  const copy = async (d: Draft) => {
    try {  // the clipboard first, while the click still counts as a user gesture
      await navigator.clipboard.writeText(`${d.subject}\n\n${d.body}`);
      setCopied(d.id);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      /* clipboard blocked: the text stays on screen to copy by hand */
    }
    approve(d).catch(() => {});
  };
  const openMail = async (d: Draft) => {
    await approve(d);
    window.location.href = `mailto:?subject=${encodeURIComponent(d.subject)}&body=${encodeURIComponent(d.body)}`;
  };

  return (
    <section className="panel outbox" aria-label="Outbox">
      <header className="panel-head">
        <div>
          <h2>Outbox · {drafts.length} draft{drafts.length === 1 ? "" : "s"}</h2>
          <p>Written by your Career coach when you asked. Never sent by the app: approve one to copy it or open it in your own mail.</p>
        </div>
      </header>
      <ul className="draft-list">
        {drafts.map((d) => (
          <li key={d.id} className="draft">
            <div className="draft-head">
              <b>To {d.to_name}</b>
              <span className={`sync-chip ${d.status === "approved" ? "is-on" : ""}`}>{d.status === "approved" ? "Approved" : "Draft"}</span>
            </div>
            {d.subject && <p className="draft-subject">{d.subject}</p>}
            <p className="draft-body">{d.body}</p>
            <div className="draft-actions">
              <button className="primary-btn" onClick={() => copy(d)}>{copied === d.id ? "Copied" : "Approve & copy"}</button>
              <button className="toggle" onClick={() => openMail(d)}>Approve & open in Mail</button>
              <button className="link-btn" onClick={() => decideDraft(d.id, "discarded").then(load)}>Discard</button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
