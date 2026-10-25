import type { CSSProperties } from "react";
import type { Action, Bucket } from "../actions";
import { BUCKETS, bucketOf, sortActions } from "../actions";
import { initials } from "../format";
import { CheckIcon } from "./Icons";
import Logo from "./Logo";

const KIND: Record<Action["kind"], string> = {
  apply: "Apply", prepare: "Get ready", recheck: "Recheck", interview: "Interview", find: "Find a contact",
  reach: "Reach out", nudge: "Nudge", schedule: "Schedule", call: "Meet", next: "Next step", checkin: "Keep warm", event: "Event", review: "Review", check: "Check", followup: "Follow up",
};

type Props = {
  actions: Action[];
  onDone: (a: Action) => void;
  onOpen: (a: Action) => void;
  readOnly?: boolean;
};

function ActionCard({ a, bucket, onDone, onOpen, readOnly }: { a: Action; bucket: Bucket } & Omit<Props, "actions">) {
  return (
    <article className={`action-card kind-${a.kind}`} tabIndex={0} onClick={() => onOpen(a)} onKeyDown={(e) => e.key === "Enter" && onOpen(a)}>
      {readOnly ? (
        <span className="tick tick-off" aria-hidden />
      ) : (
        <button className="tick" aria-label={`Mark "${a.title}" done`} title="Mark done" onClick={(e) => { e.stopPropagation(); onDone(a); }}>
          <CheckIcon />
        </button>
      )}
      <div className="action-main">
        <div className="action-top">
          <span className="action-kind">{KIND[a.kind]}</span>
          <span className={`due-chip due-${bucket}`} title={a.why}>{a.dueLabel}</span>
        </div>
        <h3>{a.title}</h3>
        <div className="action-sub">
          {a.contact ? (
            <span className="person-avatar action-avatar" aria-hidden>{initials(a.contact.name)}</span>
          ) : a.app ? (
            <Logo src={a.app.logo} company={a.app.company} size={18} />
          ) : a.apps ? (
            <span className="logo-stack">{a.apps.slice(0, 4).map((x) => <Logo key={x.id} src={x.logo} company={x.company} size={18} />)}</span>
          ) : null}
          <span>{a.subtitle}</span>
        </div>
      </div>
    </article>
  );
}

/** Pending actions in four time columns, derived in code from the student's records (zero tokens). */
export default function ActionPlan({ actions, onDone, onOpen, readOnly = false }: Props) {
  return (
    <div className="board action-board" style={{ "--cols": BUCKETS.length } as CSSProperties}>
      {BUCKETS.map((b) => {
        const list = actions.filter((a) => bucketOf(a) === b.key).sort(sortActions);
        return (
          <section key={b.key} className={`column bucket-${b.key}`}>
            <header className="column-head">
              <span className="dot" />
              <h2>{b.label}</h2>
              <span className="count">{list.length}</span>
            </header>
            <p className="column-hint">{b.hint}</p>
            <div className="column-body">
              {list.map((a) => <ActionCard key={a.key} a={a} bucket={b.key} onDone={onDone} onOpen={onOpen} readOnly={readOnly} />)}
              {list.length === 0 && <div className="empty">All clear</div>}
            </div>
          </section>
        );
      })}
    </div>
  );
}
