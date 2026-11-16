"""ACL drift: keep the index's copy of permissions in step with the source system.

Run this on a schedule (or from source-system change webhooks). Between runs, the
retriever's live check covers restricted content.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pa_rag.ingest.sources import SourceSystem
from pa_rag.retrieval.store import VectorStore, collection_for


@dataclass
class SyncReport:
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    needs_reindex: list[str] = field(default_factory=list)


def sync_acls(source: SourceSystem, store: VectorStore) -> SyncReport:
    report = SyncReport()
    truth = source.all_acls()
    for doc_id, indexed_acl in store.indexed_acls().items():
        current = truth.get(doc_id)
        if current is None:
            store.delete_doc(doc_id)
            report.removed.append(doc_id)
        elif current != indexed_acl:
            if collection_for(current) != collection_for(indexed_acl):
                # Crossed the restricted boundary: the chunks must move collections.
                store.delete_doc(doc_id)
                report.needs_reindex.append(doc_id)
            else:
                store.set_acl(doc_id, current)
                report.updated.append(doc_id)
    return report
