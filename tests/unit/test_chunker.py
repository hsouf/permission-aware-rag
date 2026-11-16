from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pa_rag.ingest.chunker import chunk_document
from pa_rag.models import Acl, Classification, Document

subjects = st.sampled_from(
    ["group:eng", "group:exec", "group:hr", "user:ivy", "manager-of:erin", "group:all-staff"]
)
acls = st.builds(
    Acl,
    allowed_principals=st.frozensets(subjects, min_size=1),
    classification=st.sampled_from(list(Classification)),
    department=st.one_of(st.none(), st.sampled_from(["hr", "eng"])),
)
texts = st.lists(st.text(min_size=0, max_size=900), max_size=8).map("\n\n".join)


@given(text=texts, acl=acls, max_chars=st.integers(min_value=50, max_value=600))
def test_every_chunk_inherits_exactly_the_parent_acl(text: str, acl: Acl, max_chars: int) -> None:
    doc = Document("doc.md", "Doc", text, acl, "doc.md")
    chunks = chunk_document(doc, max_chars=max_chars)

    assert all(c.acl == acl for c in chunks)  # never stripped, never widened
    assert all(c.doc_id == "doc.md" for c in chunks)
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert all(len(c.text) <= max_chars for c in chunks)


@given(text=texts, acl=acls)
def test_chunking_loses_no_content(text: str, acl: Acl) -> None:
    doc = Document("doc.md", "Doc", text, acl, "doc.md")
    rebuilt = "".join(c.text for c in chunk_document(doc))
    assert "".join(rebuilt.split()) == "".join(text.split())


def test_an_empty_acl_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one principal"):
        Acl(frozenset(), Classification.INTERNAL)
