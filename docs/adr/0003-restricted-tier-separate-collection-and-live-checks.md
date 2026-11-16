# ADR 0003: Separate collection and live ACL checks for restricted content

**Status:** accepted

## Context

A metadata filter is one line of code away from being wrong. For the most sensitive content (executive compensation, board minutes), we want a second, independent barrier, and we want revocation to take effect immediately rather than at the next ACL sync.

## Decision

- Restricted chunks are stored in their own Qdrant collection. The retriever queries it only when the principal has restricted clearance, and the ACL filter still applies inside it.
- For hits at or above `live_check_level` (restricted by default), the retriever re-checks the ACL against the source system at query time and drops the hit if access was revoked.
- Lower tiers rely on `sync_acls`, run on a schedule or from source-system webhooks.

## Consequences

- A user without clearance never issues a query that could touch restricted vectors (tested with a spy on the store).
- Revoking access to a restricted document is immediate (tested).
- Restricted hits cost a source-system lookup each. That's acceptable at restricted volume; lowering `live_check_level` extends immediacy to more content at more cost.
- Reclassifying a document across the boundary means moving its chunks; the sync flags these for re-indexing.
