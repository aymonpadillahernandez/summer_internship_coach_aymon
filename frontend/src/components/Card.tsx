import type { Application } from "../types";
import { CONTACT_STATUS, OFFICIAL_STATUS, concepts, followUp, formatDate, initials, priorityClass, stakeholders, yesNo } from "../format";
import { ChatIcon, CheckCircleIcon, ClockIcon, MailIcon, PeopleIcon, PinIcon } from "./Icons";
import Logo from "./Logo";
import { dragHandlers, useCardClicks, type DragProps } from "./Board";

type Props = {
  app: Application;
  statusLabel: string;
  onOpen: (app: Application) => void;
  drag: DragProps;
};

function Flag({ label, value, raw }: { label: string; value: "Y" | "N" | "?"; raw: string }) {
  const tone = value === "Y" ? "yes" : value === "N" ? "no" : "unknown";
  return (
    <span className="flag" title={`${label}: ${raw || "not recorded"}`}>
      {label}
      <b className={`yn yn-${tone}`}>{value}</b>
    </span>
  );
}

export default function Card({ app, statusLabel, onOpen, drag }: Props) {
  const { raw, entries, people } = stakeholders(app);
  const latest = app.activity[0];
  const live = app.verified_status === "open" || app.verified_status === "opens_later" || app.verified_status === "rolling";
  const nudge = latest?.contact_status === "reached_out" && app.last_contact ? followUp(app.last_contact, app.follow_up_days) : null;
  // Compact by default: one click opens it small (another click closes it), a double click opens the full sheet.
  const { open, setOpen, onClick } = useCardClicks(() => onOpen(app));

  if (!open) {
    return (
      <article
        className={`card is-compact${drag.dragging ? " is-dragging" : ""}`}
        {...dragHandlers(app.id, drag)}
        tabIndex={0}
        title="Click to open · double-click for the full card"
        onClick={onClick}
        onKeyDown={(e) => e.key === "Enter" && setOpen(true)}
      >
        <div className="compact-row">
          <Logo src={app.logo} company={app.company} size={28} />
          <div className="compact-text">
            <h3 className="card-company">{app.company}</h3>
            <p className="card-role">{app.role}</p>
          </div>
          <span className={`prio ${priorityClass(app.priority)}`} title="Priority">{app.priority || "—"}</span>
        </div>
        {app.deadline && <p className="compact-line"><ClockIcon /><span>{app.deadline}</span></p>}
      </article>
    );
  }

  return (
    <article
      className={`card${drag.dragging ? " is-dragging" : ""}`}
      {...dragHandlers(app.id, drag)}
      tabIndex={0}
      title="Click to close · double-click for the full card"
      onClick={onClick}
      onKeyDown={(e) => e.key === "Enter" && onOpen(app)}
    >
      <div className="card-top">
        <span className="card-top-left">
          <span className={`prio ${priorityClass(app.priority)}`} title="Priority">{app.priority || "—"}</span>
          {app.origin !== "demo" && app.origin !== "manual" && (
            <span className="new-badge" title="Added by the Opportunity scout from something you pasted">
              New
            </span>
          )}
          {app.fit && app.fit !== "unknown" && (
            <span className={`fit-badge fit-${app.fit}`} title={app.fit_reason ?? "Fit with your profile"}>{app.fit} fit</span>
          )}
        </span>
        <span className={`status stage-${app.status}`}><span className="dot" />{statusLabel}</span>
      </div>

      <div className="card-title">
        <Logo src={app.logo} company={app.company} />
        <div>
          <h3 className="card-company">{app.company}</h3>
          <p className="card-role">{app.role}</p>
        </div>
      </div>

      <div className="deadline" title="Deadline / trigger">
        <ClockIcon />
        <span>
          <em>Deadline</em>
          {app.deadline || "Not recorded"}
        </span>
      </div>
      <span className="meta" title="Location"><PinIcon />{app.location || "No location recorded"}</span>

      {app.verified_status && (
        <div className={`official os-${app.verified_status}`} title={app.verified_evidence ? `“${app.verified_evidence}”` : ""}>
          <CheckCircleIcon />
          <span>
            <b>{OFFICIAL_STATUS[app.verified_status]}</b>
            {app.verified_summary}
            <small>
              Page you linked · read {formatDate(app.verified_on ?? "", false)}
              {app.verified_fit === "no" && live && <em className="fit fit-no">Not for MBAs</em>}
              {app.verified_fit === "check" && live && <em className="fit fit-check">Check fit</em>}
            </small>
          </span>
        </div>
      )}

      {latest && (
        <div className={`card-activity${nudge?.overdue ? " is-due" : ""}`} title={`From: ${latest.source_subject}`}>
          <MailIcon />
          <span>
            <b>{formatDate(latest.date, false)} · {latest.contact}</b>
            {CONTACT_STATUS[latest.contact_status ?? ""] ?? ""}
            {nudge && (nudge.overdue ? " · follow up now" : ` · nudge ${nudge.label}`)}
          </span>
        </div>
      )}

      {app.leads.length > 0 && (
        <div className="card-leads" title={app.leads.map((l) => l.summary).join("\n")}>
          <ChatIcon />
          <span>
            <b>
              {app.leads.length === 1 ? "1 lead" : `${app.leads.length} leads`} from{" "}
              {[...new Set(app.leads.map((l) => ({ posting: "postings", chat: "chats", email: "emails", demo: "club news" } as Record<string, string>)[l.origin] ?? "your notes"))].join(" & ")}
            </b>
            {app.leads[0].summary}
          </span>
        </div>
      )}

      <div className="card-flags">
        <Flag label="Formal internship" value={yesNo(app.formal_internship)} raw={app.formal_internship} />
        <Flag label="MBA eligible" value={yesNo(app.mba_eligible)} raw={app.mba_eligible} />
      </div>

      <div className="card-block">
        <h4>Keep in mind</h4>
        <ol className="mini-concepts">
          {concepts(app).map((c) => <li key={c}>{c}</li>)}
        </ol>
      </div>

      {app.found.length > 0 && (
        <div className="card-network card-found" title={app.found.map((f) => `${f.name} · ${f.affiliation}`).join("\n")}>
          <span>People to approach: <b>{app.found.map((f) => f.name).join(", ")}</b></span>
        </div>
      )}

      {app.network.length > 0 && (
        <div className="card-network" title="People in your network who could open doors here">
          <span className="avatars" aria-hidden>
            {app.network.slice(0, 2).map((n) => <span key={n.id} className="avatar-sm">{initials(n.name)}</span>)}
          </span>
          <span>In your network: <b>{app.network.map((n) => n.name).join(", ")}</b></span>
        </div>
      )}

      <div className={`card-people${people.length ? "" : " is-empty"}`} title="Key stakeholders">
        <span className="avatars" aria-hidden>
          {people.slice(0, 3).map((p, i) => <span key={i} className="avatar-sm">{initials(p)}</span>)}
          {people.length > 3 && <span className="avatar-sm avatar-more">+{people.length - 3}</span>}
          {!people.length && (
            entries.length
              ? <span className="avatar-sm avatar-group"><PeopleIcon /></span>
              : <span className="avatar-sm avatar-empty" />
          )}
        </span>
        <span className="people-text">{entries.length ? raw : "No contacts mapped yet"}</span>
      </div>
      <button className="card-collapse" onClick={(e) => { e.stopPropagation(); onOpen(app); }}>Open full card ↗</button>
    </article>
  );
}
