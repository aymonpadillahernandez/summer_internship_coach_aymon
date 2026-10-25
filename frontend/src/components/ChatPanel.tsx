import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { askCoach, type Candidate, type ChatMessage, type TraceStep, type Usage } from "../api";
import AgentTrace, { AGENTS, UsageLine } from "./AgentTrace";
import { CloseIcon } from "./Icons";

const STORE = "coach-chat";
const SUGGESTIONS = [
  "Which of my target organisations have no contact yet, and who in my network could help?",
  "Which deadlines close in the next two weeks, and am I ready for them?",
  "Who is waiting on me right now?",
  "Prepare my next call",
];

type Turn = ChatMessage & { agent?: string | null; usage?: Usage; seconds?: number; trace?: TraceStep[]; runId?: string };

/** "Ask your coach": the Career strategist answers from your records, consulting the specialists when it needs them.
 *  Call-prep questions go straight to Network intelligence (routed in code). seed: a question to send on open. */
export default function ChatPanel({ onClose, seed, candidates, onOpenRecord }: {
  onClose: () => void;
  seed?: string;
  candidates: Candidate[];
  onOpenRecord: (id: string) => void;
}) {
  const [turns, setTurns] = useState<Turn[]>(() => JSON.parse(sessionStorage.getItem(STORE) || "[]"));
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Block bodies: an effect must return nothing (Chrome's scrollIntoView now returns a Promise).
  useEffect(() => {
    sessionStorage.setItem(STORE, JSON.stringify(turns));
  }, [turns]);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy, error]);
  useEffect(() => {
    inputRef.current?.focus();
    const onKey = (e: globalThis.KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const send = async (text: string, history: Turn[] = turns) => {
    const question = text.trim();
    if (!question || busy) return;
    const next = [...history, { role: "user" as const, content: question }];
    setTurns(next);
    setDraft("");
    setError(null);
    setBusy(true);
    try {
      const r = await askCoach(next.map(({ role, content }) => ({ role, content })), candidates.slice(0, 20));
      if (!r.answer) throw new Error(r.status === "model_rejected" ? "A different model answered, so the reply was rejected." : "The coach could not answer this time.");
      setTurns([...next, { role: "assistant", content: r.answer, agent: r.agent, usage: r.usage, seconds: r.seconds, trace: r.trace, runId: r.run_id }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The coach could not answer.");
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  // A question handed over by a card ("Prepare this call") is asked once, in a fresh chat.
  const seeded = useRef(false);
  useEffect(() => {
    if (seed && !seeded.current) {
      seeded.current = true;
      send(seed, []);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed]);

  // Try again: resend the last question without adding it twice.
  const retry = () => {
    const last = turns[turns.length - 1];
    if (last?.role === "user") send(last.content, turns.slice(0, -1));
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(draft);
    }
  };

  return (
    <div className="scrim chat-scrim" onClick={onClose}>
      <aside className="sheet chat" role="dialog" aria-label="Ask your coach" onClick={(e) => e.stopPropagation()}>
        <header className="chat-head">
          <div>
            <h2>Ask your coach</h2>
            <p>The Career strategist answers from your records and asks the specialists when needed.</p>
          </div>
          <div className="chat-head-actions">
            {turns.length > 0 && (
              <button className="chat-new" onClick={() => { setTurns([]); setError(null); }} disabled={busy}>New chat</button>
            )}
            <button className="icon-btn" onClick={onClose} aria-label="Close"><CloseIcon /></button>
          </div>
        </header>

        <div className="chat-log" aria-live="polite">
          {turns.length === 0 && (
            <div className="chat-empty">
              <p>Ask anything about your search. Answers cite the records they used (OPP- and CON- ids), and nothing is ever sent for you.</p>
              <div className="chat-suggestions">
                {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
              </div>
            </div>
          )}
          {turns.map((t, i) =>
            t.role === "user" ? (
              <div key={i} className="chat-q">{t.content}</div>
            ) : (
              <div key={i} className="chat-a">
                <Markdown remarkPlugins={[remarkGfm]} components={{ a: (p) => <a {...p} target="_blank" rel="noopener noreferrer" /> }}>
                  {t.content}
                </Markdown>
                {t.usage && (
                  <details className="chat-meta">
                    <summary>{t.agent === "network" ? "Network intelligence · call prep" : "Career strategist"} · gpt-6-luna · {(t.usage.input + t.usage.output).toLocaleString()} tokens</summary>
                    {t.trace && <AgentTrace trace={t.trace} onOpenRecord={onOpenRecord} />}
                    <UsageLine usage={t.usage} seconds={t.seconds} />
                  </details>
                )}
              </div>
            ),
          )}
          {busy && <div className="chat-a chat-thinking" aria-label="Thinking"><span /><span /><span /></div>}
          {busy && <p className="chat-wait">{AGENTS.strategist.name} is on it; specialist questions take 10–20 s.</p>}
          {error && (
            <div className="chat-error" role="alert">
              {error} <button onClick={retry}>Try again</button>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(draft); }}>
          <textarea
            ref={inputRef}
            rows={1}
            value={draft}
            placeholder="Ask a question…"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            maxLength={2000}
          />
          <button type="submit" disabled={busy || !draft.trim()} aria-label="Send">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M12 19V5M5 12l7-7 7 7" /></svg>
          </button>
        </form>
      </aside>
    </div>
  );
}
