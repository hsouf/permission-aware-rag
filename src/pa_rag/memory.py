"""Conversation memory scoped to the user and re-authorized on every read.

* Keyed by (user_id, conversation_id): knowing someone else's conversation id gets you
  nothing.
* Each turn records which documents fed it. On read, a turn is shown only if the user
  can *still* read all of them per the source system. Lose access, lose the history
  that quoted it.
"""

from __future__ import annotations

from dataclasses import dataclass

from pa_rag.authz.base import Authorizer
from pa_rag.ingest.sources import SourceSystem
from pa_rag.models import Principal


@dataclass(frozen=True, slots=True)
class Turn:
    question: str
    answer: str
    source_doc_ids: tuple[str, ...]


class ConversationStore:
    def __init__(self, source: SourceSystem, authorizer: Authorizer) -> None:
        self._source = source
        self._authorizer = authorizer
        self._turns: dict[tuple[str, str], list[Turn]] = {}

    def append(self, principal: Principal, conversation_id: str, turn: Turn) -> None:
        self._turns.setdefault((principal.user_id, conversation_id), []).append(turn)

    def history(self, principal: Principal, conversation_id: str) -> list[Turn]:
        turns = self._turns.get((principal.user_id, conversation_id), [])
        return [t for t in turns if self._still_readable(principal, t)]

    def _still_readable(self, principal: Principal, turn: Turn) -> bool:
        for doc_id in turn.source_doc_ids:
            acl = self._source.current_acl(doc_id)
            if acl is None or not self._authorizer.can_read(principal, acl):
                return False
        return True
