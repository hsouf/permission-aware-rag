"""Token verification: the only way a request gets an identity.

In production you verify tokens minted by your SSO provider against its JWKS
(RS256/ES256). The demo uses a local HS256 issuer so it runs offline, but the
verification rules are the ones that matter in production too: pinned algorithm,
required claims, issuer and audience checks, expiry.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import jwt

from pa_rag.errors import AuthenticationError

ALLOWED_ALGORITHMS = ["HS256"]  # pinned: never accept the token's own "alg" blindly
REQUIRED_CLAIMS = ["sub", "iss", "aud", "exp", "iat"]


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    user_id: str
    token_id: str | None


class TokenVerifier:
    def __init__(self, secret: str, issuer: str, audience: str, leeway_s: int = 30) -> None:
        self._secret = secret
        self._issuer = issuer
        self._audience = audience
        self._leeway = leeway_s

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=ALLOWED_ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"invalid token: {type(exc).__name__}") from exc
        subject = claims["sub"]
        if not isinstance(subject, str) or not subject:
            raise AuthenticationError("invalid token: empty subject")
        return VerifiedIdentity(user_id=subject, token_id=claims.get("jti"))


def issue_dev_token(
    user_id: str,
    secret: str,
    issuer: str,
    audience: str,
    ttl_s: int = 900,
) -> str:
    """Stand-in for the SSO provider. Used by the demo and tests only."""
    now = int(time.time())
    claims = {"sub": user_id, "iss": issuer, "aud": audience, "iat": now, "exp": now + ttl_s}
    return jwt.encode(claims, secret, algorithm="HS256")
