from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pa_rag.api.app import create_app
from pa_rag.auth.tokens import issue_dev_token
from pa_rag.bootstrap import AppState
from tests import oracle


@pytest.fixture
def client(state: AppState) -> TestClient:
    return TestClient(create_app(state=state))


def _auth(state: AppState, user_id: str) -> dict[str, str]:
    s = state.settings
    token = issue_dev_token(user_id, s.jwt_secret, s.jwt_issuer, s.jwt_audience)
    return {"Authorization": f"Bearer {token}"}


def test_health_needs_no_auth(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic x"}]
)
def test_requests_without_a_valid_token_are_rejected(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post("/ask", json={"question": "hi"}, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_token_for_unknown_user_is_rejected(client: TestClient, state: AppState) -> None:
    response = client.get("/me", headers=_auth(state, "mallory"))
    assert response.status_code == 401


def test_me_reflects_the_directory(client: TestClient, state: AppState) -> None:
    body = client.get("/me", headers=_auth(state, "dan")).json()
    assert body == {
        "user_id": "dan",
        "groups": ["all-staff", "eng", "managers"],
        "clearance": "confidential",
        "direct_reports": ["erin", "ivy"],
    }


@pytest.mark.parametrize("field", ["user_id", "as_user", "groups", "role"])
def test_the_body_cannot_carry_identity(client: TestClient, state: AppState, field: str) -> None:
    response = client.post(
        "/ask", json={"question": "CEO salary", field: "cora"}, headers=_auth(state, "ivy")
    )
    assert response.status_code == 422


def test_ask_returns_only_permitted_citations(client: TestClient, state: AppState) -> None:
    response = client.post(
        "/ask", json={"question": "What does the CEO make?"}, headers=_auth(state, "ivy")
    )
    assert response.status_code == 200
    cited_docs = {c.split("#")[0] for c in response.json()["citations"]}
    assert cited_docs
    assert not cited_docs & oracle.forbidden_docs("ivy")
