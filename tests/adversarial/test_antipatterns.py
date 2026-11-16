"""Proof that the common shortcuts fail, run against the same index and data."""

from __future__ import annotations

from pa_rag.antipatterns import PostFilterRetriever, QuestionKeyedCache, UnfilteredRetriever
from pa_rag.bootstrap import AppState
from pa_rag.embeddings import HashingEmbedder
from tests import oracle

QUESTION = "What is the CEO's salary and bonus?"


def test_prompt_only_security_puts_restricted_chunks_in_context(shared_state: AppState) -> None:
    ivy = shared_state.directory.resolve("ivy")
    hits = UnfilteredRetriever(shared_state.store, HashingEmbedder()).retrieve(ivy, QUESTION)
    leaked = {h.chunk.doc_id for h in hits} & oracle.forbidden_docs("ivy")
    assert "exec_comp_2026.md" in leaked  # the system prompt is all that's left


def test_post_filtering_starves_results_that_pre_filtering_finds(shared_state: AppState) -> None:
    ivy = shared_state.directory.resolve("ivy")
    post = PostFilterRetriever(
        shared_state.store, HashingEmbedder(), shared_state.authorizer
    ).retrieve(ivy, QUESTION, k=3)
    pre = shared_state.retriever.retrieve(ivy, QUESTION, k=3)
    assert len(pre) == 3
    assert len(post) < len(pre)  # forbidden chunks took the top-k slots, then got dropped


def test_question_keyed_cache_serves_the_ceos_answer_to_the_intern(shared_state: AppState) -> None:
    cache = QuestionKeyedCache()
    cora = shared_state.directory.resolve("cora")
    cache.put(QUESTION, shared_state.service.ask(cora, QUESTION))
    served_to_ivy = cache.get(QUESTION)
    assert served_to_ivy is not None
    assert any(c.startswith("exec_comp_2026.md") for c in served_to_ivy.retrieved_chunk_ids)
