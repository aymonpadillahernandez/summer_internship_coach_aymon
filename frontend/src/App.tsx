import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import type { Application, Contact, Lead, Stage, SyncInfo } from "./types";
import { type Candidate, type DataCheck, fetchBoard, fetchProfile, fetchChecks, fetchDone, fetchLeads, fetchNetwork, markAction, moveApplication, moveContact, setAppInterest, setContactInterest, updateContact } from "./api";
import { type Action, bucketOf, checkActions, followUpDue, internshipActions, leadActions, networkingActions, sortActions, todayIso } from "./actions";
import ChatPanel from "./components/ChatPanel";
import ActionPlan from "./components/ActionPlan";
import { byPriority, followUp, formatDate, hasContacts, priorityRank, priorityTier, safeUrl, yesNo } from "./format";
import Board from "./components/Board";
import Card from "./components/Card";
import ContactCard from "./components/ContactCard";
import ContactSheet from "./components/ContactSheet";
import DetailSheet from "./components/DetailSheet";
import { ChatIcon, MoonIcon, SearchIcon, SunIcon } from "./components/Icons";
import TodayView from "./components/TodayView";
import ConnectView from "./components/ConnectView";
import UsagePanel from "./components/UsagePanel";
import ProfilePanel from "./components/ProfilePanel";
import type { User } from "./api";

type Tab = "today" | "internships" | "networking" | "plan" | "connect";
type Area = "internships" | "networking";
type Tier = "all" | "A" | "B";
type Source = "all" | "email" | "chat" | "linkedin" | "posting" | "note" | "demo";
const INACTIVE = new Set(["not_started", "rejected"]);
const TABS: Tab[] = ["today", "internships", "networking", "plan", "connect"];
const tabFromHash = (): Tab => TABS.find((t) => window.location.hash === `#${t}`) ?? "today";
const isoDay = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
/** The action plan, as the only actions the Career coach may rank (it can never invent one). */
const toCandidate = (a: Action): Candidate => ({ key: a.key, title: a.title, subtitle: a.subtitle, due: a.due ? isoDay(a.due) : null, why: a.why });

/** Optimistic status change that rolls back only this card, and only if nothing moved it since. */
function mover<T extends { id: number; status: string }>(
  items: T[],
  setItems: Dispatch<SetStateAction<T[]>>,
  save: (id: number, status: string) => Promise<T>,
  onSaved: () => void,
  onFail: () => void,
) {
  return async (id: number, status: string) => {
    const prev = items.find((a) => a.id === id)?.status;
    if (!prev || prev === status) return;
    const settle = (patch: Partial<T>) =>
      setItems((cur) => cur.map((a) => (a.id === id && a.status === status ? { ...a, ...patch } : a)));
    setItems((cur) => cur.map((a) => (a.id === id ? { ...a, status } : a)));
    try {
      settle(await save(id, status));
      onSaved();
    } catch {
      settle({ status: prev } as Partial<T>);
      onFail();
    }
  };
}

export default function App({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const readOnly = false;
  const [showUsage, setShowUsage] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [profileFilled, setProfileFilled] = useState(true);
  const loadProfile = () => fetchProfile().then((r) => setProfileFilled(r.text.trim().length > 0)).catch(() => {});
  const [asking, setAsking] = useState(false);
  const [askSeed, setAskSeed] = useState<string | undefined>(undefined);
  const [outboxKey, setOutboxKey] = useState(0);  // bumped when the coach chat closes, so new drafts show on Today
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === "dark");
  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    if (next) document.documentElement.dataset.theme = "dark";
    else delete document.documentElement.dataset.theme;
    localStorage.setItem("coach-theme", next ? "dark" : "light");
  };
  const [checks, setChecks] = useState<DataCheck[]>([]);
  const [tab, setTabState] = useState<Tab>(tabFromHash);
  const [error, setError] = useState<string | null>(null);

  const [stages, setStages] = useState<Stage[]>([]);
  const [apps, setApps] = useState<Application[]>([]);
  const [openAppId, setOpenAppId] = useState<number | null>(null);

  const [netStages, setNetStages] = useState<Stage[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [, setSync] = useState<SyncInfo | null>(null);
  const [openContactId, setOpenContactId] = useState<number | null>(null);

  const [leads, setLeads] = useState<Lead[]>([]);
  const [done, setDone] = useState<Set<string>>(new Set());
  const [area, setArea] = useState<Area>("internships");
  const [toast, setToast] = useState<{ action: Action; undo: () => Promise<void> } | null>(null);

  // Summer internships filters
  const [query, setQuery] = useState("");
  const [tier, setTier] = useState<Tier>("all");
  const [formalOnly, setFormalOnly] = useState(false);
  const [mbaOnly, setMbaOnly] = useState(false);
  // Networking filters
  const [netQuery, setNetQuery] = useState("");
  const [source, setSource] = useState<Source>("all");
  const [aTierOnly, setATierOnly] = useState(false);
  const [dueOnly, setDueOnly] = useState(false);

  const loadNetwork = () =>
    fetchNetwork()
      .then((d) => {
        setNetStages(d.stages);
        setContacts(d.contacts);
        setSync(d.sync);
      })
      .catch(() => setError("Couldn't load your networking contacts."));

  const loadBoard = () =>
    fetchBoard()
      .then((d) => {
        setStages(d.stages);
        setApps(d.applications);
      })
      .catch(() => setError("Can't reach the coach's server. Is the backend running on port 8020?"));

  const loadLeads = () => fetchLeads().then((d) => setLeads(d.leads)).catch(() => {});
  const reloadAll = async () => {
    await Promise.all([loadBoard(), loadNetwork(), loadLeads()]);
  };

  useEffect(() => {
    loadBoard();
    loadNetwork();
    loadLeads();
    loadProfile();
    fetchDone().then((d) => setDone(new Set(d.done))).catch(() => {});
    const onHash = () => setTabState(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const setTab = (t: Tab) => {
    window.location.hash = t;
    setTabState(t);
  };
  // A new account starts at Setup (the Setup guide is step 1); only once, and never over a link to another tab.
  useEffect(() => {
    Promise.all([fetchBoard(), fetchNetwork()]).then(([b, n]) => {
      if (!b.applications.length && !n.contacts.length && !window.location.hash && !localStorage.getItem("coach-setup-landed")) {
        localStorage.setItem("coach-setup-landed", "1");
        setTab("connect");
      }
    }).catch(() => {});
  }, []);
  const openApp = (a: Application) => {
    setOpenContactId(null);
    setTab("internships");
    setOpenAppId(a.id);
  };
  const openContact = (c: Contact) => {
    setOpenAppId(null);
    setTab("networking");
    setOpenContactId(c.id);
  };
  /** "OPP-12" / "CON-7" (the ids agents cite) -> open that card. */
  const openRecord = (id: string) => {
    const [kind, num] = id.split("-");
    if (kind === "OPP") {
      const a = apps.find((x) => x.id === Number(num));
      if (a) openApp(a);
    } else if (kind === "CON") {
      const c = contacts.find((x) => x.id === Number(num));
      if (c) openContact(c);
    }
    setShowUsage(false);
    setAsking(false);
  };

  const appById = useMemo(() => new Map(apps.map((a) => [a.id, a])), [apps]);
  const contactByName = useMemo(() => new Map(contacts.map((c) => [c.name.toLowerCase(), c])), [contacts]);

  // ─── Summer internships ─────────────────────────────────
  const visibleApps = useMemo(() => {
    const q = query.trim().toLowerCase();
    return apps.filter(
      (a) =>
        (tier === "all" || priorityTier(a.priority) === tier) &&
        (!formalOnly || yesNo(a.formal_internship) === "Y") &&
        (!mbaOnly || yesNo(a.mba_eligible) === "Y") &&
        (!q || [a.company, a.role, a.location, a.context, a.stakeholders].join(" ").toLowerCase().includes(q)),
    );
  }, [apps, query, tier, formalOnly, mbaOnly]);

  const moveApp = readOnly ? async () => {} : mover(apps, setApps, moveApplication, () => {}, () =>
    setError("Couldn't save that move. That card has been put back."),
  );

  // ─── Networking ─────────────────────────────────────────
  const bestRank = (c: Contact) => {
    const ids = c.application_ids.length ? c.application_ids : c.network_ids;
    return Math.min(99, ...ids.map((id) => priorityRank(appById.get(id)?.priority ?? "")));
  };
  const isDue = (c: Contact) =>
    (c.status === "reached_out" && !!c.last_contact && followUp(c.last_contact).overdue) ||
    (c.status === "follow_up" && followUpDue(c) <= new Date());
  const linkedToATier = (c: Contact) =>
    [...c.application_ids, ...c.network_ids].some((id) => priorityTier(appById.get(id)?.priority ?? "B") === "A");

  const visibleContacts = useMemo(() => {
    const q = netQuery.trim().toLowerCase();
    return contacts.filter((c) => {
      const companies = [...c.application_ids, ...c.network_ids].map((id) => appById.get(id)?.company ?? "");
      return (
        (source === "all" || c.source === source || c.events.some((e) => e.origin === source)) &&
        (!aTierOnly || linkedToATier(c)) &&
        (!dueOnly || isDue(c)) &&
        (!q || [c.name, c.affiliation, c.notes, c.how_met, ...companies].join(" ").toLowerCase().includes(q))
      );
    });
  }, [contacts, appById, netQuery, source, aTierOnly, dueOnly]);

  // Follow-ups sort by when they are due; other columns by the date of the next step.
  const nextKey = (c: Contact) => (c.status === "follow_up" ? followUpDue(c).toISOString().slice(0, 10) : c.next_date ?? "9999");
  const byNext = (a: Contact, b: Contact) =>
    nextKey(a).localeCompare(nextKey(b)) ||
    bestRank(a) - bestRank(b) ||
    (b.last_contact ?? "").localeCompare(a.last_contact ?? "") ||
    a.name.localeCompare(b.name);

  // A contact's status also shows on internship cards, so refresh them after a move.
  const moveNet = readOnly ? async () => {} : mover(contacts, setContacts, moveContact, loadBoard, () =>
    setError("Couldn't save that move. That card has been put back."),
  );

  // ─── Shared ─────────────────────────────────────────────
  const nextCall = useMemo(
    () =>
      contacts
        .filter((c) => !c.not_interested_at && c.status === "call_booked" && c.next_date && new Date(c.next_date) >= new Date(new Date().toDateString()))
        .sort((a, b) => a.next_date!.localeCompare(b.next_date!))[0] ?? null,
    [contacts],
  );

  // Cards set aside as not interested don't count anywhere; they stay folded on the board.
  const keptApps = apps.filter((a) => !a.not_interested_at);
  const keptContacts = contacts.filter((c) => !c.not_interested_at);
  const appStats = {
    total: keptApps.length,
    aTier: keptApps.filter((a) => priorityTier(a.priority) === "A").length,
    mapped: keptApps.filter(hasContacts).length,
    active: keptApps.filter((a) => !INACTIVE.has(a.status)).length,
  };
  const netStats = {
    total: keptContacts.length,
    toContact: keptContacts.filter((c) => c.status === "to_contact").length,
    waiting: keptContacts.filter((c) => c.status === "reached_out").length,
    due: keptContacts.filter(isDue).length,
  };
  const setInterest = async (kind: "app" | "contact", id: number, notInterested: boolean) => {
    try {
      if (kind === "app") {
        const row = await setAppInterest(id, notInterested);
        setApps((xs) => xs.map((a) => (a.id === id ? row : a)));
      } else {
        const row = await setContactInterest(id, notInterested);
        setContacts((xs) => xs.map((c) => (c.id === id ? row : c)));
      }
    } catch {
      setError("Couldn't save that change. Try again.");
    }
  };

  // ─── Action plan ────────────────────────────────────────
  useEffect(() => {
    if (apps.length || contacts.length) fetchChecks().then((d) => setChecks(d.checks)).catch(() => {});
  }, [apps, contacts]);
  const allActions = useMemo(
    () =>
      [...checkActions(checks, appById, contacts), ...internshipActions(apps), ...networkingActions(contacts, appById),
        ...leadActions(leads, appById)].filter((a) => !done.has(a.key)),
    [checks, apps, contacts, leads, appById, done],
  );
  const planActions = allActions.filter((a) => a.area === area);
  const candidates = useMemo(() => [...allActions].sort(sortActions).slice(0, 60).map(toCandidate), [allActions]);
  const weekCount = allActions.filter((a) => ["overdue", "week"].includes(bucketOf(a))).length;
  const firstName = user.is_demo ? "Jordan" : (user.name.trim().split(/\s+/)[0] ?? "");
  const countIn = (a: Area) => allActions.filter((x) => x.area === a).length;
  const planStats = {
    overdue: planActions.filter((a) => bucketOf(a) === "overdue").length,
    week: planActions.filter((a) => bucketOf(a) === "week").length,
    soon: planActions.filter((a) => bucketOf(a) === "soon").length,
    done: done.size,
  };

  /** Tick an action off. Clear-cut ones also update the card they came from. */
  async function completeAction(a: Action) {
    if (readOnly) return;
    const c = a.contact;
    const before = c ? { status: c.status, last_contact: c.last_contact ?? undefined } : null;
    setDone((cur) => new Set(cur).add(a.key));
    try {
      await markAction(a.key, true);
      if (c && a.kind === "reach") await updateContact(c.id, { status: "reached_out", last_contact: todayIso() });
      if (c && a.kind === "nudge") await updateContact(c.id, { last_contact: todayIso() });
      if (c && a.kind === "call" && a.title.startsWith("Log")) await updateContact(c.id, { status: "follow_up", last_contact: todayIso() });
      if (c && ["reach", "nudge", "call"].includes(a.kind)) await Promise.all([loadNetwork(), loadBoard()]);
      setToast({
        action: a,
        undo: async () => {
          await markAction(a.key, false);
          if (c && before && ["reach", "nudge", "call"].includes(a.kind)) {
            await updateContact(c.id, { status: before.status, last_contact: before.last_contact ?? "" });
            await Promise.all([loadNetwork(), loadBoard()]);
          }
          setDone((cur) => {
            const next = new Set(cur);
            next.delete(a.key);
            return next;
          });
          setToast(null);
        },
      });
    } catch {
      setDone((cur) => {
        const next = new Set(cur);
        next.delete(a.key);
        return next;
      });
      setError("Couldn't save that. The action is back on the plan.");
    }
  }
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(t);
  }, [toast]);

  const openAction = (a: Action) => {
    if (a.contact) openContact(a.contact);
    else if (a.app) openApp(a.app);
    else if (a.apps) setTab("internships");
    else if (a.kind === "review") {
      setSource("linkedin");
      setTab("networking");
    }
    else if (safeUrl(a.lead?.url)) window.open(safeUrl(a.lead?.url), "_blank", "noreferrer");
  };

  const shownApp = apps.find((a) => a.id === openAppId) ?? null;
  const shownContact = contacts.find((c) => c.id === openContactId) ?? null;
  const filteredApps = visibleApps.length !== apps.length;
  const filteredContacts = visibleContacts.length !== contacts.length;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <img src="/favicon.svg" alt="" width={30} height={30} />
          <div>
            <h1>Summer Internship Coach</h1>
            <p>{user.is_demo ? "Demo · fictional student" : "Your AI career coach"}</p>
          </div>
        </div>
        <div className="segmented view-switch" role="tablist" aria-label="Section">
          <button role="tab" aria-selected={tab === "today"} className={tab === "today" ? "is-active" : ""} onClick={() => setTab("today")}>
            Today
          </button>
          <button role="tab" aria-selected={tab === "internships"} className={tab === "internships" ? "is-active" : ""} onClick={() => setTab("internships")}>
            Opportunities <span>{appStats.total}</span>
          </button>
          <button role="tab" aria-selected={tab === "networking"} className={tab === "networking" ? "is-active" : ""} onClick={() => setTab("networking")}>
            Networking <span>{netStats.total}</span>
          </button>
          <button role="tab" aria-selected={tab === "plan"} className={tab === "plan" ? "is-active" : ""} onClick={() => setTab("plan")}>
            Action plan <span>{allActions.length}</span>
          </button>
          <button role="tab" aria-selected={tab === "connect"} className={tab === "connect" ? "is-active" : ""} onClick={() => setTab("connect")}>
            Setup
          </button>
        </div>
        <dl className="stats">
          {tab === "plan" ? (
            <>
              <div className={planStats.overdue ? "stat-due" : ""}><dt>Overdue</dt><dd>{planStats.overdue}</dd></div>
              <div className="stat-accent"><dt>This week</dt><dd>{planStats.week}</dd></div>
              <div><dt>Next 2 weeks</dt><dd>{planStats.soon}</dd></div>
              <div><dt>Done</dt><dd>{planStats.done}</dd></div>
            </>
          ) : tab === "internships" ? (
            <>
              <div><dt>Opportunities</dt><dd>{appStats.total}</dd></div>
              <div><dt>A-tier</dt><dd>{appStats.aTier}</dd></div>
              <div><dt>Contacts mapped</dt><dd>{appStats.mapped}</dd></div>
              <div className="stat-accent"><dt>In motion</dt><dd>{appStats.active}</dd></div>
            </>
          ) : tab === "networking" ? (
            <>
              <div><dt>People</dt><dd>{netStats.total}</dd></div>
              <div><dt>To contact</dt><dd>{netStats.toContact}</dd></div>
              <div className="stat-accent"><dt>Waiting on reply</dt><dd>{netStats.waiting}</dd></div>
              <div className={netStats.due ? "stat-due" : ""}><dt>Follow-ups due</dt><dd>{netStats.due}</dd></div>
            </>
          ) : (
            <>
              <div><dt>Opportunities</dt><dd>{appStats.total}</dd></div>
              <div><dt>People</dt><dd>{netStats.total}</dd></div>
              <div className="stat-accent"><dt>Due this week</dt><dd>{weekCount}</dd></div>
              <div className={netStats.due ? "stat-due" : ""}><dt>Follow-ups due</dt><dd>{netStats.due}</dd></div>
            </>
          )}
          {nextCall && (
            <button className="stat-next" onClick={() => openContact(nextCall)} title={nextCall.next_step ?? ""}>
              <dt>Next call</dt>
              <dd>{formatDate(nextCall.next_date!)}</dd>
              <small>{nextCall.name}</small>
            </button>
          )}
          <button className="stat-next stat-ask" onClick={() => setAsking(true)} title="Ask the Career coach about your search">
            <dt>Ask your coach</dt>
            <dd><ChatIcon /> Ask a question</dd>
            <small>Answers from your records</small>
          </button>
        </dl>
        <div className="account">
          {user.is_demo && <span className="view-only" title="A private sandbox with fictional data, deleted after 3 days">Demo</span>}
          <button className="toggle" onClick={() => setShowUsage(true)} title="Real token usage of every AI run">Usage</button>
          <button className="toggle" onClick={() => setShowProfile(true)} title="Your profile and your data">Profile</button>
          <button className="account-btn" onClick={onSignOut} title={`Signed in as ${user.email}`}>
            <span className="person-avatar account-avatar" aria-hidden>{(user.name || user.email).slice(0, 1).toUpperCase()}</span>
            Sign out
          </button>
          <button className="toggle theme-btn" onClick={toggleTheme} title={dark ? "Day mode" : "Night mode"} aria-label={dark ? "Switch to day mode" : "Switch to night mode"}>
            {dark ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </header>

      {tab === "today" || tab === "connect" ? null : tab === "plan" ? (
        <div className="toolbar">
          <div className="segmented subtabs" role="tablist" aria-label="Action plan area">
            {(["internships", "networking"] as Area[]).map((a) => (
              <button key={a} role="tab" aria-selected={area === a} className={area === a ? "is-active" : ""} onClick={() => setArea(a)}>
                {a === "internships" ? "Opportunities" : "Networking"} <span>{countIn(a)}</span>
              </button>
            ))}
          </div>
          <span className="showing">Tick an action when it's done. Click it to open the card behind it.</span>
          <span className="legend">Worked out in code from your records · the coach ranks them on Today</span>
        </div>
      ) : tab === "internships" ? (
        <div className="toolbar">
          <label className="search">
            <SearchIcon />
            <input placeholder="Search company, role, city, person…" value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          <div className="segmented" role="group" aria-label="Priority tier">
            {(["all", "A", "B"] as Tier[]).map((t) => (
              <button key={t} className={tier === t ? "is-active" : ""} onClick={() => setTier(t)}>
                {t === "all" ? "All" : `${t}-tier`}
              </button>
            ))}
          </div>
          <button className={`toggle${formalOnly ? " is-on" : ""}`} onClick={() => setFormalOnly(!formalOnly)}>Formal internships</button>
          <button className={`toggle${mbaOnly ? " is-on" : ""}`} onClick={() => setMbaOnly(!mbaOnly)}>MBA eligible</button>
          {filteredApps && <span className="showing">Showing {visibleApps.length} of {apps.length}</span>}
          <span className="legend" aria-label="Answer key">
            <b className="yn yn-yes">Y</b> yes
            <b className="yn yn-no">N</b> no
            <b className="yn yn-unknown">?</b> not stated
          </span>
        </div>
      ) : (
        <div className="toolbar">
          <label className="search">
            <SearchIcon />
            <input placeholder="Search name, organisation, note…" value={netQuery} onChange={(e) => setNetQuery(e.target.value)} />
          </label>
          <div className="segmented" role="group" aria-label="Source">
            {(["all", "email", "chat", "linkedin", "posting", "note", "demo"] as Source[]).map((s) => (
              <button key={s} className={source === s ? "is-active" : ""} onClick={() => setSource(s)}>
                {{ all: "All", email: "Email", chat: "Chats", linkedin: "LinkedIn", posting: "Postings", note: "Notes", demo: "Demo" }[s]}
              </button>
            ))}
          </div>
          <button className={`toggle${aTierOnly ? " is-on" : ""}`} onClick={() => setATierOnly(!aTierOnly)}>Linked to A-tier</button>
          <button className={`toggle${dueOnly ? " is-on" : ""}`} onClick={() => setDueOnly(!dueOnly)}>Follow-up due</button>
          {filteredContacts && <span className="showing">Showing {visibleContacts.length} of {contacts.length}</span>}
        </div>
      )}

      {error && (
        <div className="banner" role="alert">
          {error}
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {tab === "connect" ? (
        <ConnectView onChanged={reloadAll} onGoToday={() => setTab("today")} />
      ) : tab === "today" ? (
        <TodayView
          candidates={candidates}
          onOpenRecord={openRecord}
          onChanged={reloadAll}
          onAsk={(q) => { setAskSeed(q); setAsking(true); }}
          firstName={firstName}
          counts={{ opportunities: apps.length, people: contacts.length }}
          profileFilled={profileFilled}
          onOpenProfile={() => setShowProfile(true)}
          onOpenConnect={() => setTab("connect")}
          outboxKey={outboxKey}
        />
      ) : tab === "plan" ? (
        <ActionPlan actions={planActions} onDone={completeAction} onOpen={openAction} readOnly={readOnly} />
      ) : tab === "internships" ? (
        <Board
          stages={stages}
          items={visibleApps}
          sort={byPriority}
          onMove={moveApp}
          readOnly={readOnly}
          renderCard={(a, label, drag) => <Card app={a} statusLabel={label} onOpen={openApp} drag={drag} />}
        />
      ) : (
        <Board
          stages={netStages}
          items={visibleContacts}
          sort={byNext}
          onMove={moveNet}
          readOnly={readOnly}
          renderCard={(c, label, drag) => (
            <ContactCard c={c} statusLabel={label} apps={appById} onOpen={openContact} onOpenApp={openApp} drag={drag} />
          )}
        />
      )}

      {showUsage && <UsagePanel onClose={() => setShowUsage(false)} onOpenRecord={openRecord} />}
      {showProfile && <ProfilePanel user={user} onClose={() => { setShowProfile(false); loadProfile(); }} onSaved={loadProfile} onDeleted={onSignOut} />}
      {asking && (
        <ChatPanel seed={askSeed} candidates={candidates} onOpenRecord={openRecord} onClose={() => { setAsking(false); setAskSeed(undefined); setOutboxKey((k) => k + 1); }} />
      )}

      {toast && (
        <div className="toast" role="status">
          <span><b>Done:</b> {toast.action.title}</span>
          <button onClick={() => toast.undo()}>Undo</button>
        </div>
      )}

      {shownApp && (
        <DetailSheet
          app={shownApp}
          stages={stages}
          onMove={moveApp}
          onClose={() => setOpenAppId(null)}
          readOnly={readOnly}
          findContact={(name) => contactByName.get(name.toLowerCase())}
          onOpenContact={openContact}
          onInterest={(v) => setInterest("app", shownApp.id, v)}
          onUpdated={(card) => setApps((xs) => xs.map((a) => (a.id === card.id ? card : a)))}
        />
      )}
      {shownContact && (
        <ContactSheet
          c={shownContact}
          stages={netStages}
          apps={appById}
          onMove={moveNet}
          onOpenApp={openApp}
          onClose={() => setOpenContactId(null)}
          readOnly={readOnly}
          onInterest={(v) => setInterest("contact", shownContact.id, v)}
          onPrepare={() => { setOpenContactId(null); setAskSeed(`Prepare my call with ${shownContact.name}`); setAsking(true); }}
        />
      )}
    </div>
  );
}
