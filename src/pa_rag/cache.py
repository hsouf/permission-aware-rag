"""Response cache keyed by permission set, never by question alone.

A cache keyed only on the question serves the CEO's answer to the intern. Here the
key includes a fingerprint of everything that decides what the caller can see:
their resolved subjects, their clearance, and the source system's ACL version (so
any sharing change invalidates every entry).
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable

from pa_rag.authz.base import Authorizer
from pa_rag.models import Answer, Principal


def permission_fingerprint(principal: Principal, authorizer: Authorizer, acl_version: int) -> str:
    material = "|".join(
        [
            ",".join(sorted(authorizer.subjects(principal))),
            str(int(principal.clearance)),
            f"acl-v{acl_version}",
        ]
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _normalize(question: str) -> str:
    return " ".join(question.lower().split())


class PermissionScopedCache:
    def __init__(self, ttl_s: float = 300.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_s
        self._clock = clock
        self._entries: dict[str, tuple[float, Answer]] = {}

    @staticmethod
    def key(fingerprint: str, question: str) -> str:
        return hashlib.sha256(f"{fingerprint}\n{_normalize(question)}".encode()).hexdigest()

    def get(self, fingerprint: str, question: str) -> Answer | None:
        entry = self._entries.get(self.key(fingerprint, question))
        if entry is None:
            return None
        stored_at, answer = entry
        if self._clock() - stored_at > self._ttl:
            return None
        return answer

    def put(self, fingerprint: str, question: str, answer: Answer) -> None:
        self._entries[self.key(fingerprint, question)] = (self._clock(), answer)
