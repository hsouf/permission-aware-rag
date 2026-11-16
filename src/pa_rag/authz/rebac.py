"""Relationship-based authorization (ReBAC), in-process.

Rules like "managers can read their direct reports' reviews" do not fit in a static
group list. Here the relationship is stored on the document as ``manager-of:<user>``
and expanded per principal from the directory's reporting lines at query time.
Because it is resolved per request, a re-org takes effect on the next query
without re-indexing anything.

At larger scale, move this into OpenFGA, SpiceDB, Cerbos, Oso or Permit.io and have
``subjects`` call the service (or ``can_read`` call its check API). The retriever
does not change: it only depends on the ``Authorizer`` protocol.
"""

from __future__ import annotations

from pa_rag.authz.base import acl_permits
from pa_rag.authz.groups import GroupAuthorizer
from pa_rag.models import Acl, Principal


class RelationshipAuthorizer:
    def __init__(self) -> None:
        self._groups = GroupAuthorizer()

    def subjects(self, principal: Principal) -> frozenset[str]:
        relations = {f"manager-of:{report}" for report in principal.direct_reports}
        return self._groups.subjects(principal) | relations

    def can_read(self, principal: Principal, acl: Acl) -> bool:
        return acl_permits(self.subjects(principal), principal, acl)
