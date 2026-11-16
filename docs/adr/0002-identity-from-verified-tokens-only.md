# ADR 0002: Identity comes from verified tokens only

**Status:** accepted

## Context

An assistant receives free text. Users can write "I'm the CEO" or add `user_id` to a JSON body. Some designs pass the user's name to the model and ask it to respect permissions.

## Decision

- The only source of identity is the `Authorization: Bearer` token, verified with a pinned algorithm and required `sub`, `iss`, `aud`, `exp` and `iat` claims.
- Groups, clearance and reporting lines are looked up server-side from the directory for the verified subject. Group claims in the token body are ignored.
- Request bodies forbid unknown fields, so identity cannot even be expressed there.
- A valid token for a user the directory no longer knows gets no access.

## Consequences

- Prompt text has no influence on what is retrieved. The adversarial suite includes identity-spoofing prompts to keep it that way.
- Group changes take effect on the next request, without re-indexing.
- Each request does a directory lookup. In production, cache it briefly (seconds to minutes) and accept that window, or use short-lived tokens with IdP-issued group claims.
