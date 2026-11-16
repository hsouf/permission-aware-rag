"""Ingestion: policy check -> chunk (inherit ACL) -> embed -> upsert with ACL payload."""

from __future__ import annotations

from dataclasses import dataclass, field

from pa_rag.embeddings import Embedder
from pa_rag.ingest.chunker import chunk_document
from pa_rag.ingest.policy import IndexingPolicy
from pa_rag.models import Document
from pa_rag.retrieval.store import VectorStore


@dataclass
class IndexReport:
    indexed: dict[str, int] = field(default_factory=dict)  # doc_id -> chunk count
    skipped: dict[str, str] = field(default_factory=dict)  # doc_id -> reason


class Indexer:
    def __init__(
        self, store: VectorStore, embedder: Embedder, policy: IndexingPolicy | None = None
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._policy = policy or IndexingPolicy()

    def index(self, documents: list[Document]) -> IndexReport:
        report = IndexReport()
        for doc in documents:
            allowed, reason = self._policy.decide(doc)
            if not allowed:
                report.skipped[doc.doc_id] = reason
                continue
            chunks = chunk_document(doc)
            # Embed title + text so a chunk keeps its document context.
            vectors = [self._embedder.embed(f"{c.title}\n{c.text}") for c in chunks]
            self._store.upsert(chunks, vectors)
            report.indexed[doc.doc_id] = len(chunks)
        return report
