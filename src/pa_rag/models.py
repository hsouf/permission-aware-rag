"""Core domain types.

Two ideas carry the whole design:

* ``Principal`` is *who is asking*. It is only ever built from a verified token
  plus the directory, never from anything in the request body or the prompt.
* ``Acl`` travels with every piece of content: documents, chunks, derived
  summaries, cached answers and conversation memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class Classification(IntEnum):
    """Ordered sensitivity levels. Higher is more sensitive."""

    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3

    @classmethod
    def parse(cls, value: str) -> Classification:
        return cls[value.upper()]


@dataclass(frozen=True, slots=True)
class Acl:
    """Access rules attached to a document and inherited by everything derived from it.

    ``allowed_principals`` holds typed subject strings, mirroring how systems such as
    OpenFGA or SpiceDB name subjects:

    * ``group:eng``       members of a directory group
    * ``user:erin``       one specific user
    * ``manager-of:erin`` whoever is erin's manager (a relationship, resolved at query time)
    """

    allowed_principals: frozenset[str]
    classification: Classification
    department: str | None = None

    def __post_init__(self) -> None:
        if not self.allowed_principals:
            # An empty ACL would be readable by nobody; that is almost always an ingestion
            # bug (lost permissions), so refuse it loudly instead of indexing dead data.
            raise ValueError("ACL must name at least one principal")

    def to_payload(self) -> dict[str, Any]:
        return {
            "allowed_principals": sorted(self.allowed_principals),
            "classification": self.classification.name.lower(),
            "classification_level": int(self.classification),
            "department": self.department,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Acl:
        return cls(
            allowed_principals=frozenset(payload["allowed_principals"]),
            classification=Classification.parse(payload["classification"]),
            department=payload.get("department"),
        )


@dataclass(frozen=True, slots=True)
class Principal:
    """An authenticated caller, fully resolved against the directory."""

    user_id: str
    groups: frozenset[str]
    clearance: Classification
    direct_reports: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class Document:
    doc_id: str
    title: str
    text: str
    acl: Acl
    source_path: str
    indexable: bool = True


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    text: str
    acl: Acl
    ordinal: int


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk: Chunk
    score: float
    collection: str


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    citations: tuple[str, ...]
    retrieved_chunk_ids: tuple[str, ...]
    cache_hit: bool = False
    tool_calls: tuple[str, ...] = field(default_factory=tuple)
