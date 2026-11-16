"""Cache, memory, ACL drift: the places most real leaks come from."""

from __future__ import annotations

from pa_rag.acl_sync import sync_acls
from pa_rag.bootstrap import AppState
from pa_rag.cache import PermissionScopedCache
from pa_rag.memory import Turn
from pa_rag.models import Answer

Q = "What is the CEO's salary and bonus?"


def _docs(state: AppState, user_id: str, question: str) -> set[str]:
    principal = state.directory.resolve(user_id)
    return {h.chunk.doc_id for h in state.retriever.retrieve(principal, question, k=100)}


# --- response cache ------------------------------------------------------------------


def test_cache_never_crosses_permission_sets(state: AppState) -> None:
    cora, ivy = state.directory.resolve("cora"), state.directory.resolve("ivy")
    first = state.service.ask(cora, Q)
    assert any(c.startswith("exec_comp") for c in first.retrieved_chunk_ids)

    ivy_answer = state.service.ask(ivy, Q)
    assert not ivy_answer.cache_hit
    assert not any(c.startswith("exec_comp") for c in ivy_answer.retrieved_chunk_ids)

    assert state.service.ask(ivy, Q).cache_hit  # same permission set: safe to reuse


def test_any_sharing_change_invalidates_the_cache(state: AppState) -> None:
    hana = state.directory.resolve("hana")
    assert any(c.startswith("exec_comp") for c in state.service.ask(hana, Q).retrieved_chunk_ids)
    state.source.change_sharing("exec_comp_2026.md", ["group:exec"])
    after = state.service.ask(hana, Q)
    assert not after.cache_hit
    assert not any(c.startswith("exec_comp") for c in after.retrieved_chunk_ids)


def test_cache_entries_expire() -> None:
    now = [0.0]
    cache = PermissionScopedCache(ttl_s=10, clock=lambda: now[0])
    cache.put("fp", "q", Answer("a", (), ()))
    assert cache.get("fp", "Q ") is not None  # normalized
    now[0] = 11
    assert cache.get("fp", "q") is None


# --- conversation memory --------------------------------------------------------------


def test_conversations_are_scoped_to_their_owner(state: AppState) -> None:
    cora, ivy = state.directory.resolve("cora"), state.directory.resolve("ivy")
    state.service.ask(cora, Q, conversation_id="conv-1")
    assert state.service.memory.history(cora, "conv-1")
    assert state.service.memory.history(ivy, "conv-1") == []  # guessing the id gets nothing


def test_history_disappears_when_access_is_revoked(state: AppState) -> None:
    hana = state.directory.resolve("hana")
    memory = state.service.memory
    memory.append(hana, "c", Turn("q", "CEO base is 410,000", ("exec_comp_2026.md",)))
    assert len(memory.history(hana, "c")) == 1
    state.source.change_sharing("exec_comp_2026.md", ["group:exec"])
    assert memory.history(hana, "c") == []


# --- ACL drift --------------------------------------------------------------------------


def test_restricted_content_is_checked_live_so_revocation_is_immediate(state: AppState) -> None:
    assert "exec_comp_2026.md" in _docs(state, "hana", Q)
    state.source.change_sharing("exec_comp_2026.md", ["group:exec"])  # no sync has run
    assert "exec_comp_2026.md" not in _docs(state, "hana", Q)


def test_lower_tiers_drift_until_the_sync_runs(state: AppState) -> None:
    question = "platform team reorganisation"
    assert "reorg_plan_draft.md" in _docs(state, "dan", question)

    state.source.change_sharing("reorg_plan_draft.md", ["group:hr"])
    # Confidential content relies on the sync, not a live check: the window is real.
    # This test documents it so the trade-off is a decision, not a surprise.
    assert "reorg_plan_draft.md" in _docs(state, "dan", question)

    report = sync_acls(state.source, state.store)
    assert report.updated == ["reorg_plan_draft.md"]
    assert "reorg_plan_draft.md" not in _docs(state, "dan", question)


def test_sync_removes_deleted_docs_and_flags_reclassified_ones(state: AppState) -> None:
    state.source.remove("incident_postmortem_2026_q3.md")
    state.source.reclassify("eng_onboarding.md", "restricted")
    report = sync_acls(state.source, state.store)
    assert report.removed == ["incident_postmortem_2026_q3.md"]
    assert report.needs_reindex == ["eng_onboarding.md"]
    assert "incident_postmortem_2026_q3.md" not in _docs(state, "erin", "search outage")


def test_group_changes_take_effect_on_the_next_request(state: AppState) -> None:
    assert "reorg_plan_draft.md" in _docs(state, "dan", "reorganisation")
    state.directory.set_groups("dan", {"all-staff", "eng"})  # stepped down as manager
    assert "reorg_plan_draft.md" not in _docs(state, "dan", "reorganisation")
