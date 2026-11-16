"""Chunking that can never strip a document's protection.

Every chunk receives the parent document's ``Acl`` object unchanged. There is no
code path that builds a chunk without one, and ``Acl`` itself refuses to be empty.
A property-based test checks this over arbitrary documents.
"""

from __future__ import annotations

import re

from pa_rag.models import Chunk, Document

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def _pieces(text: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    for para in _PARAGRAPH_SPLIT.split(text):
        para = para.strip()
        while len(para) > max_chars:  # hard-split very long paragraphs
            pieces.append(para[:max_chars])
            para = para[max_chars:].strip()
        if para:
            pieces.append(para)
    return pieces


def chunk_document(doc: Document, max_chars: int = 400) -> list[Chunk]:
    if max_chars < 50:
        raise ValueError("max_chars too small to be useful")
    chunks: list[Chunk] = []
    buffer = ""
    for piece in _pieces(doc.text, max_chars):
        candidate = f"{buffer}\n\n{piece}" if buffer else piece
        if len(candidate) <= max_chars:
            buffer = candidate
            continue
        if buffer:
            chunks.append(_make(doc, buffer, len(chunks)))
        buffer = piece
    if buffer:
        chunks.append(_make(doc, buffer, len(chunks)))
    return chunks


def _make(doc: Document, text: str, ordinal: int) -> Chunk:
    return Chunk(
        chunk_id=f"{doc.doc_id}#{ordinal}",
        doc_id=doc.doc_id,
        title=doc.title,
        text=text,
        acl=doc.acl,  # inherited verbatim: same object, same rules
        ordinal=ordinal,
    )
