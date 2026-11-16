"""HTTP API. Identity comes from the Authorization header only.

The request body has no user field, and unknown fields are rejected, so "ask as
cora" is not something a client can even express.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from pa_rag.bootstrap import AppState, build
from pa_rag.config import Settings
from pa_rag.errors import AccessViolation, AuthenticationError
from pa_rag.models import Principal

bearer = HTTPBearer(auto_error=False)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=128)


class AskResponse(BaseModel):
    answer: str
    citations: list[str]
    cache_hit: bool
    tool_calls: list[str]


class MeResponse(BaseModel):
    user_id: str
    groups: list[str]
    clearance: str
    direct_reports: list[str]


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.pa_rag
    return state


def current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    state = _state(request)
    try:
        identity = state.verifier.verify(credentials.credentials)
        return state.directory.resolve(identity.user_id)
    except AuthenticationError as exc:
        raise unauthorized from exc


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def create_app(settings: Settings | None = None, state: AppState | None = None) -> FastAPI:
    app = FastAPI(title="permission-aware-rag", version="0.1.0")
    app.state.pa_rag = state or build(settings or Settings.from_env())

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/me")
    def me(principal: CurrentPrincipal) -> MeResponse:
        return MeResponse(
            user_id=principal.user_id,
            groups=sorted(principal.groups),
            clearance=principal.clearance.name.lower(),
            direct_reports=sorted(principal.direct_reports),
        )

    @app.post("/ask")
    def ask(body: AskRequest, principal: CurrentPrincipal, request: Request) -> AskResponse:
        try:
            answer = _state(request).service.ask(principal, body.question, body.conversation_id)
        except AccessViolation as exc:
            # Fail closed and say nothing about what was found.
            raise HTTPException(status_code=500, detail="internal error") from exc
        return AskResponse(
            answer=answer.text,
            citations=list(answer.citations),
            cache_hit=answer.cache_hit,
            tool_calls=list(answer.tool_calls),
        )

    return app
