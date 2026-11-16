"""Ground truth for "who may read which document", computed independently of pa_rag.

The adversarial tests compare the retriever against this oracle. It reads the raw
JSON files and re-implements the rule in the simplest possible way, so a bug in the
production authorizer cannot hide by also being present in the expected values.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
LEVELS = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}


def _load() -> tuple[dict[str, dict], dict[str, dict], dict[str, str]]:
    directory = json.loads((DATA / "directory.json").read_text())
    manifest = json.loads((DATA / "source_acls.json").read_text())
    users = {u["id"]: u for u in directory["users"]}
    return users, manifest["documents"], directory["clearance_by_group"]


def readable_docs(user_id: str) -> set[str]:
    users, docs, clearance_by_group = _load()
    user = users[user_id]
    clearance = max(LEVELS[clearance_by_group.get(g, "public")] for g in user["groups"])
    subjects = {f"user:{user_id}"} | {f"group:{g}" for g in user["groups"]}
    subjects |= {f"manager-of:{u['id']}" for u in users.values() if u.get("manager") == user_id}
    return {
        doc_id
        for doc_id, entry in docs.items()
        if subjects & set(entry["allowed"]) and LEVELS[entry["classification"]] <= clearance
    }


def all_docs() -> set[str]:
    return set(_load()[1])


def forbidden_docs(user_id: str) -> set[str]:
    return all_docs() - readable_docs(user_id)


def user_ids() -> list[str]:
    return list(_load()[0])
