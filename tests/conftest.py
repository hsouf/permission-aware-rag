from __future__ import annotations

import os
from dataclasses import replace

import pytest

from pa_rag.bootstrap import AppState, build
from pa_rag.config import Settings
from pa_rag.llm import ContextOnlyGenerator


@pytest.fixture(scope="session")
def settings() -> Settings:
    # Unit and adversarial tests never touch the network, an LLM or Postgres.
    return replace(Settings.from_env(), database_url=None, llm="none")


@pytest.fixture(scope="session")
def shared_state(settings: Settings) -> AppState:
    """Read-only state shared by tests that do not mutate anything."""
    return build(settings, generator=ContextOnlyGenerator())


@pytest.fixture
def state(settings: Settings) -> AppState:
    """Fresh state for tests that change sharing settings, groups or the index."""
    return build(settings, generator=ContextOnlyGenerator())


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("PA_RAG_DATABASE_URL")
    if not url:
        pytest.skip("PA_RAG_DATABASE_URL not set (run `make db-up`)")
    return url
