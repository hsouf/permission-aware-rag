"""The request pipeline: identity -> cache -> secure retrieval -> memory -> generation -> audit."""

from __future__ import annotations

import json
import logging
from dataclasses import replace

from pa_rag.authz.base import Authorizer
from pa_rag.cache import PermissionScopedCache, permission_fingerprint
from pa_rag.ingest.sources import SourceSystem
from pa_rag.llm import Generator
from pa_rag.memory import ConversationStore, Turn
from pa_rag.models import Answer, Principal
from pa_rag.retrieval.retriever import SecureRetriever
from pa_rag.tools.hr_db import HRDatabase
from pa_rag.tools.registry import bind_tools

audit = logging.getLogger("pa_rag.audit")


class AskService:
    def __init__(
        self,
        retriever: SecureRetriever,
        authorizer: Authorizer,
        source: SourceSystem,
        cache: PermissionScopedCache,
        memory: ConversationStore,
        generator: Generator,
        hr: HRDatabase | None = None,
        k: int = 5,
    ) -> None:
        self._retriever = retriever
        self._authorizer = authorizer
        self._source = source
        self._cache = cache
        self._memory = memory
        self._generator = generator
        self._hr = hr
        self._k = k

    @property
    def memory(self) -> ConversationStore:
        return self._memory

    def ask(
        self, principal: Principal, question: str, conversation_id: str | None = None
    ) -> Answer:
        fingerprint = permission_fingerprint(principal, self._authorizer, self._source.version)
        if conversation_id is None:
            cached = self._cache.get(fingerprint, question)
            if cached is not None:
                self._audit(principal, cached, cache_hit=True)
                return replace(cached, cache_hit=True)

        hits = self._retriever.retrieve(principal, question, self._k)
        history = self._memory.history(principal, conversation_id) if conversation_id else []
        tools = bind_tools(principal, self._hr) if self._hr else None
        generated = self._generator.generate(question, hits, history, tools)

        chunk_ids = tuple(h.chunk.chunk_id for h in hits)
        answer = Answer(
            text=generated.text,
            citations=chunk_ids,
            retrieved_chunk_ids=chunk_ids,
            tool_calls=generated.tool_calls,
        )
        if conversation_id:
            doc_ids = tuple(dict.fromkeys(h.chunk.doc_id for h in hits))
            self._memory.append(principal, conversation_id, Turn(question, answer.text, doc_ids))
        else:
            self._cache.put(fingerprint, question, answer)
        self._audit(principal, answer, cache_hit=False)
        return answer

    @staticmethod
    def _audit(principal: Principal, answer: Answer, cache_hit: bool) -> None:
        # IDs only. Logs are a side door too: never write question text, answers or
        # chunk content into a log stream with broader access than the data itself.
        audit.info(
            json.dumps(
                {
                    "event": "ask",
                    "user": principal.user_id,
                    "chunks": list(answer.retrieved_chunk_ids),
                    "tools": list(answer.tool_calls),
                    "cache_hit": cache_hit,
                }
            )
        )
