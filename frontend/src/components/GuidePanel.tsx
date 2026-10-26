import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { askGuide, fetchSetup, type ChatMessage, type SetupStatus, type TraceStep, type Usage } from "../api";
import AgentTrace, { UsageLine } from "./AgentTrace";

const STORE = "guide-chat";
const SUGGESTIONS = [
  "What should I connect first?",
  "Which channels update on their own, and which need an export?",
  "How do I bring in WhatsApp?",
  "Auto-sync says it needs Full Disk Access: what do I do?",
];
const STEP_NAMES: Record<string, string> = {
  profile: "Profile", targets: "Targets", connector_key: "Connector key", gmail: "Gmail", messages: "Messages",
  whatsapp: "WhatsApp", linkedin: "LinkedIn", auto_sync: "Auto-sync",
};

type Turn = ChatMessage & { usage?: Usage; seconds?: number; trace?: TraceStep[] };

/** Step 1 of a new account: the Setup guide agent walks the student through every channel, one step at a time,
 *  next to a checklist worked out in code from what is already connected. */
export default function GuidePanel({ refreshKey = 0 }: { refreshKey?: number }) {
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [turns, setTurns] = useState<Turn[]>(() => JSON.parse(sessionStorage.getItem(STORE) || "[]"));
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchSetup().then(setSetup).catch(() => {});
  }, [refreshKey, turns.length]);
  useEffect(() => {
    sessionStorage.setItem(STORE, JSON.stringify(turns));
  }, [turns]);
  useEffect(() => {
    if (turns.length) endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns, busy]);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    const next = [...turns, { role: "user" as const, content: q }];
    setTurns(next);
    setDraft("");
    setError(null);
    setBusy(true);
    try {
      const r = await askGuide(next.map(({ role, content }) => ({ role, content })));
      if (!r.answer) throw new Error("The guide could not answer this time. Try again.");
      setTurns([...next, { role: "assistant", content: r.answer, usage: r.usage, seconds: r.seconds, trace: r.trace }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The guide could not answer.");
    } finally {
      setBusy(false);
    }
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(draft);
    }
  };
  const allSteps = Object.keys(STEP_NAMES);

  return (
    <section className="panel guide-agent" aria-label="Setup guide">
      <header className="panel-head">
        <div>
          <h2>Step 1 · Your Setup guide</h2>
          <p>An agent that walks you through bringing every channel in, one step at a time. It checks what is already connected; it can't click,
            read your accounts or send anything.</p>
        </div>
      </header>
      {setup && (
        <div className="setup-progress">
          <ol>
            {allSteps.map((k) => (
              <li key={k} className={setup.done.includes(k) ? "is-done" : setup.next?.key === k ? "is-next" : ""}>
                <span>{setup.done.includes(k) ? "✓" : allSteps.indexOf(k) + 1}</span>{STEP_NAMES[k]}
              </li>
            ))}
          </ol>
          <p className="setup-next">{setup.next ? <><b>Next:</b> {setup.next.what}</> : <b>All set: everything is connected.</b>}</p>
        </div>
      )}
      <div className="guide-chat">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "assistant" ? "chat-a" : "chat-q"}>
            {t.role === "assistant" ? <Markdown remarkPlugins={[remarkGfm]} disallowedElements={["img"]} unwrapDisallowed
              components={{ a: (p) => <a {...p} target="_blank" rel="noopener noreferrer" /> }}>{t.content}</Markdown> : <p>{t.content}</p>}
            {t.trace && (
              <details className="how-decided">
                <summary>What the guide did</summary>
                <AgentTrace trace={t.trace} onOpenRecord={() => {}} />
              </details>
            )}
            {t.usage && <UsageLine usage={t.usage} seconds={t.seconds ?? 0} />}
          </div>
        ))}
        {busy && <p className="chat-wait">The Setup guide is checking your setup…</p>}
        {error && <p className="inline-error">{error}</p>}
        <div ref={endRef} />
      </div>
      {turns.length === 0 && (
        <div className="chat-suggestions guide-suggestions">
          {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
        </div>
      )}
      <div className="guide-input">
        <textarea rows={2} value={draft} placeholder="Ask the Setup guide… (Enter to send)" onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} />
        <button className="primary-btn" disabled={busy || !draft.trim()} onClick={() => send(draft)}>{busy ? "Thinking…" : "Ask"}</button>
        {turns.length > 0 && <button className="toggle" onClick={() => setTurns([])}>Clear</button>}
      </div>
    </section>
  );
}
