import { useState } from "react";
import { ApiError, savePrefs, type Prefs } from "../api";

const INDUSTRIES = ["Consulting", "Investment banking", "Private equity / VC", "Tech", "Sports", "Media & entertainment",
  "Consumer brands", "Retail", "Healthcare", "Energy & climate", "Real estate", "Nonprofit / social impact"];
const ROLES = ["Strategy", "Business development", "Partnerships", "Product management", "Marketing / brand", "Finance",
  "Operations", "General management"];
const CITIES = ["New York", "Boston", "San Francisco", "Los Angeles", "Chicago", "Seattle", "Washington, DC", "London", "Remote"];
const EMPTY: Prefs = { school: "Yale SOM", timing: "Summer 2027", industries: [], roles: [], companies: [], cities: [], notes: "" };

function Chips({ options, value, onChange }: { options: string[]; value: string[]; onChange: (v: string[]) => void }) {
  const extra = value.filter((v) => !options.includes(v));
  return (
    <div className="pref-chips">
      {[...options, ...extra].map((o) => (
        <button key={o} type="button" className={`pref-chip${value.includes(o) ? " is-on" : ""}`}
          onClick={() => onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o])}>{o}</button>
      ))}
    </div>
  );
}

function AddOther({ onAdd, placeholder }: { onAdd: (v: string) => void; placeholder: string }) {
  const [v, setV] = useState("");
  const add = () => { if (v.trim()) { onAdd(v.trim()); setV(""); } };
  return (
    <div className="pref-other">
      <input value={v} placeholder={placeholder} onChange={(e) => setV(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} />
      <button type="button" className="toggle" onClick={add}>Add</button>
    </div>
  );
}

/** The first step of a new account: what the student wants this summer. It opens the profile every agent reads, and
 *  each target organisation goes straight onto the Opportunities board (no AI needed). Editable any time. */
export default function PreferencesForm({ initial, onSaved, onSkip, firstRun = false }: {
  initial: Prefs | null;
  onSaved: (added: string[]) => void;
  onSkip?: () => void;
  firstRun?: boolean;
}) {
  const [p, setP] = useState<Prefs>(initial ?? EMPTY);
  const [companies, setCompanies] = useState((initial?.companies ?? []).join("\n"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof Prefs) => (v: string[] | string) => setP((x) => ({ ...x, [k]: v }));

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const r = await savePrefs({ ...p, companies: companies.split(/[\n,;]+/).map((c) => c.trim()).filter(Boolean) });
      onSaved(r.added);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't save. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel prefs-form" aria-label="Your internship preferences">
      <header className="panel-head">
        <div>
          <h2>{firstRun ? "Welcome! What are you looking for this summer?" : "Your internship preferences"}</h2>
          <p>Two minutes. Every agent uses this: the scout searches the web for roles that fit, Network intelligence looks for people
            (and alumni of your school) at your target organisations, and the coach plans your week around it.</p>
        </div>
      </header>
      <div className="pref-grid">
        <label><span>School</span><input value={p.school} maxLength={120} onChange={(e) => set("school")(e.target.value)} /></label>
        <label><span>Internship</span><input value={p.timing} maxLength={60} onChange={(e) => set("timing")(e.target.value)} /></label>
      </div>
      <div className="pref-block"><b>Industries</b><Chips options={INDUSTRIES} value={p.industries} onChange={set("industries")} />
        <AddOther placeholder="Another industry" onAdd={(v) => set("industries")([...p.industries, v])} /></div>
      <div className="pref-block"><b>Roles</b><Chips options={ROLES} value={p.roles} onChange={set("roles")} />
        <AddOther placeholder="Another role" onAdd={(v) => set("roles")([...p.roles, v])} /></div>
      <div className="pref-block"><b>Cities</b><Chips options={CITIES} value={p.cities} onChange={set("cities")} />
        <AddOther placeholder="Another city" onAdd={(v) => set("cities")([...p.cities, v])} /></div>
      <div className="pref-block"><b>Target companies and organisations</b> <span className="muted small">one per line; each becomes a card on your board</span>
        <textarea rows={4} value={companies} maxLength={4000} placeholder={"e.g.\nNBA\nDisney\nMcKinsey & Company"} onChange={(e) => setCompanies(e.target.value)} /></div>
      <div className="pref-block"><b>Anything else</b> <span className="muted small">languages, visa, goals, deal-breakers</span>
        <textarea rows={2} value={p.notes} maxLength={1000} onChange={(e) => set("notes")(e.target.value)} /></div>
      {error && <p className="inline-error">{error}</p>}
      <div className="pref-actions">
        <button className="primary-btn" disabled={busy} onClick={save}>{busy ? "Saving…" : firstRun ? "Save and set up my channels" : "Save preferences"}</button>
        {onSkip && <button className="toggle" onClick={onSkip}>{firstRun ? "Skip for now" : "Cancel"}</button>}
      </div>
    </section>
  );
}
