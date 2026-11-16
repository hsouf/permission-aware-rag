"""HR database tool: queries run as the end user, enforced by Postgres RLS.

Why not text-to-SQL here? If the model can send arbitrary SQL over this connection,
it can also send ``RESET ROLE`` / ``SET ROLE rag_hr_comp`` and escape. Fixed,
parameterized queries close that door. If you need free-form SQL, give each user
(or each permission tier) its own *login* role instead of ``SET ROLE``, so there is
nothing to escalate to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql

from pa_rag.models import Principal

HR_COMP_GROUPS = frozenset({"hr-comp", "exec"})


@dataclass(frozen=True, slots=True)
class ToolResult:
    ok: bool
    rows: list[dict[str, Any]]
    error: str | None = None


def db_role_for(principal: Principal) -> str:
    """Map directory groups to a database role. Least privilege by default."""
    return "rag_hr_comp" if principal.groups & HR_COMP_GROUPS else "rag_employee"


class HRDatabase:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _run(
        self, principal: Principal, query: sql.SQL | sql.Composed, params: tuple[Any, ...]
    ) -> ToolResult:
        try:
            with psycopg.connect(self._dsn) as conn, conn.transaction(), conn.cursor() as cur:
                # Both settings are transaction-scoped (LOCAL): nothing leaks to the
                # next request that reuses this connection from a pool.
                cur.execute(
                    sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(db_role_for(principal)))
                )
                cur.execute("SELECT set_config('app.user_id', %s, true)", (principal.user_id,))
                cur.execute(query, params)
                columns = [d.name for d in cur.description or []]
                rows = [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
            return ToolResult(ok=True, rows=rows)
        except psycopg.errors.InsufficientPrivilege:
            return ToolResult(ok=False, rows=[], error="access denied by database policy")

    def list_people(self, principal: Principal) -> ToolResult:
        """Directory info the caller may see (self + direct reports, or everyone for HR comp)."""
        return self._run(
            principal,
            sql.SQL(
                "SELECT employee_id, full_name, title, department, manager_id "
                "FROM compensation ORDER BY employee_id"
            ),
            (),
        )

    def get_salary(self, principal: Principal, employee_name: str) -> ToolResult:
        return self._run(
            principal,
            sql.SQL(
                "SELECT employee_id, full_name, base_salary FROM compensation "
                "WHERE lower(full_name) = lower(%s)"
            ),
            (employee_name,),
        )
