"""Recruiting signals used in code (zero tokens) to keep only what matters before any model sees it: the LinkedIn
messages filter here, and the Coach Connector on the student's computer (it downloads this list with the student's
organisations and people from /api/connector/context, so both filters stay the same)."""

from __future__ import annotations

import re
import unicodedata

RECRUITING_WORDS = [
    "internship", "intern", "summer associate", "mba", "recruit", "recruiter", "recruiting", "interview", "superday",
    "application", "applied", "apply", "offer", "position", "opening", "hiring", "coffee chat", "coffee",
    "informational", "catch up", "zoom", "intro", "introduce", "introduction", "connect you", "connecting you",
    "referral", "refer you", "resume", "cv", "networking", "career", "alum", "alumni", "prácticas", "entrevista",
]
AUTOMATED = re.compile(r"verification code|your code is|one-time code|reply stop|text stop|tracking number|out for delivery|"
                       r"unsubscribe from this list", re.I)


def norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def topic_regex(organisations: list[str]) -> re.Pattern:
    words = RECRUITING_WORDS + [o for o in organisations if len(o) >= 3]
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True)) + r")\b", re.I)


def context(user_id: int) -> dict:
    """What the student's own filters need: their organisations, their people and the recruiting words."""
    import db

    return {"organisations": sorted({a["company"] for a in db.list_applications(user_id) if a["company"].strip()}),
            "people": sorted({c["name"] for c in db.list_contacts(user_id)}),
            "keywords": RECRUITING_WORDS}
