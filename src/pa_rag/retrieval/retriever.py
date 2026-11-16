"""The secure retriever: the only path from the index to the LLM context."""

from __future__ import annotations

import logging

from pa_rag.authz.base import Authorizer
from pa_rag.embeddings import Embedder
from pa_rag.errors import AccessViolation
from pa_rag.ingest.sources import SourceSystem
from pa_rag.models import Classification, Principal, RetrievedChunk
from pa_rag.retrieval.store import GENERAL, RESTRICTED, VectorStore

log = logging.getLogger("pa_rag.retrieval")


class SecureRetriever:
    """Pre-filters by the caller's identity, then verifies every result again.

    1. ``subjects`` come from the authorizer, computed from the verified principal.
       The question text plays no part in the filter.
    2. The restricted collection is queried only with restricted clearance.
    3. Every hit is re-checked with ``can_read``. A failure here means the filter is
       broken, so the request fails rather than leaking (``AccessViolation``).
    4. Hits at or above ``live_check_level`` are re-checked against the source system,
       which closes the ACL-drift window for the most sensitive content.
    """

    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        authorizer: Authorizer,
        source: SourceSystem,
        live_check_level: Classification = Classification.RESTRICTED,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._authorizer = authorizer
        self._source = source
        self._live_check_level = live_check_level

    def retrieve(self, principal: Principal, question: str, k: int = 5) -> list[RetrievedChunk]:
        subjects = self._authorizer.subjects(principal)
        vector = self._embedder.embed(question)

        collections = [GENERAL]
        if principal.clearance >= Classification.RESTRICTED:
            collections.append(RESTRICTED)

        hits: list[RetrievedChunk] = []
        for collection in collections:
            hits += self._store.search(collection, vector, subjects, principal.clearance, k)
        hits.sort(key=lambda h: h.score, reverse=True)

        verified: list[RetrievedChunk] = []
        for hit in hits[:k]:
            if not self._authorizer.can_read(principal, hit.chunk.acl):
                raise AccessViolation(
                    f"pre-filter returned {hit.chunk.chunk_id} to {principal.user_id}"
                )
            if hit.chunk.acl.classification >= self._live_check_level:
                live = self._source.current_acl(hit.chunk.doc_id)
                if live is None or not self._authorizer.can_read(principal, live):
                    log.warning(
                        "dropped stale chunk %s for %s: access revoked at source",
                        hit.chunk.chunk_id,
                        principal.user_id,
                    )
                    continue
            verified.append(hit)
        return verified
