"""Settings from environment variables. Nothing here is user-controllable at request time."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-0123456789"  # noqa: S105
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass(frozen=True, slots=True)
class Settings:
    env: str
    jwt_secret: str
    jwt_issuer: str
    jwt_audience: str
    data_dir: Path
    database_url: str | None
    anthropic_model: str
    llm: str

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get("PA_RAG_ENV", "dev")
        secret = os.environ.get("PA_RAG_JWT_SECRET", DEV_JWT_SECRET)
        if env != "dev" and secret == DEV_JWT_SECRET:
            raise RuntimeError("PA_RAG_JWT_SECRET must be set outside the dev environment")
        return cls(
            env=env,
            jwt_secret=secret,
            jwt_issuer=os.environ.get("PA_RAG_JWT_ISSUER", "https://idp.example.test"),
            jwt_audience=os.environ.get("PA_RAG_JWT_AUDIENCE", "pa-rag"),
            data_dir=Path(os.environ.get("PA_RAG_DATA_DIR", DEFAULT_DATA_DIR)),
            database_url=os.environ.get("PA_RAG_DATABASE_URL") or None,
            anthropic_model=os.environ.get("PA_RAG_ANTHROPIC_MODEL", "claude-opus-5-5"),
            llm=os.environ.get("PA_RAG_LLM", "none"),
        )
