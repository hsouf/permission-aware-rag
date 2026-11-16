"""The "source system": documents plus their permissions, as a connector would export them.

In production this is a SharePoint / Google Drive / Confluence / Box connector. The
point it demonstrates: the source system is the single source of truth for who can
read what. The index holds a *copy* of those rules, which can go stale (ACL drift),
so the retriever can also ask the source directly for high-sensitivity content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pa_rag.models import Acl, Classification, Document


def _acl_from_manifest(entry: dict[str, Any]) -> Acl:
    return Acl(
        allowed_principals=frozenset(entry["allowed"]),
        classification=Classification.parse(entry["classification"]),
        department=entry.get("department"),
    )


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


class SourceSystem:
    def __init__(self, corpus_dir: Path, manifest: dict[str, Any]) -> None:
        self._corpus_dir = corpus_dir
        self._entries: dict[str, dict[str, Any]] = dict(manifest["documents"])
        self.version: int = int(manifest.get("version", 1))

    @classmethod
    def from_dir(cls, data_dir: Path) -> SourceSystem:
        manifest = json.loads((data_dir / "source_acls.json").read_text())
        return cls(data_dir / "corpus", manifest)

    def documents(self) -> list[Document]:
        docs: list[Document] = []
        for doc_id, entry in sorted(self._entries.items()):
            path = self._corpus_dir / doc_id
            text = path.read_text()
            docs.append(
                Document(
                    doc_id=doc_id,
                    title=_title(text, doc_id),
                    text=text,
                    acl=_acl_from_manifest(entry),
                    source_path=str(path),
                    indexable=bool(entry.get("index", True)),
                )
            )
        return docs

    def current_acl(self, doc_id: str) -> Acl | None:
        """Live permission lookup. ``None`` means the document is gone or unshared."""
        entry = self._entries.get(doc_id)
        return _acl_from_manifest(entry) if entry else None

    def all_acls(self) -> dict[str, Acl]:
        return {doc_id: _acl_from_manifest(e) for doc_id, e in self._entries.items()}

    # --- simulate an admin changing sharing settings in the source system ---
    def change_sharing(self, doc_id: str, allowed: list[str]) -> None:
        self._entries[doc_id] = {**self._entries[doc_id], "allowed": allowed}
        self.version += 1

    def reclassify(self, doc_id: str, classification: str) -> None:
        self._entries[doc_id] = {**self._entries[doc_id], "classification": classification}
        self.version += 1

    def remove(self, doc_id: str) -> None:
        self._entries.pop(doc_id, None)
        self.version += 1
