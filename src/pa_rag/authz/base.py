"""The authorization contract the retriever depends on.

Two questions, matching what dedicated authorization services expose:

* ``subjects(principal)``: "what can this user be matched as?" Used to build the
  vector-store pre-filter (the analogue of OpenFGA ``ListObjects`` / SpiceDB
  ``LookupResources``, but expressed as subjects so it fits in a metadata filter).
* ``can_read(principal, acl)``: "can this user read this item?" Used for
  defense-in-depth checks on everything that comes back.
"""

from __future__ import annotations

from typing import Protocol

from pa_rag.models import Acl, Principal


class Authorizer(Protocol):
    def subjects(self, principal: Principal) -> frozenset[str]: ...

    def can_read(self, principal: Principal, acl: Acl) -> bool: ...


def acl_permits(subjects: frozenset[str], principal: Principal, acl: Acl) -> bool:
    """Shared rule: match at least one allowed subject AND hold enough clearance."""
    return bool(subjects & acl.allowed_principals) and principal.clearance >= acl.classification
