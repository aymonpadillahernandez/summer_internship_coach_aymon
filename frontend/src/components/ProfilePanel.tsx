import { useEffect, useRef, useState } from "react";
import { deleteAccount, fetchProfile, saveProfile, type User } from "../api";
import { CloseIcon } from "./Icons";

/** The student's own profile (used by the strategist and call prep), and "delete my account and data". */
export default function ProfilePanel({ user, onClose, onDeleted, onSaved }: {
  user: User;
  onClose: () => void;
  onDeleted: () => void;
  onSaved?: () => void;
}) {
  const [text, setText] = useState("");
  const [loaded, setLoaded] = useState(false); // typing waits for the saved profile, so it can't overwrite what you typed
  const [saved, setSaved] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load once: the parent passes a new onClose on every render, which must not trigger a reload (it reset typed text).
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    fetchProfile().then((r) => setText(r.text)).catch(() => {}).finally(() => setLoaded(true));
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeRef.current();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const save = () =>
    saveProfile(text).then(() => { setSaved("Saved. The coach uses it from your next run."); onSaved?.(); }).catch(() => setError("Couldn't save. Try again."));
  const remove = () => deleteAccount().then(onDeleted).catch(() => setError("Couldn't delete. Try again."));

  return (
    <div className="scrim" onClick={onClose}>
      <aside className="sheet profile-sheet" role="dialog" aria-label="Your profile" onClick={(e) => e.stopPropagation()}>
        <header className="sheet-head">
          <div>
            <h2>Your profile</h2>
            <p>{user.is_demo ? "Demo account · fictional student" : user.email}</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><CloseIcon /></button>
        </header>
        <section className="sheet-section">
          <h4>What the coach should know about you</h4>
          <p className="muted small">Background, target roles and industries, locations, languages, timing. The agents judge fit and prepare calls against it.</p>
          <textarea className="profile-text" rows={8} maxLength={2000} value={text} disabled={!loaded} placeholder={loaded ? "e.g. First-year MBA, ex-consultant, targeting strategy roles in sports and media in New York; speaks English and Spanish." : "Loading…"} onChange={(e) => { setText(e.target.value); setSaved(null); }} />
          <div className="profile-actions">
            <button className="primary-btn" onClick={save} disabled={!loaded}>Save profile</button>
            {saved && <span className="muted small">{saved}</span>}
          </div>
        </section>
        <section className="sheet-section danger-zone">
          <h4>Your data</h4>
          <p className="muted small">The pasted texts themselves are never stored, only the facts and the quotes that back them. Deleting removes your account, every record, every run and every token log.</p>
          {!confirming ? (
            <button className="danger-btn" onClick={() => setConfirming(true)}>Delete my account and data</button>
          ) : (
            <div className="profile-actions">
              <button className="danger-btn" onClick={remove}>Yes, delete everything</button>
              <button className="toggle" onClick={() => setConfirming(false)}>Cancel</button>
            </div>
          )}
          {error && <p className="inline-error">{error}</p>}
        </section>
      </aside>
    </div>
  );
}
