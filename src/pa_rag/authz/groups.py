"""Plain group-based authorization. Enough for most small deployments."""

from __future__ import annotations

from pa_rag.authz.base import acl_permits
from pa_rag.models import Acl, Principal


class GroupAuthorizer:
    def subjects(self, principal: Principal) -> frozenset[str]:
        return frozenset({f"user:{principal.user_id}"} | {f"group:{g}" for g in principal.groups})

    def can_read(self, principal: Principal, acl: Acl) -> bool:
        return acl_permits(self.subjects(principal), principal, acl)
