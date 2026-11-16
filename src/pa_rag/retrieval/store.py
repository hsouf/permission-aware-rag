"""Qdrant wrapper. Every search goes through ``search``, which requires an ACL filter.

There is deliberately no "search without a filter" method on this class. The
anti-pattern versions used in the tests live in ``pa_rag.antipatterns``.

Restricted content lives in its own collection (physical separation). A principal
without restricted clearance never even issues a query against it.
"""

from __future__ import annotations

import uuid
import warnings
from collections.abc import Iterable, Sequence

from qdrant_client import QdrantClient, models

from pa_rag.models import Acl, Chunk, Classification, RetrievedChunk

GENERAL = "general"
RESTRICTED = "restricted"
_ID_NAMESPACE = uuid.UUID("6f0f3c1e-0000-4000-8000-00000000a11c")


def collection_for(acl: Acl) -> str:
    return RESTRICTED if acl.classification >= Classification.RESTRICTED else GENERAL


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, chunk_id))


def acl_filter(subjects: Iterable[str], clearance: Classification) -> models.Filter:
    """The pre-filter: match one of the caller's subjects AND stay within clearance."""
    return models.Filter(
        must=[
            models.FieldCondition(
                key="acl.allowed_principals", match=models.MatchAny(any=sorted(subjects))
            ),
            models.FieldCondition(
                key="acl.classification_level", range=models.Range(lte=int(clearance))
            ),
        ]
    )


def chunk_from_payload(payload: dict[str, object]) -> Chunk:
    acl_payload = payload["acl"]
    assert isinstance(acl_payload, dict)
    return Chunk(
        chunk_id=str(payload["chunk_id"]),
        doc_id=str(payload["doc_id"]),
        title=str(payload["title"]),
        text=str(payload["text"]),
        acl=Acl.from_payload(acl_payload),
        ordinal=int(str(payload["ordinal"])),
    )


class VectorStore:
    def __init__(self, client: QdrantClient, dim: int) -> None:
        self.client = client
        self.dim = dim
        for name in (GENERAL, RESTRICTED):
            if not client.collection_exists(name):
                client.create_collection(
                    name,
                    vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
                )
                # Index the fields we filter on so filtering stays fast at scale.
                # (Embedded mode ignores payload indexes and warns; a server uses them.)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    for field, schema in (
                        ("acl.allowed_principals", models.PayloadSchemaType.KEYWORD),
                        ("acl.classification_level", models.PayloadSchemaType.INTEGER),
                        ("doc_id", models.PayloadSchemaType.KEYWORD),
                    ):
                        client.create_payload_index(name, field, schema)

    @classmethod
    def in_memory(cls, dim: int) -> VectorStore:
        return cls(QdrantClient(":memory:"), dim)

    def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[list[float]]) -> None:
        for chunk, vector in zip(chunks, vectors, strict=True):
            self.client.upsert(
                collection_for(chunk.acl),
                points=[
                    models.PointStruct(
                        id=point_id(chunk.chunk_id),
                        vector=vector,
                        payload={
                            "chunk_id": chunk.chunk_id,
                            "doc_id": chunk.doc_id,
                            "title": chunk.title,
                            "text": chunk.text,
                            "ordinal": chunk.ordinal,
                            "acl": chunk.acl.to_payload(),
                        },
                    )
                ],
            )

    def search(
        self,
        collection: str,
        vector: list[float],
        subjects: Iterable[str],
        clearance: Classification,
        limit: int,
    ) -> list[RetrievedChunk]:
        response = self.client.query_points(
            collection,
            query=vector,
            query_filter=acl_filter(subjects, clearance),
            limit=limit,
            with_payload=True,
        )
        return [
            RetrievedChunk(chunk_from_payload(p.payload or {}), p.score, collection)
            for p in response.points
        ]

    def doc_filter(self, doc_id: str) -> models.Filter:
        return models.Filter(
            must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))]
        )

    def set_acl(self, doc_id: str, acl: Acl) -> None:
        for name in (GENERAL, RESTRICTED):
            self.client.set_payload(name, {"acl": acl.to_payload()}, points=self.doc_filter(doc_id))

    def delete_doc(self, doc_id: str) -> None:
        for name in (GENERAL, RESTRICTED):
            self.client.delete(
                name, points_selector=models.FilterSelector(filter=self.doc_filter(doc_id))
            )

    def indexed_acls(self) -> dict[str, Acl]:
        """doc_id -> ACL as currently stored in the index (used by the drift sync)."""
        found: dict[str, Acl] = {}
        for name in (GENERAL, RESTRICTED):
            for chunk in self.all_chunks(name):
                found[chunk.doc_id] = chunk.acl
        return found

    def all_chunks(self, collection: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        offset = None
        while True:
            records, offset = self.client.scroll(
                collection, limit=256, offset=offset, with_payload=True
            )
            chunks += [chunk_from_payload(r.payload or {}) for r in records]
            if offset is None:
                return chunks
