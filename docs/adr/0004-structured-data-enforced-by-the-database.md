# ADR 0004: Structured data is enforced by the database

**Status:** accepted

## Context

Salaries and reporting lines live in a relational HR database. Options: export them into the vector index, query through a shared service account and filter in the app, or have the database enforce access for the end user.

## Decision

- Don't index HR records into the vector store.
- The app connects as `rag_gateway`, a `NOINHERIT` login role with no data privileges. For each request it runs `SET LOCAL ROLE` (the role mapped from the user's groups) and `set_config('app.user_id', <verified id>, true)`, both transaction-scoped.
- Row-level security limits rows (self and direct reports, or everyone for HR comp). Policies match nothing if the user id is missing.
- Column privileges keep `base_salary` from ordinary employees, including managers.
- The model gets fixed, parameterized tools (`list_people`, `get_salary`), never free-form SQL.

## Consequences

- An application bug cannot widen access: the database refuses.
- `SET ROLE` is not a boundary against arbitrary SQL on the same connection (`RESET ROLE` undoes it). A test demonstrates this. If text-to-SQL is ever required, switch to per-user or per-tier login roles on a read-only replica.
- New questions about HR data need new tools rather than new prompts. That is intentional.
