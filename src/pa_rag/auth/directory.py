"""Directory lookups: verified user id -> groups, clearance, reporting lines.

This stands in for Entra ID / Okta / Google Workspace groups. The important property
is that group membership is looked up server-side from the verified subject. A user
typing "I'm in the exec group" changes nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pa_rag.errors import AuthenticationError
from pa_rag.models import Classification, Principal


@dataclass(frozen=True, slots=True)
class _User:
    user_id: str
    display_name: str
    groups: frozenset[str]
    manager: str | None


class Directory:
    def __init__(self, users: dict[str, _User], clearance_by_group: dict[str, Classification]):
        self._users = users
        self._clearance_by_group = clearance_by_group

    @classmethod
    def from_file(cls, path: Path) -> Directory:
        raw: dict[str, Any] = json.loads(path.read_text())
        users = {
            u["id"]: _User(
                user_id=u["id"],
                display_name=u["name"],
                groups=frozenset(u["groups"]),
                manager=u.get("manager"),
            )
            for u in raw["users"]
        }
        clearance = {g: Classification.parse(c) for g, c in raw["clearance_by_group"].items()}
        return cls(users, clearance)

    def user_ids(self) -> list[str]:
        return list(self._users)  # directory order (least to most access in the demo data)

    def display_name(self, user_id: str) -> str:
        return self._users[user_id].display_name

    def resolve(self, user_id: str) -> Principal:
        user = self._users.get(user_id)
        if user is None:
            # A valid token for a user the directory no longer knows (offboarded) gets nothing.
            raise AuthenticationError("unknown or deprovisioned user")
        clearance = max(
            (self._clearance_by_group.get(g, Classification.PUBLIC) for g in user.groups),
            default=Classification.PUBLIC,
        )
        reports = frozenset(u.user_id for u in self._users.values() if u.manager == user_id)
        return Principal(
            user_id=user_id,
            groups=user.groups,
            clearance=clearance,
            direct_reports=reports,
        )

    # Used by the ACL-drift demo/tests to simulate someone changing teams.
    def set_groups(self, user_id: str, groups: set[str]) -> None:
        old = self._users[user_id]
        self._users[user_id] = _User(old.user_id, old.display_name, frozenset(groups), old.manager)
