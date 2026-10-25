"""Test setup: a throwaway SQLite database and no network. Agents are driven by PydanticAI FunctionModels that
script what a (possibly manipulated) model would answer, so the tests need no API key and spend no tokens."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.pop("DATABASE_URL", None)  # never touch a real database
os.environ.setdefault("PORTKEY_API_KEY", "test-key-never-used")  # the model is replaced in every test
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import store  # noqa: E402

store.SQLITE_PATH = Path(tempfile.mkdtemp(prefix="coach-test-")) / "test.db"

import main  # noqa: E402  (creates the schema in the throwaway database)
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def demo_client(client):
    assert client.post("/api/auth/demo").status_code == 200
    return client


@pytest.fixture
def accept_test_model(monkeypatch):
    """FunctionModel answers as 'function:…'. Most tests accept it; the substitution test does not use this."""
    import config

    monkeypatch.setattr(config, "MODEL", "function")
