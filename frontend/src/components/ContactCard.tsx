import type { Application, Contact } from "../types";
import { followUp, formatDate, initials } from "../format";
import { callPassed, followUpDue } from "../actions";
import { CalendarIcon, ChatIcon, ClockIcon, GlobeIcon, LinkIcon, ListIcon, MailIcon, NoteIcon, PeopleIcon } from "./Icons";
import Logo from "./Logo";
import { dragHandlers, useCardClicks, type DragProps } from "./Board";

export type NextStep = { tone: "due" | "booked" | "todo" | "calm"; label: string; value: string; detail?: string };

/** What to do next with this person, derived only from what is recorded. */
export function nextStep(c: Contact): NextStep {
  switch (c.status) {
    case "call_booked":
      if (c.next_date && callPassed(c.next_date))
        return { tone: "due", label: "Call was", value: formatDate(c.next_date), detail: "Did it happen? Move them to Follow up" };
      return { tone: "booked", label: "Call booked", value: c.next_date ? formatDate(c.next_date) : "Date not set", detail: c.next_step ?? undefined };
    case "follow_up": {
      const due = followUpDue(c);
      const overdue = due < new Date(new Date().toDateString());
      const when = formatDate(`${due.getFullYear()}-${String(due.getMonth() + 1).padStart(2, "0")}-${String(due.getDate()).padStart(2, "0")}`, false);
      return { tone: overdue ? "due" : "todo", label: overdue ? "Follow up now" : "Follow up by", value: overdue ? `Was due ${when}` : when, detail: c.next_step ?? undefined };
    }
    case "reached_out": {
      if (!c.last_contact) return { tone: "todo", label: "Nudge", value: "About a week after reaching out", detail: "Date of first message not recorded" };
      const f = followUp(c.last_contact);
      return f.overdue
        ? { tone: "due", label: "Follow up", value: "Now", detail: `No reply since ${formatDate(c.last_contact, false)}` }
        : { tone: "todo", label: "Nudge", value: f.label, detail: `No reply since ${formatDate(c.last_contact, false)}` };
    }
    case "to_contact":
      return { tone: "todo", label: "Next step", value: "Reach out" };
    default:
      return { tone: "calm", label: "Last touch", value: c.last_contact ? formatDate(c.last_contact) : "Not recorded" };
  }
}

const SOURCES: Record<string, { label: string; title: string; Icon: () => React.JSX.Element }> = {
  demo: { label: "Demo", title: "Part of the demo student's data", Icon: ListIcon },
  manual: { label: "You", title: "Added by you", Icon: NoteIcon },
  note: { label: "You", title: "From your notes", Icon: NoteIcon },
  email: { label: "Email", title: "From an email you pasted", Icon: MailIcon },
  chat: { label: "Chat", title: "From a chat you pasted (WhatsApp, Slack or texts)", Icon: ChatIcon },
  linkedin: { label: "LinkedIn", title: "From your LinkedIn connections export", Icon: PeopleIcon },
  posting: { label: "Posting", title: "From a job posting you pasted", Icon: GlobeIcon },
};

/** Every place this person shows up: where they were first found, then where their history comes from. */
export const sourcesOf = (c: Contact) => [...new Set([c.source, ...c.events.map((e) => e.origin)])];

export const SourceBadges = ({ c }: { c: Contact }) => (
  <span className="sources">
    {sourcesOf(c).map((s) => {
      const { label, title, Icon } = SOURCES[s] ?? SOURCES.note;
      return (
        <span key={s} className={`source src-${s}`} title={title}>
          <Icon />
          {label}
        </span>
      );
    })}
  </span>
);

type Props = {
  c: Contact;
  statusLabel: string;
  apps: Map<number, Application>;
  onOpen: (c: Contact) => void;
  onOpenApp: (a: Application) => void;
  drag: DragProps;
};

export default function ContactCard({ c, statusLabel, apps, onOpen, onOpenApp, drag }: Props) {
  const next = nextStep(c);
  const linked = c.application_ids.map((id) => apps.get(id)).filter((a): a is Application => !!a);
  const doors = c.network_ids.length;
  const latest = c.events[0];
  const NextIcon = next.tone === "booked" ? CalendarIcon : c.status === "reached_out" ? MailIcon : ClockIcon;
  // Compact by default: one click opens it small (another click closes it), a double click opens the full sheet.
  const { open, setOpen, onClick } = useCardClicks(() => onOpen(c));

  if (!open) {
    return (
      <article
        className={`card contact-card is-compact${drag.dragging ? " is-dragging" : ""}`}
        {...dragHandlers(c.id, drag)}
        tabIndex={0}
        title="Click to open · double-click for the full card"
        onClick={onClick}
        onKeyDown={(e) => e.key === "Enter" && setOpen(true)}
      >
        <div className="compact-row">
          <span className="avatar person-avatar compact-avatar" aria-hidden>{initials(c.name)}</span>
          <div className="compact-text">
            <h3 className="card-company">{c.name}</h3>
            <p className="card-role">{c.affiliation}</p>
          </div>
        </div>
        <p className={`compact-line next-${next.tone}`}><NextIcon /><span>{next.label} · {next.value}</span></p>
      </article>
    );
  }

  return (
    <article
      className={`card contact-card${drag.dragging ? " is-dragging" : ""}`}
      {...dragHandlers(c.id, drag)}
      tabIndex={0}
      title="Click to close · double-click for the full card"
      onClick={onClick}
      onKeyDown={(e) => e.key === "Enter" && onOpen(c)}
    >
      <div className="card-top">
        <SourceBadges c={c} />
        <span className={`status stage-${c.status}`}><span className="dot" />{statusLabel}</span>
      </div>

      <div className="card-title">
        <span className="avatar person-avatar" aria-hidden>{initials(c.name)}</span>
        <div>
          <h3 className="card-company">{c.name}</h3>
          <p className="card-role">{c.affiliation}</p>
        </div>
      </div>

      <div className={`deadline next-${next.tone}`}>
        <NextIcon />
        <span>
          <em>{next.label}</em>
          {next.value}
          {next.detail && <small>{next.detail}</small>}
        </span>
      </div>

      {c.notes && <span className="meta meta-clamp" title={c.notes}><NoteIcon />{c.notes}</span>}

      {linked.length > 0 && (
        <div className="contact-apps">
          {linked.slice(0, 2).map((a) => (
            <button key={a.id} className="app-chip" title={`${a.company} — ${a.role}`} onClick={(e) => { e.stopPropagation(); onOpenApp(a); }}>
              <Logo src={a.logo} company={a.company} size={18} />
              <span>{a.company}</span>
            </button>
          ))}
          {linked.length > 2 && <span className="app-chip app-chip-more">+{linked.length - 2}</span>}
        </div>
      )}
      {doors > 0 && <div className="card-network"><span>Could open doors at <b>{doors} {doors === 1 ? "row" : "rows"}</b></span></div>}

      {latest && (
        <div className="card-block">
          <h4>Latest</h4>
          <p className="latest"><time>{formatDate(latest.date, false)}</time> {latest.text}</p>
        </div>
      )}

      {c.how_met && <span className="meta how-met"><LinkIcon />{c.how_met}</span>}
      <button className="card-collapse" onClick={(e) => { e.stopPropagation(); onOpen(c); }}>Open full card ↗</button>
    </article>
  );
}
