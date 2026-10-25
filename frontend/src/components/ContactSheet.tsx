import { useEffect, useRef, useState } from "react";
import type { Application, Contact, Stage } from "../types";
import { FROM_LABEL, formatDate, initials, safeUrl } from "../format";
import { CloseIcon, EyeOffIcon } from "./Icons";
import Logo from "./Logo";
import { SourceBadges, nextStep, sourcesOf } from "./ContactCard";

type Props = {
  c: Contact;
  stages: Stage[];
  apps: Map<number, Application>;
  onMove: (id: number, status: string) => void;
  readOnly?: boolean;
  onInterest?: (notInterested: boolean) => void; // owner only
  onPrepare?: () => void; // owner only: open the chat's call-prep expert for this person
  onOpenApp: (a: Application) => void;
  onClose: () => void;
};

function AppChips({ ids, apps, onOpenApp, limit }: { ids: number[]; apps: Map<number, Application>; onOpenApp: Props["onOpenApp"]; limit?: number }) {
  const [all, setAll] = useState(false);
  const list = ids.map((id) => apps.get(id)).filter((a): a is Application => !!a);
  const shown = limit && !all ? list.slice(0, limit) : list;
  return (
    <div className="contact-apps">
      {shown.map((a) => (
        <button key={a.id} className="app-chip" onClick={() => onOpenApp(a)} title={`Open ${a.company} in Summer internships`}>
          <Logo src={a.logo} company={a.company} size={18} />
          <span>{a.company}</span>
        </button>
      ))}
      {limit && list.length > limit && (
        <button className="app-chip app-chip-more" onClick={() => setAll(!all)}>{all ? "Show less" : `+${list.length - limit} more`}</button>
      )}
    </div>
  );
}

export default function ContactSheet({ c, stages, apps, onMove, onOpenApp, onClose, readOnly = false, onInterest, onPrepare }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const pressedBackdrop = useRef(false);
  const next = nextStep(c);

  return (
    <div
      className="scrim"
      onMouseDown={(e) => { pressedBackdrop.current = e.target === e.currentTarget; }}
      onClick={(e) => { if (pressedBackdrop.current && e.target === e.currentTarget) onClose(); }}
    >
      <aside className="sheet" role="dialog" aria-label={c.name}>
        <header className="sheet-head">
          <span className="avatar person-avatar sheet-avatar" aria-hidden>{initials(c.name)}</span>
          <div className="sheet-title">
            <SourceBadges c={c} />
            <h2>{c.name}</h2>
            <p>{c.affiliation}</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><CloseIcon /></button>
        </header>
        {c.not_interested_at && (
          <div className="parked-banner">
            <EyeOffIcon />
            <span>Not interested since {formatDate(c.not_interested_at, false)}. It stays folded at the bottom of its column.</span>
            {!readOnly && onInterest && <button onClick={() => onInterest(false)}>Bring it back</button>}
          </div>
        )}

        <section className="sheet-section">
          <h4>Status</h4>
          <div className="stage-picker">
            {stages.map((s) => (
              <button key={s.key} className={`stage-pill stage-${s.key}${c.status === s.key ? " is-active" : ""}`} disabled={readOnly} onClick={() => onMove(c.id, s.key)}>
                <span className="dot" />{s.label}
              </button>
            ))}
          </div>
          {!readOnly && onPrepare && (
            <button className="interest-btn prepare-btn" onClick={onPrepare} title="Opens the chat's call-prep expert for this person">
              Prepare this call ↗
            </button>
          )}
          {!readOnly && onInterest && !c.not_interested_at && (
            <button className="interest-btn" onClick={() => onInterest(true)} title="Fold this card away at the bottom of its column; you can bring it back any time">
              <EyeOffIcon /> Not interested
            </button>
          )}
        </section>

        <section className="sheet-section">
          <dl className="facts">
            <div><dt>{next.label}</dt><dd>{next.value}{next.detail && <small className="fact-detail">{next.detail}</small>}</dd></div>
            <div><dt>Last contact</dt><dd>{c.last_contact ? formatDate(c.last_contact) : "—"}</dd></div>
            <div><dt>How you know them</dt><dd>{c.how_met || "—"}</dd></div>
            <div><dt>Found in</dt><dd>{sourcesOf(c).map((s) => ({ demo: "Demo data", email: "A pasted email", chat: "A pasted chat", linkedin: "LinkedIn export", posting: "A pasted posting", note: "Your notes", manual: "Added by you" } as Record<string, string>)[s] ?? s).join(" · ")}</dd></div>
          </dl>
          {c.notes && <p className="sheet-notes">{c.notes}</p>}
        </section>

        {c.application_ids.length > 0 && (
          <section className="sheet-section">
            <h4>For these applications</h4>
            <AppChips ids={c.application_ids} apps={apps} onOpenApp={onOpenApp} />
          </section>
        )}

        {c.network_ids.length > 0 && (
          <section className="sheet-section">
            <h4>Could open doors at · {c.network_ids.length} rows</h4>
            <AppChips ids={c.network_ids} apps={apps} onOpenApp={onOpenApp} limit={6} />
          </section>
        )}

        <section className="sheet-section">
          <h4>History · from your emails and Slack</h4>
          {c.events.length ? (
            <ol className="timeline">
              {c.events.map((e) => (
                <li key={e.id}>
                  <time>{formatDate(e.date, false)}</time>
                  <div>
                    {e.text}
                    <details>
                      <summary>{FROM_LABEL[e.origin] ?? "Source"}</summary>
                      <blockquote>{e.evidence}</blockquote>
                      {e.origin === "posting" && safeUrl(e.source_subject)
                        ? <a className="lead-link" href={safeUrl(e.source_subject)} target="_blank" rel="noreferrer">Open the official page ↗</a>
                        : <cite>{e.source_subject}</cite>}
                    </details>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">Nothing with {c.name.split(" ")[0]} in your emails or Slack yet. It will show here after the next sync.</p>
          )}
        </section>
      </aside>
    </div>
  );
}
