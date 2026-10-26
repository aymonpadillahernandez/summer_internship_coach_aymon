import { useEffect, useRef, useState, type ChangeEvent } from "react";
import {
  ApiError, createConnectorKey, fetchConnectorStatus, fileToBase64, revokeConnectorKey, runIntakeFile,
  type ConnectorKey, type ConnectorSync, type IntakeResult,
} from "../api";
import { formatDate } from "../format";
import { AGENTS } from "./AgentTrace";
import GuidePanel from "./GuidePanel";
import PreferencesForm from "./PreferencesForm";
import { fetchPrefs, type Prefs } from "../api";

type Result = { ok: boolean; text: string };

function summary(r: IntakeResult): string {
  const s = r.saved;
  const parts = [
    s.opportunities_added?.length && `${s.opportunities_added.length} new opportunities`,
    s.opportunities_updated?.length && `${s.opportunities_updated.length} updated`,
    s.contacts_added?.length && `${s.contacts_added.length} new people`,
    s.contacts_updated?.length && `${s.contacts_updated.length} people updated`,
    s.events_added && `${s.events_added} dated facts`,
    s.leads_added && `${s.leads_added} leads`,
  ].filter(Boolean);
  const shield = r.flagged.length + r.hidden.length + r.rejected.length;
  const who = r.routes.length ? ` · read by ${r.routes.map((x) => AGENTS[x]?.name ?? x).join(" + ")}` : "";
  return `${parts.length ? parts.join(", ") : "Nothing new"}${shield ? ` · shield stopped ${shield}` : ""}${who}`;
}

function CopyLine({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="code-line">
      <code>{text}</code>
      <button className="toggle" onClick={() => navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })}>
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

type Tone = "on" | "warn" | "manual" | "off";

/** What the last connector check says about one channel: auto-sync on, needs attention, synced by hand, or not connected. */
function syncState(s: ConnectorSync | undefined): { tone: Tone; text: string } {
  if (!s) return { tone: "off", text: "Not connected yet" };
  const at = new Date(`${s.synced_at.replace(" ", "T")}Z`);  // stored in UTC
  const when = at.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const minutes = (Date.now() - at.getTime()) / 60_000;
  if (!s.ok) return { tone: "warn", text: `${s.summary} · ${when}` };
  if (s.auto_minutes && minutes <= s.auto_minutes * 2 + 10) return { tone: "on", text: `Auto-sync on · last check ${when} · ${s.summary}` };
  if (s.auto_minutes) return { tone: "warn", text: `Auto-sync hasn't checked since ${when} (Mac asleep or off?)` };
  return { tone: "manual", text: `Synced by hand · ${when} · ${s.summary}` };
}

const AUTOMATIC: { id?: string; title: string; how: string }[] = [
  { id: "gmail", title: "Gmail", how: "Read with an app password, read-only; emails stay unread." },
  { title: "School email (Outlook)", how: "Forward it to that Gmail once (Outlook → Settings → Mail → Forwarding)." },
  { id: "imessage", title: "iMessage / SMS", how: "Messages on your Mac; iPhone texts too when they sync to the Mac." },
  { id: "whatsapp", title: "WhatsApp", how: "WhatsApp Desktop on your Mac, kept open in the background." },
];

const BY_HAND: { title: string; how: string }[] = [
  { title: "LinkedIn messages and connections", how: "Download your data → upload the CSVs. LinkedIn lets no app read messages." },
  { title: "Slack", how: "Copy and paste. School workspaces only allow apps their admins approve." },
  { title: "Android texts", how: "Copy the thread from Google Messages for web. Texts stay on the phone." },
  { title: "Calendar invites", how: "Upload the invite's .ics file." },
  { title: "WhatsApp without a Mac", how: "Export chat → upload the .zip." },
  { title: "Job postings", how: "Paste the link on Today; Handshake or LinkedIn Jobs: paste the text." },
];

type Channel = {
  id: string;
  title: string;
  steps: string[];
  accept?: string;
  kind?: "auto" | "opportunity" | "conversation";
  note?: string;
  samples?: { name: string; file: string }[];  // fictional exports, offered in demo accounts (graders, visitors)
};

const CHANNELS: Channel[] = [
  { id: "whatsapp", title: "WhatsApp without a Mac (Export chat)", kind: "conversation", accept: ".zip,.txt",
    samples: [{ name: "whatsapp", file: "WhatsApp Chat - Priya Shah.zip" }],
    steps: ["iPhone: open the chat → tap the name at the top → Export chat → Without media → Save to Files.",
      "Android: open the chat → ⋮ → More → Export chat → Without media.",
      "Upload the .zip here. One chat at a time: export only recruiting chats."],
    note: "On a Mac, the Coach Connector reads WhatsApp Desktop on its own instead (above). Export chat is WhatsApp's own, official way." },
  { id: "linkedin", title: "LinkedIn connections and messages", kind: "auto", accept: ".csv",
    samples: [{ name: "linkedin_connections", file: "Connections.csv" }, { name: "linkedin_messages", file: "messages.csv" }],
    steps: ["On a computer: Me → Settings & Privacy → Data privacy → Download your data.",
      "Pick Connections and Messages → Request archive (it arrives by email, usually within minutes).",
      "Upload Connections.csv and messages.csv here. Add your targets first: only people at your organisations, and conversations about them or recruiting, are kept."],
    note: "LinkedIn does not let other apps read your messages; its data download is the official route." },
  { id: "email", title: "Any email (Gmail, Outlook, school mail)", kind: "auto", accept: ".eml",
    samples: [{ name: "email", file: "Re Harborview partnerships internship.eml" }],
    steps: ["Gmail: open the email → ⋮ → Download message.",
      "Outlook: open the email → … → Save as (or drag it to your desktop).",
      "Upload the .eml here, or copy the text and paste it on Today. For automatic Gmail, use the Coach Connector above."] },
  { id: "imessage", title: "iMessage / SMS without the connector", kind: "conversation", accept: ".pdf,.txt",
    samples: [{ name: "imessage", file: "Messages - Luis Moreno.txt" }],
    steps: ["Short threads: select the messages, copy and paste them on Today.",
      "Long threads on a Mac: Messages → select the conversation → File → Print → PDF → Save as PDF.",
      "Upload the PDF here. Android: use Google Messages for web and copy the thread."] },
  { id: "slack", title: "Slack", steps: ["Open the DM or thread, select the messages, copy them.", "Paste them on Today."],
    note: "School Slack workspaces only let apps approved by their admins read messages, so copying is the free way in." },
  { id: "calendar", title: "Calendar invites (booked calls)", kind: "conversation", accept: ".ics",
    samples: [{ name: "calendar", file: "Coffee chat - Maya Chen.ics" }],
    steps: ["Open the invite email → download invite.ics (or export one event from your calendar).",
      "Upload it here: the Inbox organizer records the call with its date and the person."] },
  { id: "pages", title: "Careers pages and postings", steps: ["Paste the link on Today: the Opportunity scout reads the page itself, without hidden text.",
    "Handshake, LinkedIn Jobs or school career sites: copy the posting's text and paste it (their terms forbid automated reading)."] },
];

/** "Connect your channels": free ways to bring every channel in, automatic (Coach Connector) or by upload / paste. */
export default function ConnectView({ onChanged, onGoToday, isDemo = false }: { onChanged: () => Promise<void> | void; onGoToday: () => void; isDemo?: boolean }) {
  const [keys, setKeys] = useState<ConnectorKey[]>([]);
  const [syncs, setSyncs] = useState<ConnectorSync[]>([]);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, Result>>({});
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [editPrefs, setEditPrefs] = useState(false);
  const [prefsNote, setPrefsNote] = useState<string | null>(null);
  useEffect(() => {
    fetchPrefs().then((r) => setPrefs(r.prefs)).catch(() => {});
  }, [editPrefs]);
  const files = useRef<Record<string, HTMLInputElement | null>>({});
  const origin = window.location.origin;

  const load = () => fetchConnectorStatus().then((r) => { setKeys(r.keys); setSyncs(r.syncs); }).catch(() => {});
  useEffect(() => { load(); }, []);

  async function makeKey() {
    const r = await createConnectorKey("My computer");
    setNewKey(r.key);
    load();
  }

  async function upload(ch: Channel, e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy(ch.id);
    setResults((x) => ({ ...x, [ch.id]: { ok: true, text: `Reading ${f.name}…` } }));
    try {
      const r = await runIntakeFile(f.name, await fileToBase64(f), ch.kind ?? "auto");
      setResults((x) => ({ ...x, [ch.id]: { ok: true, text: `${f.name}: ${summary(r)}` } }));
      await onChanged();
    } catch (err) {
      setResults((x) => ({ ...x, [ch.id]: { ok: false, text: err instanceof ApiError ? err.message : "That upload didn't work. Try again." } }));
    } finally {
      setBusy(null);
    }
  }

  async function trySample(ch: Channel, s: { name: string; file: string }) {
    setBusy(ch.id);
    setResults((x) => ({ ...x, [ch.id]: { ok: true, text: `Reading the sample ${s.file}…` } }));
    try {
      const res = await fetch(`/api/demo-files/${s.name}`, { credentials: "same-origin" });
      if (!res.ok) throw new Error("The sample could not be loaded.");
      const file = new File([await res.blob()], s.file);
      const r = await runIntakeFile(s.file, await fileToBase64(file), ch.kind ?? "auto");
      setResults((x) => ({ ...x, [ch.id]: { ok: true, text: `Sample ${s.file}: ${summary(r)}` } }));
      await onChanged();
    } catch (err) {
      setResults((x) => ({ ...x, [ch.id]: { ok: false, text: err instanceof Error ? err.message : "That sample didn't work. Try again." } }));
    } finally {
      setBusy(null);
    }
  }

  const active = keys.filter((k) => !k.revoked_at);
  const syncOf = (c: string) => syncs.find((s) => s.channel === c);

  return (
    <main className="today connect">
      {editPrefs ? (
        <PreferencesForm initial={prefs} onSkip={() => setEditPrefs(false)}
          onSaved={async (added) => { setEditPrefs(false); setPrefsNote(added.length ? `Added to your board: ${added.join(", ")}.` : "Saved."); await onChanged(); }} />
      ) : (
        <section className="panel prefs-summary">
          <div>
            <h2>Your internship preferences</h2>
            {prefs ? (
              <p><b>{prefs.timing}</b>{prefs.school ? ` · ${prefs.school}` : ""} · {[...prefs.industries].join(", ") || "any industry"} · {prefs.roles.join(", ") || "any role"} · {prefs.cities.join(", ") || "any city"}
                {prefs.companies.length ? ` · ${prefs.companies.length} target organisations` : ""}</p>
            ) : <p>Not filled in yet: tell the coach what you want, and every agent works from it.</p>}
            {prefsNote && <p className="upload-ok">{prefsNote}</p>}
          </div>
          <button className="primary-btn" onClick={() => setEditPrefs(true)}>{prefs ? "Edit" : "Fill in (2 minutes)"}</button>
        </section>
      )}
      <GuidePanel refreshKey={syncs.length + keys.length} />
      <section className="panel connect-head">
        <h2>Connect your channels</h2>
        <p>Free, and read-only: the coach never sends anything from your accounts. Only what matches your search (your organisations,
          your people, recruiting topics) is shared, every fact keeps the quote it came from, and Profile → Delete removes everything.</p>
        {isDemo && (
          <div className="demo-tour">
            <b>Demo tour: every channel works here, with fictional data.</b>
            <ol>
              <li><b>Imports:</b> on each card below, <i>Try a sample file</i> runs the real import with a fictional export: a WhatsApp chat (.zip),
                LinkedIn connections and messages (.csv), an email (.eml), a calendar invite (.ics) and a Messages thread.</li>
              <li><b>The connector:</b> create a key (step 1), download the script (step 2), run setup with that key (press Enter to skip Gmail,
                n for Messages and WhatsApp), then <code>python3 ~/coach_connector.py demo</code>. It sends fictional Gmail, Messages and
                WhatsApp messages through the real connector path, and the Gmail, Messages and WhatsApp cards turn to synced. Your own accounts
                are never read.</li>
            </ol>
          </div>
        )}
        <div className="glance">
          <div className="glance-col is-auto">
            <h3>Updates on its own</h3>
            <p className="muted small">After a one-time setup on your Mac (Coach Connector, below): it checks every 30 minutes while
              the Mac is awake and sends only new messages that matter, with a little context.</p>
            <ul>
              {AUTOMATIC.map((c) => {
                const st = c.id ? syncState(syncOf(c.id)) : null;
                return (
                  <li key={c.title}>
                    <div><b>{c.title}</b><span>{c.how}</span></div>
                    {st && <span className={`sync-chip is-${st.tone}`}>{{ on: "On", warn: "Check", manual: "By hand", off: "Not yet" }[st.tone]}</span>}
                  </li>
                );
              })}
            </ul>
          </div>
          <div className="glance-col">
            <h3>Export or paste each time</h3>
            <p className="muted small">These apps don't let other apps read your messages, so you bring them in yourself (upload cards below).</p>
            <ul>
              {BY_HAND.map((c) => (
                <li key={c.title}><div><b>{c.title}</b><span>{c.how}</span></div></li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="panel">
        <header className="panel-head">
          <div>
            <h2>Automatic · Coach Connector</h2>
            <p>A small script on your own Mac. It reads your Gmail, Messages (iMessage / SMS) and WhatsApp Desktop read-only, filters
              them on your computer, and sends only the matches to your coach. Your passwords never leave your Mac.</p>
          </div>
        </header>
        <ol className="guide-steps connect-steps">
          <li>
            <span className="guide-num">1</span>
            <div>
              <b>Create your connector key</b>
              <p>It links the script to your account. It is shown once; you can revoke it here any time.</p>
              {newKey ? <CopyLine text={newKey} /> : <button className="primary-btn" onClick={makeKey}>Create a connector key</button>}
              {active.length > 0 && (
                <ul className="key-list">
                  {active.map((k) => (
                    <li key={k.id}>
                      Key #{k.id} · created {formatDate(k.created_at.slice(0, 10), false)} · {k.last_used_at ? `last used ${formatDate(k.last_used_at.slice(0, 10), false)}` : "not used yet"}
                      <button className="link-btn" onClick={() => revokeConnectorKey(k.id).then(load)}>Revoke</button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </li>
          <li>
            <span className="guide-num">2</span>
            <div>
              <b>Download and set it up</b>
              <p>Open Terminal (Applications → Utilities) and run these two lines. Setup asks for your key, then which channels to
                connect: Gmail (with an app password), Messages and WhatsApp Desktop.</p>
              <CopyLine text={`curl -fsSL ${origin}/connector/coach_connector.py -o ~/coach_connector.py`} />
              <CopyLine text="python3 ~/coach_connector.py setup" />
            </div>
          </li>
          <li>
            <span className="guide-num">3</span>
            <div>
              <b>Gmail: create an app password</b>
              <p>Google Account → Security → turn on 2-Step Verification → App passwords → create one called “Summer Internship Coach” and paste
                it into setup. School mail (e.g. Outlook): forward it to your personal Gmail (Outlook → Settings → Mail → Forwarding), then connect that Gmail.</p>
              <a className="lead-link" href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer">Open Google app passwords ↗</a>
            </div>
          </li>
          <li>
            <span className="guide-num">4</span>
            <div>
              <b>Messages and WhatsApp: allow access on your Mac</b>
              <p>System Settings → Privacy &amp; Security → Full Disk Access → turn on Terminal, then quit and reopen Terminal. The script only
                reads. WhatsApp: install WhatsApp Desktop (whatsapp.com/download) and link your phone; this reads the app's own data on your
                Mac and never connects to WhatsApp. It isn't a WhatsApp feature, so if you prefer, skip it and use Export chat below.</p>
            </div>
          </li>
          <li>
            <span className="guide-num">5</span>
            <div>
              <b>Check, then sync</b>
              <p>The first line shows what would be shared and sends nothing. The second sends it once.</p>
              <CopyLine text="python3 ~/coach_connector.py run --dry-run" />
              <CopyLine text="python3 ~/coach_connector.py run" />
            </div>
          </li>
          <li>
            <span className="guide-num">6</span>
            <div>
              <b>Turn on auto-sync</b>
              <p>From then on it runs by itself every 30 minutes while your Mac is awake and sends only new messages that matter, with a
                little context: when nothing new happened, no messages are sent and no AI is used. macOS asks once more for Full Disk
                Access, this time for Python, so auto-sync can read Messages and WhatsApp: the command shows the exact path and opens the
                right settings page. That gives your Mac's Python itself the access, so other scripts run with it get it too; if you'd
                rather not, skip it: Gmail still syncs on its own, and the run line above syncs Messages and WhatsApp by hand.</p>
              <CopyLine text="python3 ~/coach_connector.py schedule" />
              <p className="muted small">Check it: <code>python3 ~/coach_connector.py status</code> · stop it: <code>python3 ~/coach_connector.py unschedule</code></p>
            </div>
          </li>
        </ol>
        <div className="sync-row">
          {(["gmail", "imessage", "whatsapp"] as const).map((c) => {
            const st = syncState(syncOf(c));
            return (
              <div key={c} className={`sync-card is-${st.tone}`}>
                <b>{{ gmail: "Gmail", imessage: "Messages", whatsapp: "WhatsApp" }[c]}</b>
                <span>{st.text}</span>
              </div>
            );
          })}
        </div>
      </section>

      <section className="panel">
        <header className="panel-head">
          <div>
            <h2>Upload or paste · every channel</h2>
            <p>The official export of each app, read on the server in code, then by the specialists. Nothing else from the file is kept.</p>
          </div>
        </header>
        <div className="channel-grid">
          {CHANNELS.map((ch) => (
            <article key={ch.id} className="channel-card">
              <h3>{ch.title}</h3>
              <ol>{ch.steps.map((s) => <li key={s}>{s}</li>)}</ol>
              {ch.note && <p className="muted small">{ch.note}</p>}
              <div className="channel-actions">
                {ch.accept ? (
                  <>
                    <button className="primary-btn" disabled={busy !== null} onClick={() => files.current[ch.id]?.click()}>
                      {busy === ch.id ? "Reading…" : `Upload ${ch.accept.split(",")[0]}`}
                    </button>
                    {isDemo && ch.samples?.map((s) => (
                      <button key={s.name} className="toggle" disabled={busy !== null} onClick={() => trySample(ch, s)}>
                        Try a sample file{ch.samples && ch.samples.length > 1 ? `: ${s.file}` : ""}
                      </button>
                    ))}
                    <input ref={(el) => { files.current[ch.id] = el; }} type="file" accept={ch.accept} hidden onChange={(e) => upload(ch, e)} />
                  </>
                ) : (
                  <button className="toggle" onClick={onGoToday}>Go to Today</button>
                )}
              </div>
              {results[ch.id] && <p className={results[ch.id].ok ? "upload-ok" : "inline-error"}>{results[ch.id].text}</p>}
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
