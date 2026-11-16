from __future__ import annotations

import time

import jwt
import pytest

from pa_rag.auth.directory import Directory
from pa_rag.auth.tokens import TokenVerifier, issue_dev_token
from pa_rag.config import DEFAULT_DATA_DIR
from pa_rag.errors import AuthenticationError
from pa_rag.models import Classification

SECRET = "unit-test-secret-that-is-long-enough-123"
ISS, AUD = "https://idp.example.test", "pa-rag"


@pytest.fixture
def verifier() -> TokenVerifier:
    return TokenVerifier(SECRET, ISS, AUD, leeway_s=0)


def _claims(**overrides: object) -> dict[str, object]:
    now = int(time.time())
    claims: dict[str, object] = {"sub": "ivy", "iss": ISS, "aud": AUD, "iat": now, "exp": now + 60}
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def test_valid_token(verifier: TokenVerifier) -> None:
    assert verifier.verify(issue_dev_token("ivy", SECRET, ISS, AUD)).user_id == "ivy"


@pytest.mark.parametrize(
    ("label", "token"),
    [
        ("wrong key", jwt.encode(_claims(), "another-secret-of-sufficient-length-xx", "HS256")),
        ("expired", jwt.encode(_claims(exp=int(time.time()) - 10), SECRET, "HS256")),
        ("wrong audience", jwt.encode(_claims(aud="other-app"), SECRET, "HS256")),
        ("wrong issuer", jwt.encode(_claims(iss="https://evil.example"), SECRET, "HS256")),
        ("missing exp", jwt.encode(_claims(exp=None), SECRET, "HS256")),
        ("alg none", jwt.encode(_claims(sub="cora"), None, algorithm="none")),
        ("garbage", "not-a-jwt"),
    ],
)
def test_rejected_tokens(verifier: TokenVerifier, label: str, token: str) -> None:
    with pytest.raises(AuthenticationError):
        verifier.verify(token)


def test_groups_come_from_the_directory_not_the_token(verifier: TokenVerifier) -> None:
    # A token that *claims* exec membership changes nothing: groups are looked up server-side.
    token = jwt.encode(_claims(groups=["exec"], clearance="restricted"), SECRET, "HS256")
    identity = verifier.verify(token)
    principal = Directory.from_file(DEFAULT_DATA_DIR / "directory.json").resolve(identity.user_id)
    assert "exec" not in principal.groups
    assert principal.clearance < Classification.RESTRICTED


def test_deprovisioned_user_gets_nothing() -> None:
    directory = Directory.from_file(DEFAULT_DATA_DIR / "directory.json")
    with pytest.raises(AuthenticationError):
        directory.resolve("former-employee")


def test_reporting_lines_resolve_to_direct_reports() -> None:
    directory = Directory.from_file(DEFAULT_DATA_DIR / "directory.json")
    assert directory.resolve("dan").direct_reports == {"ivy", "erin"}
    assert directory.resolve("ivy").direct_reports == frozenset()
