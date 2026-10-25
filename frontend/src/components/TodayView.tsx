import { useEffect, useRef, useState, type ChangeEvent } from "react";
import {
  ApiError, fetchLatestPlan, fetchSamples, runIntake, runIntakeLink, runPlan,
  type Candidate, type CoachPlan, type IntakeResult, type Sample, type TraceStep, type Usage,
} from "../api";
import { formatDate } from "../format";
import AgentTrace, { AGENTS, UsageLine } from "./AgentTrace";

type PlanView = CoachPlan & { run_id: string; usage: Usage; seconds: number; trace: TraceStep[]; created_at?: string };

const PLAN_STAGES = [
  "The Career strategist is reading your candidate actions…",
  "Asking the Opportunity scout and Network intelligence…",
  "The specialists are searching your records…",
  "Ranking where your time matters most this week…",
];
const INTAKE_STAGES = ["The shield is checking the text…", "A specialist is reading it…", "Checking every quote against your text…"];

const errorText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);
const MAX_PASTE = 20_000;
const MAX_EXPORT = 400_000; // a LinkedIn connections export: filtered in code before the AI reads it
const asLink = (t: string) => (/^https?:\/\/\S+$/i.test(t.trim()) ? t.trim() : null);
const isLinkedInExport = (t: string) => /^\s*first name\s*,\s*last name\s*,/im.test(t.slice(0, 3000));

function useStaged(active: boolean, stages: string[]) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (!active) {
      setI(0);
      return;
    }
    const t = setInterval(() => setI((x) => Math.min(x + 1, stages.length - 1)), 4500);
    return () => clearInterval(t);
  }, [active, stages.length]);
  return stages[i];
}

const RecordChips = ({ ids, onOpen }: { ids: string[]; onOpen: (id: string) => void }) =>
  ids.length ? (
    <span className="record-chips">
      {ids.map((id) => <button key={id} className="record-chip" onClick={() => onOpen(id)} title="Open this record">{id}</button>)}
    </span>
  ) : null;

const TARGETS_TEMPLATE = `My target list for next summer (organisation — role — deadline or status — city):
1. 
2. 
3. 
4. 
5. `;

/** The coach's home: this week's ranked plan (Career strategist) and "Add what's new" (the two specialists).
 *  New accounts first see a three-step guide: profile, targets, people. */
export default function TodayView({ candidates, onOpenRecord, onChanged, onAsk, firstName, counts, profileFilled, onOpenProfile }: {
  candidates: Candidate[];
  onOpenRecord: (id: string) => void;
  onChanged: () => Promise<void> | void;
  onAsk: (q: string) => void;
  firstName: string;
  counts: { opportunities: number; people: number };
  profileFilled: boolean;
  onOpenProfile: () => void;
}) {
  const [plan, setPlan] = useState<PlanView | null>(null);
  const [planBusy, setPlanBusy] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const planStage = useStaged(planBusy, PLAN_STAGES);

  const [samples, setSamples] = useState<Sample[]>([]);
  const [text, setText] = useState("");
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<"auto" | "opportunity" | "conversation">("auto");
  const [intakeBusy, setIntakeBusy] = useState(false);
  const [intake, setIntake] = useState<IntakeResult | null>(null);
  const [intakeError, setIntakeError] = useState<string | null>(null);
  const intakeStage = useStaged(intakeBusy, INTAKE_STAGES);
  const fileRef = useRef<HTMLInputElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const [guideHidden, setGuideHidden] = useState(() => localStorage.getItem("coach-guide-hidden") === "1");
  const steps = [
    { done: profileFilled, title: "Tell the coach about you", text: "Background, target roles and industries, cities, languages. The agents judge fit and prepare calls against it.",
      action: "Write your profile", onClick: onOpenProfile },
    { done: counts.opportunities > 0, title: "Add your targets", text: "Paste your target list (one line per organisation and role), or a posting or careers-page link.",
      action: "Use a target-list template", onClick: () => { setText(TARGETS_TEMPLATE); setLabel("My target list"); setKind("opportunity"); textRef.current?.focus(); } },
    { done: counts.people > 0, title: "Add your people", text: "Paste a recent email or chat with a contact, your coffee-chat notes, or upload LinkedIn's Connections.csv.",
      action: "Upload a file", onClick: () => fileRef.current?.click() },
  ];
  const doneCount = steps.filter((x) => x.done).length;
  const showGuide = !guideHidden && doneCount < steps.length;

  useEffect(() => {
    fetchLatestPlan().then((r) => r.plan && setPlan(r.plan)).catch(() => {});
    fetchSamples().then((r) => setSamples(r.samples)).catch(() => {});
  }, []);

  async function makePlan() {
    setPlanBusy(true);
    setPlanError(null);
    try {
      const r = await runPlan(candidates.slice(0, 60));
      if (!r.plan) throw new ApiError(500, r.status === "model_rejected" ? "A different model answered, so the plan was rejected." : "The coach could not make a plan this time. Try again.");
      setPlan({ ...r.plan, run_id: r.run_id, usage: r.usage, seconds: r.seconds, trace: r.trace, created_at: new Date().toISOString() });
    } catch (e) {
      setPlanError(errorText(e, "The coach could not make a plan. Try again."));
    } finally {
      setPlanBusy(false);
    }
  }

  const link = asLink(text);

  async function addIntake() {
    if (text.length > MAX_PASTE && !isLinkedInExport(text)) {
      setIntakeError(`That's ${text.length.toLocaleString()} characters. Paste at most ${MAX_PASTE.toLocaleString()} at a time (LinkedIn exports can be longer).`);
      return;
    }
    setIntakeBusy(true);
    setIntakeError(null);
    setIntake(null);
    try {
      const r = link ? await runIntakeLink(link, kind) : await runIntake(text, kind, label || "Pasted text");
      setIntake(r);
      await onChanged();
    } catch (e) {
      setIntakeError(errorText(e, "That didn't go through. Try again."));
    } finally {
      setIntakeBusy(false);
    }
  }

  function pickSample(s: Sample) {
    setText(s.text);
    setLabel(s.title);
    setKind(s.kind);
    setIntake(null);
    setIntakeError(null);
  }

  function onFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 1_000_000) {
      setIntakeError("That file is too large. Paste the relevant part instead.");
      return;
    }
    f.text().then((t) => {
      const exportFile = isLinkedInExport(t);
      setText(t.slice(0, exportFile ? MAX_EXPORT : MAX_PASTE));
      setLabel(f.name);
      setIntake(null);
      setIntakeError(!exportFile && t.length > MAX_PASTE ? `Only the first ${MAX_PASTE.toLocaleString()} characters were kept.` : null);
    });
    e.target.value = "";
  }

  const saved = intake?.saved ?? {};
  const savedItems = [
    ...(saved.opportunities_added ?? []).map((o) => ({ id: `OPP-${o.id}`, text: `${o.company} — ${o.role}`, tag: "New opportunity" })),
    ...(saved.opportunities_updated ?? []).map((o) => ({ id: `OPP-${o.id}`, text: `${o.company} — ${o.role}`, tag: "Updated" })),
    ...(saved.contacts_added ?? []).map((c) => ({ id: `CON-${c.id}`, text: c.name, tag: "New person" })),
    ...(saved.contacts_updated ?? []).map((c) => ({ id: `CON-${c.id}`, text: c.name, tag: "Updated" })),
  ];
  const shieldCount = (intake?.flagged.length ?? 0) + (intake?.hidden.length ?? 0) + (intake?.rejected.length ?? 0);

  return (
    <main className="today">
      <section className="team-strip" aria-label="Your coaching team">
        {(["strategist", "scout", "network"] as const).map((k) => (
          <div key={k} className={`team-card ${AGENTS[k].tone}`}>
            <b>{AGENTS[k].name}</b>
            <span>{AGENTS[k].role}</span>
          </div>
        ))}
        <div className="team-card team-model"><b>gpt-6-luna</b><span>Never sends anything for you</span></div>
      </section>

      {showGuide && (
        <section className="panel guide" aria-label="Get started">
          <header className="panel-head">
            <div>
              <h2>Get started · {doneCount} of 3 done</h2>
              <p>Three quick steps, then the coach can plan your week. Nothing is ever sent on your behalf.</p>
            </div>
            <button className="toggle" onClick={() => { localStorage.setItem("coach-guide-hidden", "1"); setGuideHidden(true); }}>Hide</button>
          </header>
          <ol className="guide-steps">
            {steps.map((st, i) => (
              <li key={st.title} className={st.done ? "is-done" : ""}>
                <span className="guide-num">{st.done ? "✓" : i + 1}</span>
                <div><b>{st.title}</b><p>{st.text}</p></div>
                {!st.done && <button className="toggle" onClick={st.onClick}>{st.action}</button>}
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="today-grid">
        <section className="panel coach-panel">
          <header className="panel-head">
            <div>
              <h2>{firstName ? `Your week, ${firstName}` : "Your week"}</h2>
              <p>The Career strategist ranks your {candidates.length} open actions after consulting both specialists.</p>
            </div>
            <button className="primary-btn" onClick={makePlan} disabled={planBusy || candidates.length === 0}>
              {planBusy ? "Planning…" : plan ? "Re-plan my week" : "Plan my week"}
            </button>
          </header>

          {planBusy && <div className="working"><span className="pulse" />{planStage}</div>}
          {planError && <div className="inline-error" role="alert">{planError}</div>}

          {!plan && !planBusy && (
            <div className="empty-state">
              {candidates.length === 0 ? (
                <p><b>Nothing to rank yet.</b> Add your targets and a few conversations on the right: the coach turns them into open actions (deadlines, follow-ups, calls) and then plans your week.</p>
              ) : (
                <p><b>Not sure where to spend your time?</b> Press <em>Plan my week</em>. The coach looks at every deadline, fit and relationship, then picks the 3–5 moves worth your week, each with why now and the first step.</p>
              )}
            </div>
          )}

          {plan && (
            <div className={`plan${planBusy ? " is-stale" : ""}`}>
              <p className="plan-headline">{plan.headline}</p>
              <ol className="plan-actions">
                {plan.top_actions.map((a, i) => (
                  <li key={a.key} className="plan-action">
                    <span className="plan-rank">{i + 1}</span>
                    <div>
                      <div className="plan-title">
                        <b>{a.title}</b>
                        {a.due && <span className="due-chip">{formatDate(a.due, false)}</span>}
                      </div>
                      {a.subtitle && <p className="plan-sub">{a.subtitle}</p>}
                      <p><span className="plan-label">Why now</span>{a.why_now}</p>
                      <p><span className="plan-label">First step</span>{a.how}</p>
                      <RecordChips ids={a.record_ids} onOpen={onOpenRecord} />
                    </div>
                  </li>
                ))}
              </ol>
              {(plan.watch_outs.length > 0 || plan.open_questions.length > 0) && (
                <div className="plan-notes">
                  {plan.watch_outs.length > 0 && (
                    <div><h4>Watch out</h4><ul>{plan.watch_outs.map((w) => <li key={w}>{w}</li>)}</ul></div>
                  )}
                  {plan.open_questions.length > 0 && (
                    <div><h4>Only you can answer</h4><ul>{plan.open_questions.map((q) => <li key={q}><button className="link-btn" onClick={() => onAsk(q)}>{q}</button></li>)}</ul></div>
                  )}
                </div>
              )}
              <details className="how-decided">
                <summary>How the coach decided · run {plan.run_id}</summary>
                <AgentTrace trace={plan.trace} onOpenRecord={onOpenRecord} />
              </details>
              <UsageLine usage={plan.usage} seconds={plan.seconds} />
            </div>
          )}
        </section>

        <section className="panel intake-panel">
          <header className="panel-head">
            <div>
              <h2>Add what's new</h2>
              <p>Paste an email, a chat export, a job posting or your LinkedIn CSV. Nothing is stored except facts backed by a quote from it.</p>
            </div>
          </header>
          {samples.length > 0 && (
            <div className="samples">
              <span className="samples-label">Try a sample</span>
              {samples.map((s) => (
                <button key={s.id} className={`sample-chip${s.attack ? " is-attack" : ""}`} onClick={() => pickSample(s)} title={s.description}>
                  {s.attack && "⚠ "}{s.title}
                </button>
              ))}
            </div>
          )}
          <textarea
            ref={textRef}
            className="intake-text"
            rows={9}
            value={text}
            maxLength={MAX_EXPORT}
            placeholder="Paste here… a recruiter's reply, a WhatsApp chat about an intro, a posting, or just a link to a careers page."
            onChange={(e) => setText(e.target.value)}
          />
          <div className="intake-bar">
            <div className="segmented" role="group" aria-label="What is it?">
              {(["auto", "opportunity", "conversation"] as const).map((k) => (
                <button key={k} className={kind === k ? "is-active" : ""} onClick={() => setKind(k)}>
                  {{ auto: "Auto", opportunity: "Opportunity", conversation: "Conversation" }[k]}
                </button>
              ))}
            </div>
            <button className="toggle" onClick={() => fileRef.current?.click()}>Upload a file</button>
            <input ref={fileRef} type="file" accept=".txt,.csv,.eml,.html,.htm,.md" hidden onChange={onFile} />
            <span className="char-count">
              {link ? "A link · the coach reads the page itself" : isLinkedInExport(text) ? "LinkedIn export · filtered to your organisations first" : `${text.length.toLocaleString()} / ${MAX_PASTE.toLocaleString()}`}
            </span>
            <button className="primary-btn" onClick={addIntake} disabled={intakeBusy || (!link && text.trim().length < 20)}>
              {intakeBusy ? "Reading…" : link ? "Read this page" : "Add to my coach"}
            </button>
          </div>
          {intakeBusy && <div className="working"><span className="pulse" />{intakeStage}</div>}
          {intakeError && <div className="inline-error" role="alert">{intakeError}</div>}

          {intake && (
            <div className="intake-result">
              <p className="intake-summary">
                <b>{savedItems.length ? `${savedItems.length} record${savedItems.length > 1 ? "s" : ""} saved` : "Nothing new saved"}</b>
                {(saved.events_added ?? 0) > 0 && ` · ${saved.events_added} dated facts`}
                {(saved.leads_added ?? 0) > 0 && ` · ${saved.leads_added} leads`}
                {` · read by ${intake.routes.map((r) => AGENTS[r]?.name ?? r).join(" + ")}`}
              </p>
              {shieldCount > 0 && (
                <div className="shield-box">
                  <h4>🛡 Shield stopped {shieldCount} thing{shieldCount > 1 ? "s" : ""}</h4>
                  {intake.hidden.map((h, i) => <p key={`h${i}`}><b>Hidden text removed:</b> “{h}”</p>)}
                  {intake.flagged.map((l) => <p key={`f${l.line}`}><b>Instruction to an AI removed (line {l.line}):</b> “{l.text}”</p>)}
                  {intake.rejected.map((r, i) => <p key={`r${i}`}><b>Not saved: {r.item}</b> — {r.reason}</p>)}
                </div>
              )}
              {savedItems.length > 0 && (
                <ul className="saved-list">
                  {savedItems.map((s) => (
                    <li key={s.id + s.tag}>
                      <span className="saved-tag">{s.tag}</span>
                      <button className="link-btn" onClick={() => onOpenRecord(s.id)}>{s.text}</button>
                    </li>
                  ))}
                </ul>
              )}
              {intake.fields_not_found.length > 0 && (
                <div className="not-found"><h4>Not stated in the text</h4><ul>{intake.fields_not_found.map((f) => <li key={f}>{f}</li>)}</ul></div>
              )}
              <details className="how-decided">
                <summary>What the agents did · run {intake.run_id}</summary>
                <AgentTrace trace={intake.trace} onOpenRecord={onOpenRecord} />
              </details>
              <UsageLine usage={intake.usage} seconds={intake.seconds} />
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
