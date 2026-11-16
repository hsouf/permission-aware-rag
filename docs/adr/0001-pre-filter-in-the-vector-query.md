# ADR 0001: Pre-filter in the vector query

**Status:** accepted

## Context

Retrieval must return only chunks the caller may read. There are three options: no filter (rely on the system prompt), post-filter (retrieve top-k from everything, then drop forbidden hits), or pre-filter (pass the caller's permissions as a metadata filter, so forbidden chunks are never candidates).

## Decision

Pre-filter in the vector query, using the caller's resolved subjects (`user:`, `group:`, `manager-of:`) and clearance. The store exposes no unfiltered search. Every hit is re-checked with the authorizer; a failed check raises `AccessViolation` and fails the request.

## Consequences

- Forbidden content never enters application memory on the request path.
- Result quality doesn't degrade when most of the corpus is restricted (post-filtering starves; see `test_antipatterns.py`).
- The ACL fields must be indexed in the vector DB to keep filtered search fast, and the engine must apply the filter during the ANN search (true for Qdrant; needs care with pgvector, see the best practices guide).
- The re-check makes a filter bug loud (failed request) instead of silent (missing or leaked results).
