"""Settings for Summer Internship Coach: .env loading, the one allowed model, the Portkey client and every limit.

.env lookup order (a value found first wins; variables already set in the environment are never overridden):
  1. the repo folder
  2. one folder above the repo (the teaching staff's layout: submissions/.env + submissions/<repo>/)
  3. two folders above the repo (only for this course workspace, whose single .env sits at its root)
Never print, log or commit the key. Limits are UPPER_CASE so the report can quote them exactly.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # keep logs clean

from dotenv import load_dotenv  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings  # noqa: E402
from pydantic_ai.providers.openai import OpenAIProvider  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent  # the repo folder
ENV_FILES = (ROOT / ".env", ROOT.parent / ".env", ROOT.parent.parent / ".env")
ENV_SLOTS = ("the repo folder", "one folder above the repo", "two folders above the repo (course workspace root)")


def load_env() -> Path | None:
    """Load every .env in lookup order; return the first one found (the one whose values win)."""
    found = [env for env in ENV_FILES if env.is_file()]
    for env in found:
        load_dotenv(env, override=False)
    return found[0] if found else None


ENV_USED = load_env()

# ─── Model ──────────────────────────────────────────────────────────────
MODEL = "gpt-6-luna"  # the course Portkey key allows this model only; replies from any other model are rejected
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
FORCE_FRESH_ANSWERS = True  # Portkey's response cache replays identical requests; measured runs must reach the model
REASONING_EFFORT = "low"  # every agent; fewer hidden reasoning tokens per request
MODEL_SETTINGS = OpenAIResponsesModelSettings(openai_reasoning_effort=REASONING_EFFORT)

# Price per 1M tokens in USD. None = not known yet: the app shows token counts and leaves cost blank rather than guess.
PRICE_INPUT_PER_M: float | None = None
PRICE_CACHED_INPUT_PER_M: float | None = None
PRICE_OUTPUT_PER_M: float | None = None
PRICE_SOURCE = ""  # where the prices came from (URL + date), shown next to every cost

# ─── Limits (stopping rules and guardrails) ─────────────────────────────
MAX_INPUT_CHARS = 20_000  # one paste or upload; longer is refused before any model call (422, 0 tokens)
MAX_EXPORT_CHARS = 400_000  # a LinkedIn connections export may be this long: code filters it before any model call
LINKEDIN_MAX_ROWS = 40  # rows (connections at tracked organisations) the network agent may read from one export
MAX_CHAT_CHARS = 4_000  # one chat message
MAX_CHAT_TURNS = 12  # earlier turns are dropped before the model sees them
MAX_CANDIDATES = 60  # action-plan items the strategist may rank
AGENT_REQUEST_LIMIT = 6  # model requests per agent run
AGENT_TOOL_CALLS_LIMIT = 6  # tool calls per agent run
AGENT_TOTAL_TOKENS_LIMIT = 60_000  # tokens per agent run
AGENT_TIMEOUT_SECONDS = 90  # one agent run (the strategist's run includes waiting for its specialists)
SPECIALIST_TIMEOUT_SECONDS = 40  # one specialist answer; a slow one is cut off and the strategist carries on without it
MAX_DELEGATIONS_PER_RUN = 4  # the strategist's calls to the two specialists, per request
OUTPUT_RETRIES = 2  # re-asks when the structured output fails validation
DAILY_TOKEN_BUDGET = int(os.getenv("DAILY_TOKEN_BUDGET", "300000"))  # per user per UTC day; over it -> 429
GLOBAL_DAILY_TOKEN_BUDGET = int(os.getenv("GLOBAL_DAILY_TOKEN_BUDGET", "3000000"))  # whole site per UTC day
RETRIEVAL_TOP_K = 10  # records a specialist reads per question (BM25), instead of the whole database
DEMO_TTL_DAYS = 3  # demo accounts (and their data) are deleted after this many days
SIGNUP_CODE = os.getenv("SIGNUP_CODE", "").strip()  # optional: when set, sign-up asks for it


def key_is_set() -> bool:
    return bool(os.getenv("PORTKEY_API_KEY", "").strip())


def env_slot() -> str:
    return dict(zip(ENV_FILES, ENV_SLOTS)).get(ENV_USED, "none found (using the host's environment variables)")


def require_key() -> str:
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is missing. Put it in a .env inside the repo or one folder above it "
                           "(see .env.example).")
    return key


@lru_cache(maxsize=1)
def build_model() -> OpenAIResponsesModel:
    """gpt-6-luna through Portkey (the Lecture 12 / HW5 pattern)."""
    headers = {"x-portkey-provider": "openai"}
    if FORCE_FRESH_ANSWERS:
        headers["x-portkey-cache-force-refresh"] = "true"
    client = AsyncOpenAI(api_key=require_key(), base_url=PORTKEY_BASE_URL, default_headers=headers, max_retries=1)
    return OpenAIResponsesModel(MODEL, provider=OpenAIProvider(openai_client=client))


def cost_usd(input_tokens: int, cached_tokens: int, output_tokens: int) -> float | None:
    """Cost of one call; None while prices are unknown. input_tokens already include cached ones."""
    if None in (PRICE_INPUT_PER_M, PRICE_CACHED_INPUT_PER_M, PRICE_OUTPUT_PER_M):
        return None
    fresh = max(0, input_tokens - cached_tokens)
    return (fresh * PRICE_INPUT_PER_M + cached_tokens * PRICE_CACHED_INPUT_PER_M + output_tokens * PRICE_OUTPUT_PER_M) / 1e6
