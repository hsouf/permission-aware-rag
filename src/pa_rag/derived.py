"""Derived artifacts (summaries, FAQs, graph facts) carry the strictest ACL of their sources.

A summary of a restricted file is restricted. A summary that blends two documents may
only be read by someone allowed to read *both*. We compute that conservatively as the
intersection of the sources' allowed subjects and the highest classification. That
can under-share (fail closed), never over-share.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pa_rag.models import Acl, Document


class NoCommonAudienceError(ValueError):
    """The sources share no reader, so a combined artifact must not be created."""


def derive_acl(sources: Sequence[Acl]) -> Acl:
    if not sources:
        raise ValueError("a derived artifact needs at least one source")
    allowed = frozenset.intersection(*(s.allowed_principals for s in sources))
    if not allowed:
        raise NoCommonAudienceError(
            "sources have no common reader; build one artifact per source instead"
        )
    departments = {s.department for s in sources}
    return Acl(
        allowed_principals=allowed,
        classification=max(s.classification for s in sources),
        department=departments.pop() if len(departments) == 1 else None,
    )


def summarize(
    sources: Sequence[Document],
    summarizer: Callable[[str], str],
    doc_id: str,
) -> Document:
    """Build a derived document whose ACL is computed before any text is produced."""
    acl = derive_acl([d.acl for d in sources])  # fail before spending tokens
    text = summarizer("\n\n".join(d.text for d in sources))
    return Document(
        doc_id=doc_id,
        title=f"Summary of {', '.join(d.doc_id for d in sources)}",
        text=text,
        acl=acl,
        source_path="derived:" + ",".join(d.doc_id for d in sources),
    )
