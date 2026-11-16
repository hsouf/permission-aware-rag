"""Wire the components together from settings."""

from __future__ import annotations

from dataclasses import dataclass

from pa_rag.auth.directory import Directory
from pa_rag.auth.tokens import TokenVerifier
from pa_rag.authz.rebac import RelationshipAuthorizer
from pa_rag.cache import PermissionScopedCache
from pa_rag.config import Settings
from pa_rag.embeddings import HashingEmbedder
from pa_rag.ingest.pipeline import Indexer, IndexReport
from pa_rag.ingest.sources import SourceSystem
from pa_rag.llm import ClaudeGenerator, ContextOnlyGenerator, Generator
from pa_rag.memory import ConversationStore
from pa_rag.retrieval.retriever import SecureRetriever
from pa_rag.retrieval.store import VectorStore
from pa_rag.service import AskService
from pa_rag.tools.hr_db import HRDatabase


@dataclass
class AppState:
    settings: Settings
    directory: Directory
    verifier: TokenVerifier
    source: SourceSystem
    store: VectorStore
    authorizer: RelationshipAuthorizer
    retriever: SecureRetriever
    service: AskService
    index_report: IndexReport


def build(settings: Settings, generator: Generator | None = None) -> AppState:
    directory = Directory.from_file(settings.data_dir / "directory.json")
    source = SourceSystem.from_dir(settings.data_dir)
    embedder = HashingEmbedder()
    store = VectorStore.in_memory(embedder.dim)
    report = Indexer(store, embedder).index(source.documents())

    authorizer = RelationshipAuthorizer()
    retriever = SecureRetriever(store, embedder, authorizer, source)
    if generator is None:
        generator = (
            ClaudeGenerator(settings.anthropic_model)
            if settings.llm == "claude"
            else ContextOnlyGenerator()
        )
    service = AskService(
        retriever=retriever,
        authorizer=authorizer,
        source=source,
        cache=PermissionScopedCache(),
        memory=ConversationStore(source, authorizer),
        generator=generator,
        hr=HRDatabase(settings.database_url) if settings.database_url else None,
    )
    verifier = TokenVerifier(settings.jwt_secret, settings.jwt_issuer, settings.jwt_audience)
    return AppState(
        settings, directory, verifier, source, store, authorizer, retriever, service, report
    )
