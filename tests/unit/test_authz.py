from __future__ import annotations

from pa_rag.authz import GroupAuthorizer, RelationshipAuthorizer
from pa_rag.models import Acl, Classification, Principal

ERIN_REVIEW = Acl(
    frozenset({"user:erin", "manager-of:erin", "group:hr"}), Classification.CONFIDENTIAL
)
DAN = Principal(
    "dan",
    frozenset({"all-staff", "eng", "managers"}),
    Classification.CONFIDENTIAL,
    frozenset({"erin", "ivy"}),
)
IVY = Principal("ivy", frozenset({"all-staff", "eng", "interns"}), Classification.CONFIDENTIAL)


def test_relationships_need_rebac() -> None:
    assert not GroupAuthorizer().can_read(DAN, ERIN_REVIEW)
    assert RelationshipAuthorizer().can_read(DAN, ERIN_REVIEW)


def test_relationship_does_not_extend_to_peers() -> None:
    assert not RelationshipAuthorizer().can_read(IVY, ERIN_REVIEW)


def test_clearance_is_required_in_addition_to_a_matching_subject() -> None:
    acl = Acl(frozenset({"group:eng"}), Classification.RESTRICTED)
    assert not RelationshipAuthorizer().can_read(IVY, acl)
