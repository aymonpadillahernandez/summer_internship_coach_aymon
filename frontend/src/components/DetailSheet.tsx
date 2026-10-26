import { useEffect, useRef } from "react";
import type { Application, Contact, Stage } from "../types";
import { CONTACT_STATUS, FROM_LABEL, OFFICIAL_STATUS, concepts, formatDate, initials, priorityClass, safeUrl, stakeholders, yesNo } from "../format";
import { CloseIcon, EyeOffIcon, PeopleIcon } from "./Icons";
import Logo from "./Logo";
import DoorsSection from "./DoorsSection";
import PeopleSection from "./PeopleSection";

type Props = {
  app: Application;
  stages: Stage[];
  onMove: (id: number, status: string) => void;
  readOnly?: boolean;
  onInterest?: (notInterested: boolean) => void; // owner only
  onClose: () => void;
  findContact: (name: string) => Contact | undefined;
  onOpenContact: (c: Contact) => void;
  onUpdated?: (card: Application) => void;
};

const LEAD_KIND: Record<string, string> = { posting: "Posting", deadline: "Deadline", event: "Event", tip: "Tip", intro: "Intro" };

/** Name part of a stakeholder entry: "Derek Chang — adjacent…" / "Theo Epstein ’95" / "X via Y" → the person. */
const personName = (text: string) => text.split(/\s[—–]\s|\svia\s/)[0].replace(/\s[’']\d\d$/, "").trim();

export default function DetailSheet({ app, stages, onMove, onClose, findContact, onOpenContact, onInterest, onUpdated, readOnly = false }: Props) {
  /** A name that opens the person on the Networking tab when they are on it. */
  const person = (label: string) => {
    const c = findContact(personName(label));
    return c ? (
      <button className="person-link" onClick={() => onOpenContact(c)} title="Open in Networking">{label}</button>
    ) : label;
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const { isPath, entries, people } = stakeholders(app);
  const pressedBackdrop = useRef(false);

  return (
    <div
      className="scrim"
      onMouseDown={(e) => { pressedBackdrop.current = e.target === e.currentTarget; }}
      onClick={(e) => { if (pressedBackdrop.current && e.target === e.currentTarget) onClose(); }}
    >
      <aside className="sheet" role="dialog" aria-label={app.company}>
        <header className="sheet-head">
          <Logo src={app.logo} company={app.company} size={52} />
          <div className="sheet-title">
            <span className={`prio ${priorityClass(app.priority)}`} title="Priority">{app.priority}</span>
            <h2>{app.company}</h2>
            <p>{app.role}</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><CloseIcon /></button>
        </header>
        {app.not_interested_at && (
          <div className="parked-banner">
            <EyeOffIcon />
            <span>Not interested since {formatDate(app.not_interested_at, false)}. It stays folded at the bottom of its column.</span>
            {!readOnly && onInterest && <button onClick={() => onInterest(false)}>Bring it back</button>}
          </div>
        )}

        <section className="sheet-section">
          <h4>Status</h4>
          <div className="stage-picker">
            {stages.map((s) => (
              <button
                key={s.key}
                className={`stage-pill stage-${s.key}${app.status === s.key ? " is-active" : ""}`}
                disabled={readOnly} onClick={() => onMove(app.id, s.key)}
              >
                <span className="dot" />{s.label}
              </button>
            ))}
          </div>
          {!readOnly && onInterest && !app.not_interested_at && (
            <button className="interest-btn" onClick={() => onInterest(true)} title="Fold this card away at the bottom of its column; you can bring it back any time">
              <EyeOffIcon /> Not interested
            </button>
          )}
        </section>

        <section className="sheet-section">
          <dl className="facts">
            <div><dt>Formal internship</dt><dd>{yesNo(app.formal_internship) === "?" ? "? · not clear" : yesNo(app.formal_internship)}</dd></div>
            <div><dt>MBA eligible</dt><dd>{yesNo(app.mba_eligible) === "?" ? "? · not clear" : yesNo(app.mba_eligible)}</dd></div>
            <div><dt>Deadline / trigger</dt><dd>{app.deadline || "—"}</dd></div>
            <div><dt>Location</dt><dd>{app.location || "—"}</dd></div>
            <div><dt>Priority</dt><dd>{app.priority || "—"}</dd></div>
          </dl>
        </section>

        {app.verified_status && (
          <section className="sheet-section">
            <h4>Page you linked · read by the Opportunity scout {formatDate(app.verified_on ?? "", false)}</h4>
            <div className={`official official-lg os-${app.verified_status}`}>
              <span>
                <b>{OFFICIAL_STATUS[app.verified_status]}</b>
                {app.verified_summary}
              </span>
            </div>
            {(app.verified_opens || app.verified_deadline) && (
              <dl className="facts facts-tight">
                {app.verified_opens && <div><dt>Opens</dt><dd>{app.verified_opens}</dd></div>}
                {app.verified_deadline && <div><dt>Deadline</dt><dd>{app.verified_deadline}</dd></div>}
              </dl>
            )}
            {app.verified_evidence && <blockquote className="official-quote">“{app.verified_evidence}”</blockquote>}
            {safeUrl(app.verified_url) && <a className="lead-link" href={safeUrl(app.verified_url)} target="_blank" rel="noopener noreferrer">Open the page ↗</a>}
          </section>
        )}
        {app.fit && app.fit !== "unknown" && (
          <section className="sheet-section">
            <h4>Fit with your profile · Opportunity scout</h4>
            <p className="fit-line"><span className={`fit-badge fit-${app.fit}`}>{app.fit} fit</span> {app.fit_reason}</p>
          </section>
        )}
        {safeUrl(app.source_url) && !app.verified_status && (
          <section className="sheet-section">
            <h4>Where this came from</h4>
            <a className="lead-link" href={safeUrl(app.source_url)} target="_blank" rel="noopener noreferrer">The posting ↗</a>
          </section>
        )}

        {onUpdated && <DoorsSection app={app} findContact={findContact} onOpenContact={onOpenContact} onUpdated={onUpdated} />}
        {onUpdated && <PeopleSection app={app} />}

        <section className="sheet-section">
          <h4>Context · 3 key concepts to keep in mind</h4>
          <ol className="concepts">
            {concepts(app).map((c) => <li key={c}>{c}</li>)}
          </ol>
        </section>

        {app.activity.length > 0 && (
          <section className="sheet-section">
            <h4>Activity · from what you added</h4>
            <ol className="timeline">
              {app.activity.map((e) => (
                <li key={e.id}>
                  <time>{formatDate(e.date, false)}</time>
                  <div>
                    <b>{e.contact ? person(e.contact) : null}</b> — {e.text}
                    <details>
                      <summary>{FROM_LABEL[e.origin] ?? "Source"}</summary>
                      <blockquote>{e.evidence}</blockquote>
                      <cite>{e.source_subject}</cite>
                    </details>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        )}

        {app.leads.length > 0 && (
          <section className="sheet-section">
            <h4>Leads · deadlines, events and tips from what you added</h4>
            <ol className="timeline">
              {app.leads.map((l) => (
                <li key={l.id}>
                  <time>{formatDate(l.date, false)}</time>
                  <div>
                    <span className={`lead-kind lk-${l.kind}`}>{LEAD_KIND[l.kind]}</span> {l.summary}
                    {(l.when_text || l.posted_by) && (
                      <small className="lead-meta">{[l.when_text && `When: ${l.when_text}`, l.posted_by && `Posted by ${l.posted_by}`].filter(Boolean).join(" · ")}</small>
                    )}
                    {safeUrl(l.url) && <a className="lead-link" href={safeUrl(l.url)} target="_blank" rel="noreferrer">Open link</a>}
                    <details>
                      <summary>{FROM_LABEL[l.origin] ?? "Source"}</summary>
                      <blockquote>{l.evidence}</blockquote>
                      <cite>{l.source_subject}</cite>
                    </details>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        )}

        {app.found.length > 0 && (
          <section className="sheet-section">
            <h4>People to approach</h4>
            <ul className="people">
              {app.found.map((f) => (
                <li key={f.id}>
                  <span className="avatar avatar-web">{initials(f.name)}</span>
                  <div className="network-person">
                    <span><b>{person(f.name)}</b> · {f.affiliation.split(" · ").slice(1).join(" · ") || f.affiliation}</span>
                    {f.notes && <small>{f.notes}</small>}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        {app.network.length > 0 && (
          <section className="sheet-section">
            <h4>In your network · could open doors here</h4>
            <ul className="people">
              {app.network.map((n) => (
                <li key={n.id}>
                  <span className="avatar">{initials(n.name)}</span>
                  <div className="network-person">
                    <span><b>{person(n.name)}</b> · {n.affiliation}</span>
                    <small>
                      {CONTACT_STATUS[n.status] ?? n.status}
                      {n.next_date ? ` · ${formatDate(n.next_date)}` : n.next_step ? ` · ${n.next_step}` : ""}
                    </small>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="sheet-section">
          <h4>Key stakeholders{isPath && people.length ? " · referral path" : ""}</h4>
          {entries.length ? (
            <ul className={`people${isPath ? " is-path" : ""}`}>
              {entries.map((e, i) => (
                <li key={i} className={e.person ? "" : "is-group"}>
                  {e.person
                    ? <span className="avatar">{initials(e.text)}</span>
                    : <span className="avatar avatar-group"><PeopleIcon /></span>}
                  {e.person ? person(e.text) : e.text}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No contacts mapped yet.</p>
          )}
        </section>
      </aside>
    </div>
  );
}
