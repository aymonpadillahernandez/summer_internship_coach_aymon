import { useEffect, useState, type FormEvent } from "react";
import { ApiError, fetchAuthOptions, signIn, signUp, startDemo, type User } from "../api";

const message = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Try again.");

const PROMISES = [
  { title: "One picture of your search", text: "Paste emails, chats, postings or your LinkedIn export. The agents file opportunities, people and dated facts, each with its quote." },
  { title: "Where to spend this week", text: "The Career strategist asks the Opportunity scout and Network intelligence, then ranks your next best actions." },
  { title: "Safe by design", text: "Nothing is ever sent for you. Instructions hidden in pasted text are caught, and every fact must match its source." },
];

/** Sign in, create an account, or try the demo (a private sandbox with a fictional student's data). */
export function SignIn({ onSignedIn }: { onSignedIn: (u: User) => void }) {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"form" | "demo" | null>(null);

  useEffect(() => {
    fetchAuthOptions().then((o) => setNeedsCode(o.signup_code_required)).catch(() => {});
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy("form");
    setError(null);
    try {
      const r = mode === "signin" ? await signIn(email, password) : await signUp(email, name, password, code);
      onSignedIn(r.user);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(null);
    }
  }

  async function demo() {
    setBusy("demo");
    setError(null);
    try {
      onSignedIn((await startDemo()).user);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="auth-page landing">
      <section className="landing-hero">
        <img src="/favicon.svg" alt="" width={56} height={56} />
        <h1>Summer Internship Coach</h1>
        <p className="landing-pitch">From scattered opportunities and conversations to the next best career action.</p>
        <ul className="landing-points">
          {PROMISES.map((p) => (
            <li key={p.title}><b>{p.title}</b><span>{p.text}</span></li>
          ))}
        </ul>
      </section>
      <div className="auth-card">
        <button className="auth-button demo-button" onClick={demo} disabled={busy !== null}>
          {busy === "demo" ? "Setting up your demo…" : "Try the demo"}
        </button>
        <p className="auth-foot">A private sandbox with a fictional MBA student's search. Deleted after 3 days.</p>
        <div className="auth-divider"><span>or</span></div>
        <div className="segmented auth-switch" role="tablist">
          <button role="tab" aria-selected={mode === "signin"} className={mode === "signin" ? "is-active" : ""} onClick={() => setMode("signin")}>Sign in</button>
          <button role="tab" aria-selected={mode === "signup"} className={mode === "signup" ? "is-active" : ""} onClick={() => setMode("signup")}>Create account</button>
        </div>
        <form className="auth-form" onSubmit={submit}>
          {mode === "signup" && <label>Your name<input autoComplete="name" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} /></label>}
          <label>Email<input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>Password {mode === "signup" && <small>(at least 8 characters)</small>}
            <input type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} required minLength={mode === "signup" ? 8 : undefined} value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          {mode === "signup" && needsCode && <label>Sign-up code<input required value={code} onChange={(e) => setCode(e.target.value)} /></label>}
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="auth-button" disabled={busy !== null}>
            {busy === "form" ? "One moment…" : mode === "signin" ? "Sign in" : "Create account"}
          </button>
        </form>
      </div>
    </div>
  );
}
