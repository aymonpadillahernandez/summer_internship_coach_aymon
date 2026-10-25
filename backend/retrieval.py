"""The student's records as short labelled texts, and BM25 search over them.

A specialist answering the strategist reads only the RETRIEVAL_TOP_K records that best match the question,
instead of the whole database (the tracker sent a ~29K-token snapshot with every question). Records are labelled
[OPP-12] / [CON-7] so answers can cite them, and the code checks every cited id was really in what was retrieved.
BM25 settings follow Lecture 11 (k1=1.4, b=0.75).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date

import db

K1, B = 1.4, 0.75
STOP = set("a an and are as at be by for from has have i in is it its me my of on or our so that the their them they "
           "this to was we what when where which who why will with you your".split())
STAGE = {s["key"]: s["label"] for s in db.STAGES}
NET_STAGE = {s["key"]: s["label"] for s in db.NETWORK_STAGES}


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in STOP and len(t) > 1]


def opportunity_records(user_id: int) -> list[tuple[str, str]]:
    apps = [a for a in db.list_applications(user_id) if not a.get("not_interested_at")]
    contacts = db.list_contacts(user_id)
    leads = db.list_leads(user_id)
    out = []
    for a in apps:
        people = [f"{c['name']} (CON-{c['id']}, {NET_STAGE.get(c['status'], c['status'])}"
                  + (f", next: {c['next_step'] or 'step'} {c['next_date']}" if c["next_date"] else "") + ")"
                  for c in contacts if a["id"] in c["application_ids"] or a["id"] in c["network_ids"]]
        lead_text = [f"{l['kind']}: {l['summary']} {l['when_text']}" for l in leads if a["id"] in l["application_ids"]]
        parts = [f"[OPP-{a['id']}] {a['company']} — {a['role']}", f"stage {STAGE.get(a['status'], a['status'])}",
                 a["priority"] and f"priority {a['priority']}", a["deadline"] and f"deadline {a['deadline']}",
                 a["location"] and f"location {a['location']}", f"MBA eligible {a['mba_eligible']}",
                 f"formal internship {a['formal_internship']}", a.get("fit") and f"fit {a['fit']}: {a.get('fit_reason') or ''}",
                 a["context"] and f"keep in mind: {a['context']}", a["last_contact"] and f"last activity {a['last_contact']}",
                 people and f"people: {'; '.join(people)}", lead_text and f"leads: {'; '.join(lead_text)}",
                 a["notes"] and f"notes: {a['notes'][:200]}"]
        out.append((f"OPP-{a['id']}", " | ".join(p for p in parts if p)))
    return out


def contact_records(user_id: int) -> list[tuple[str, str]]:
    apps = {a["id"]: a for a in db.list_applications(user_id)}
    out = []
    for c in db.list_contacts(user_id):
        if c.get("not_interested_at"):
            continue
        linked = [f"OPP-{i} {apps[i]['company']}" for i in c["application_ids"] if i in apps]
        doors = [f"OPP-{i} {apps[i]['company']}" for i in c["network_ids"] if i in apps]
        history = [f"{e['date']}: {e['text']}" for e in c["events"][:4]]
        parts = [f"[CON-{c['id']}] {c['name']} — {c['affiliation']}", f"stage {NET_STAGE.get(c['status'], c['status'])}",
                 c["last_contact"] and f"last contact {c['last_contact']}", c["how_met"] and f"met: {c['how_met']}",
                 c["next_step"] and f"next step: {c['next_step']} {c['next_date'] or ''}",
                 linked and f"talking about: {', '.join(linked)}", doors and f"could open doors at: {', '.join(doors)}",
                 history and f"history: {' / '.join(history)}", c["notes"] and f"notes: {c['notes'][:160]}"]
        out.append((f"CON-{c['id']}", " | ".join(p for p in parts if p)))
    return out


def search(records: list[tuple[str, str]], query: str, k: int) -> list[tuple[str, str]]:
    """BM25 top-k. When the question matches little (e.g. 'what is urgent?'), fill up with the first records,
    which callers order by urgency."""
    if len(records) <= k:
        return records
    docs = [Counter(tokens(text)) for _, text in records]
    lengths = [sum(d.values()) for d in docs]
    avg = sum(lengths) / len(lengths) or 1
    n = len(docs)
    q = set(tokens(query))
    df = {t: sum(1 for d in docs if t in d) for t in q}
    scores = []
    for i, d in enumerate(docs):
        s = 0.0
        for t in q:
            if t in d:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * d[t] * (K1 + 1) / (d[t] + K1 * (1 - B + B * lengths[i] / avg))
        scores.append(s)
    ranked = sorted(range(n), key=lambda i: -scores[i])
    picked = [i for i in ranked if scores[i] > 0][:k]
    for i in range(n):
        if len(picked) >= k:
            break
        if i not in picked:
            picked.append(i)
    return [records[i] for i in sorted(picked, key=lambda i: -scores[i])]


def urgency_order(records: list[tuple[str, str]], user_id: int) -> list[tuple[str, str]]:
    """Opportunities with the nearest stated deadline / active stage first (used as the fallback order)."""
    today = date.today().isoformat()
    apps = {f"OPP-{a['id']}": a for a in db.list_applications(user_id)}

    def key(rec: tuple[str, str]):
        a = apps.get(rec[0])
        active = a and a["status"] in ("interview", "applied", "wip")
        return (0 if active else 1, (a or {}).get("last_contact") or today)

    return sorted(records, key=key)
