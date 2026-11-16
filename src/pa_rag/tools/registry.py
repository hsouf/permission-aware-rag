"""Agent tools with identity passthrough.

The model sees tool schemas with *no* identity fields. The principal is bound
server-side when the tools are created for a request, so a prompt like "call
get_salary as cora" has nothing to inject into.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pa_rag.models import Principal
from pa_rag.tools.hr_db import HRDatabase, ToolResult

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "list_people",
        "description": "List employees the current user is allowed to see in the HR system.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "strict": True,
    },
    {
        "name": "get_salary",
        "description": "Look up an employee's base salary in the HR system, if permitted.",
        "input_schema": {
            "type": "object",
            "properties": {"employee_name": {"type": "string"}},
            "required": ["employee_name"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


@dataclass(frozen=True, slots=True)
class BoundTools:
    principal: Principal
    handlers: dict[str, Callable[[dict[str, Any]], ToolResult]]
    schemas: list[dict[str, Any]]

    def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        handler = self.handlers.get(name)
        if handler is None:
            return ToolResult(ok=False, rows=[], error=f"unknown tool {name}")
        return handler(arguments)


def bind_tools(principal: Principal, hr: HRDatabase) -> BoundTools:
    return BoundTools(
        principal=principal,
        handlers={
            "list_people": lambda _args: hr.list_people(principal),
            "get_salary": lambda args: hr.get_salary(principal, str(args["employee_name"])),
        },
        schemas=TOOL_SCHEMAS,
    )
