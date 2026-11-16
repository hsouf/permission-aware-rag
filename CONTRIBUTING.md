# Contributing

Issues and pull requests are welcome. The bar is simple: **no change may widen what a user can retrieve unless a test says it should.**

## Setup

```bash
make install           # creates .venv and installs the package with dev tools
pre-commit install     # optional: ruff and gitleaks on every commit
make check             # ruff, mypy --strict and the test suite, the same gates as CI
make test-integration  # Postgres row-level security tests (needs Docker)
```

## Ground rules

- **Fix a leak by adding the attack first.** Add a failing case to `tests/adversarial/` that shows the leak, then fix it. The suite compares every user's reachable set against the independent oracle in `tests/oracle.py`, so don't change the oracle and the code in the same commit without explaining why.
- **Identity only comes from the verified token and the directory.** No new code path may read a user ID, group or role from a request body, a prompt or a tool argument.
- **Anything derived from a document keeps an ACL**: summaries, cache entries, memory, embeddings and logs. If you add a new kind of derived data, add a test that a lower-privileged user can't reach it.
- **Fail closed.** Missing ACLs, unknown users and unreachable authorization backends deny access.
- **Logs hold IDs, not content.**
- Keep `ruff`, `mypy --strict` and coverage (85% minimum) green.

## Reporting a vulnerability

Don't open a public issue for a way to bypass access control. Follow [SECURITY.md](SECURITY.md) instead.
