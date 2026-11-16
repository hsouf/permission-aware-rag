"""DO NOT USE. Deliberately broken patterns, kept so tests can prove how they fail.

Each class here is a mistake that shows up in real RAG systems. The test suite runs
them next to the secure versions to show the difference.
"""

from __future__ import annotations

from qdrant_client import models

from pa_rag.authz.base import Authorizer
from pa_rag.embeddings import Embedder
from pa_rag.models import Answer, Principal, RetrievedChunk
from pa_rag.retrieval.store import GENERAL, RESTRICTED, VectorStore, chunk_from_payload


class PostFilterRetriever:
    """Anti-pattern: retrieve top-k from everything, then drop what the user can't see.

    Problems: (1) restricted content was already retrieved into application memory,
    one bug away from the prompt; (2) when the top-k is dominated by forbidden chunks,
    the user gets nothing useful back even though permitted matches exist.
    """

    def __init__(self, store: VectorStore, embedder: Embedder, authorizer: Authorizer) -> None:
        self._store = store
        self._embedder = embedder
        self._authorizer = authorizer

    def retrieve(self, principal: Principal, question: str, k: int = 5) -> list[RetrievedChunk]:
        vector = self._embedder.embed(question)
        hits: list[RetrievedChunk] = []
        for collection in (GENERAL, RESTRICTED):
            response = self._store.client.query_points(
                collection, query=vector, limit=k, with_payload=True
            )
            hits += [
                RetrievedChunk(chunk_from_payload(p.payload or {}), p.score, collection)
                for p in response.points
            ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return [h for h in hits[:k] if self._authorizer.can_read(principal, h.chunk.acl)]


class UnfilteredRetriever:
    """Anti-pattern: no ACL filter at all; relies on the system prompt to keep secrets."""

    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder

    def retrieve(self, principal: Principal, question: str, k: int = 5) -> list[RetrievedChunk]:
        vector = self._embedder.embed(question)
        hits: list[RetrievedChunk] = []
        for collection in (GENERAL, RESTRICTED):
            response = self._store.client.query_points(
                collection,
                query=vector,
                limit=k,
                with_payload=True,
                query_filter=models.Filter(must=[]),
            )
            hits += [
                RetrievedChunk(chunk_from_payload(p.payload or {}), p.score, collection)
                for p in response.points
            ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]


class QuestionKeyedCache:
    """Anti-pattern: a semantic/response cache shared by every user."""

    def __init__(self) -> None:
        self._entries: dict[str, Answer] = {}

    def get(self, question: str) -> Answer | None:
        return self._entries.get(" ".join(question.lower().split()))

    def put(self, question: str, answer: Answer) -> None:
        self._entries[" ".join(question.lower().split())] = answer
