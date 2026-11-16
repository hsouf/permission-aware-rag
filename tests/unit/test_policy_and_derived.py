from __future__ import annotations

import pytest

from pa_rag.bootstrap import AppState
from pa_rag.derived import NoCommonAudienceError, derive_acl, summarize
from pa_rag.ingest.policy import IndexingPolicy
from pa_rag.models import Acl, Classification, Document


def _doc(
    doc_id: str,
    text: str,
    *allowed: str,
    level: Classification = Classification.INTERNAL,
    indexable: bool = True,
) -> Document:
    return Document(doc_id, doc_id, text, Acl(frozenset(allowed), level), doc_id, indexable)


def test_manifest_exclusion_and_deny_patterns() -> None:
    policy = IndexingPolicy()
    assert not policy.decide(_doc("a", "x", "group:hr", indexable=False))[0]
    assert not policy.decide(_doc("b", "SSN 123-45-6789", "group:hr"))[0]
    assert not policy.decide(_doc("c", "id,bank_last4\n1,1234", "group:hr"))[0]
    assert policy.decide(_doc("d", "plain text", "group:hr"))[0]


def test_payroll_export_was_never_indexed(shared_state: AppState) -> None:
    assert "payroll_export_2026_10.csv" in shared_state.index_report.skipped


def test_derived_acl_is_the_strictest_of_its_sources() -> None:
    comp = Acl(frozenset({"group:exec", "group:hr-comp"}), Classification.RESTRICTED, "hr")
    board = Acl(frozenset({"group:exec"}), Classification.RESTRICTED, "exec")
    handbook = Acl(frozenset({"group:all-staff"}), Classification.INTERNAL, "people")

    derived = derive_acl([comp, board])
    assert derived.allowed_principals == {"group:exec"}  # hr-comp can't read the board minutes
    assert derived.classification is Classification.RESTRICTED
    assert derived.department is None

    with pytest.raises(NoCommonAudienceError):
        derive_acl([handbook, comp])


def test_summary_acl_is_decided_before_any_text_is_generated() -> None:
    calls: list[str] = []
    sources = [_doc("open", "a", "group:all-staff"), _doc("secret", "b", "group:exec")]
    with pytest.raises(NoCommonAudienceError):
        summarize(sources, lambda text: calls.append(text) or "summary", "s1")
    assert calls == []  # no tokens spent, nothing to leak


def test_summary_carries_the_derived_acl() -> None:
    sources = [
        _doc("x", "a", "group:exec", "group:hr", level=Classification.CONFIDENTIAL),
        _doc("y", "b", "group:exec", level=Classification.RESTRICTED),
    ]
    summary = summarize(sources, lambda text: text.upper(), "s2")
    assert summary.acl.allowed_principals == {"group:exec"}
    assert summary.acl.classification is Classification.RESTRICTED
