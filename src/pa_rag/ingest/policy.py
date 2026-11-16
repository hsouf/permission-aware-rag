"""Data minimization: the safest restricted chunk is the one you never indexed."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pa_rag.models import Document

# Content patterns that should never land in a general-purpose index, whatever the ACL.
DEFAULT_DENY_PATTERNS = (
    re.compile(r"\bbank_last4\b|\biban\b|\brouting number\b", re.IGNORECASE),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN shape
)


@dataclass(frozen=True, slots=True)
class IndexingPolicy:
    deny_patterns: tuple[re.Pattern[str], ...] = field(default=DEFAULT_DENY_PATTERNS)

    def decide(self, doc: Document) -> tuple[bool, str]:
        if not doc.indexable:
            return False, "excluded by source manifest (index: false)"
        for pattern in self.deny_patterns:
            if pattern.search(doc.text):
                return False, f"matched deny pattern {pattern.pattern!r}"
        return True, "ok"
