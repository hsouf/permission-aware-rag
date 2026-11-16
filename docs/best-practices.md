# Permission-aware RAG: best practices

This guide explains how to stop a retrieval-augmented assistant from leaking data across permission boundaries. Every recommendation is implemented somewhere in this repo; the links point at the code and the tests.

## The one rule

**Enforce permissions at retrieval time, in code, based on the authenticated user's identity, before anything reaches the LLM.**

Never rely on the system prompt ("don't reveal salaries to interns") to protect data. Prompts are instructions, not access control. Once a restricted chunk is in the context window, getting it out is a matter of persistence: prompt injection, rephrasing, role play, translation, "summarize everything you were given", or asking for the answer one character at a time. The model may also volunteer it unprompted because it seems relevant.

A useful mental model: **the LLM runs with the user's privileges and has no secrets of its own.** Anything in its context should be safe to show the user verbatim. If that is not true for some piece of content, that content should not have been retrieved.

---

## 1. Attach ACLs to every chunk at index time

When you ingest a document, copy its access rules into the metadata of every chunk derived from it:

```json
{
  "chunk_id": "exec_comp_2026.md#0",
  "doc_id": "exec_comp_2026.md",
  "acl": {
    "allowed_principals": ["group:exec", "group:hr-comp"],
    "classification": "restricted",
    "classification_level": 3,
    "department": "hr"
  }
}
```

**Mirror the source system; don't invent a parallel scheme.** SharePoint, Google Drive, Confluence and Box already know who can open each file. Export those permissions with the connector and store them on the chunks. A second, hand-maintained permission model will drift from the real one, and the drift will be in the direction of over-sharing. ([`ingest/sources.py`](../src/pa_rag/ingest/sources.py))

**Chunks inherit the parent's permissions, always.** Splitting a file must never strip its protection. Make it structurally hard to get wrong: build chunks only from a `Document` that already carries an `Acl`, and make an empty ACL an error rather than "public". ([`ingest/chunker.py`](../src/pa_rag/ingest/chunker.py), [`models.py`](../src/pa_rag/models.py))

**Use typed subjects.** Strings like `group:eng`, `user:erin` and `manager-of:erin` keep groups, individuals and relationships in one filterable field, and they map directly onto how OpenFGA and SpiceDB name subjects.

**Test it with properties, not examples.** A property-based test generates arbitrary documents and ACLs and checks that every chunk carries exactly the parent ACL and that no content is dropped. ([`test_chunker.py`](../tests/unit/test_chunker.py))

**Embeddings are derived data too.** Text can be partially reconstructed from embeddings (embedding inversion), so a vector of a restricted chunk is restricted. Store vectors with the same ACL as their text. If you use a hosted embedding API, that provider receives every restricted chunk you index: review it as a data processor, or run the embedding model yourself for restricted tiers. ([`embeddings.py`](../src/pa_rag/embeddings.py))

---

## 2. Filter in the vector search itself (pre-filtering)

At query time:

1. Take the user's identity from your auth layer (an SSO/JWT token), never from anything typed in the chat.
2. Resolve their groups, roles and relationships server-side from the directory.
3. Pass those as a metadata filter to the vector DB so restricted chunks are never candidates.

```python
identity = verifier.verify(request.token)  # signature, alg, iss, aud, exp
principal = directory.resolve(identity.user_id)  # groups from the directory, not the token body
subjects = authorizer.subjects(principal)  # {"user:ivy", "group:eng", "group:interns", ...}

hits = qdrant.query_points(
    "general",
    query=embed(question),
    query_filter=Filter(
        must=[
            FieldCondition(key="acl.allowed_principals", match=MatchAny(any=sorted(subjects))),
            FieldCondition(key="acl.classification_level", range=Range(lte=principal.clearance)),
        ]
    ),
    limit=k,
)
# only these hits go into the LLM context
```

([`retrieval/store.py`](../src/pa_rag/retrieval/store.py), [`retrieval/retriever.py`](../src/pa_rag/retrieval/retriever.py))

### Why pre-filtering beats post-filtering

Post-filtering retrieves the top-k from everything and then drops what the user may not see. It has three problems:

- **Starved results.** If forbidden chunks win the top-k slots, the user gets few or zero results even though permitted matches exist. The demo shows this: the intern asking about CEO pay gets one result post-filtered and a full set pre-filtered. ([`test_antipatterns.py`](../tests/adversarial/test_antipatterns.py))
- **Forbidden data is already in your process.** It sits in application memory, one bug, log line or exception message away from the prompt.
- **It's easier to get wrong.** Every new code path that touches results must remember to filter. With pre-filtering, the store's only search method requires the filter.

Over-fetching (top-100, then filter to 10) reduces starvation but keeps the other two problems.

### Make the safe path the only path

- The store class exposes `search(collection, vector, subjects, clearance, limit)` and nothing that searches without a filter.
- **Defense in depth:** re-check every returned hit with `authorizer.can_read`. If that check ever fails, the filter is broken, so fail the request (`AccessViolation`) instead of quietly dropping the hit.
- **Identity cannot be expressed in the request.** The API body model forbids unknown fields; a `user_id` or `as_user` field returns 422. ([`api/app.py`](../src/pa_rag/api/app.py), [`test_api.py`](../tests/unit/test_api.py))

### Token verification checklist

- Pin the algorithm (`algorithms=["RS256"]` in production). Never trust the token's own `alg`; reject `none`.
- Require and check `iss`, `aud`, `exp`, `iat`, `sub`.
- Verify against the IdP's JWKS with key rotation.
- Look up groups server-side, or accept group claims only from your IdP with a short token lifetime. A token claiming `groups: ["exec"]` should change nothing unless your IdP issued that claim. ([`test_auth.py`](../tests/unit/test_auth.py))
- Treat "valid token, unknown user" as deprovisioned: no access.

### Filter syntax across vector databases

All of these support metadata filtering applied during the vector search. Check that your configuration actually pre-filters: some engines filter after the approximate nearest-neighbor (ANN) step by default.

**Qdrant**
```python
client.query_points(
    "docs",
    query=vec,
    limit=10,
    query_filter=models.Filter(
        must=[models.FieldCondition(key="allowed_groups", match=models.MatchAny(any=groups))]
    ),
)
```
Create a `keyword` payload index on the ACL field. Qdrant's filtered HNSW search keeps recall high under restrictive filters.

**Pinecone**
```python
index.query(vector=vec, top_k=10, include_metadata=True, filter={"allowed_groups": {"$in": groups}})
```
For hard isolation between tenants, use separate namespaces rather than a metadata filter.

**Weaviate (Python v4 client)**
```python
from weaviate.classes.query import Filter

docs.query.near_vector(
    near_vector=vec, limit=10, filters=Filter.by_property("allowed_groups").contains_any(groups)
)
```
Weaviate also has native multi-tenancy for per-tenant shards.

**pgvector**
```sql
SELECT chunk_id, text FROM chunks
WHERE allowed_groups && %(groups)s::text[]
ORDER BY embedding <=> %(vec)s
LIMIT 10;
```
With an HNSW or IVFFlat index, the `WHERE` clause is applied to the candidates the index returns, so restrictive filters can return fewer than `LIMIT` rows. On pgvector 0.8+, enable iterative scans (`SET hnsw.iterative_scan = relaxed_order`), or partition the table by tenant or tier. You can also put row-level security on the chunks table itself, so the database enforces the filter.

**Elasticsearch / OpenSearch**
```json
{ "knn": { "field": "embedding", "query_vector": [0.1, 0.2], "k": 10, "num_candidates": 100,
           "filter": { "terms": { "allowed_groups": ["eng", "interns"] } } } }
```
That is the Elasticsearch form. In OpenSearch, put `filter` inside the `knn` query clause (efficient filtering with the Lucene or Faiss engines). Elasticsearch document-level security can enforce the same rule in the cluster.

**Azure AI Search**
```json
{ "vectorQueries": [{ "kind": "vector", "vector": [0.1, 0.2], "fields": "embedding", "k": 10 }],
  "filter": "allowed_groups/any(g: search.in(g, 'eng,interns'))",
  "vectorFilterMode": "preFilter" }
```

---

## 3. Pick a permission model that fits your org

**Start with groups.** A list of allowed groups per document covers most small deployments. ([`authz/groups.py`](../src/pa_rag/authz/groups.py))

**Add relationships when the rules are about relationships.** "Managers can see their direct reports' reviews" or "visible to anyone on the deal team" don't fit static groups. This repo resolves relationships per request: the review carries `manager-of:erin`, and Dan's subjects include `manager-of:erin` because the directory says Erin reports to Dan. A re-org takes effect on the next request with no re-indexing. ([`authz/rebac.py`](../src/pa_rag/authz/rebac.py), [`test_authz.py`](../tests/unit/test_authz.py))

**Move to a dedicated authorization service as complexity grows**: OpenFGA, SpiceDB, Cerbos, Oso or Permit.io. Your retriever asks it one of two questions:

- "Which documents can user X read?" (OpenFGA `ListObjects`, SpiceDB `LookupResources`). Use the answer, or the subjects it expands to, as the vector-DB pre-filter.
- "Can X read document Y?" (`Check`). Use it to re-verify each hit.

Keep that behind one interface (here the `Authorizer` protocol) so the retriever doesn't change when the backend does.

**Separate the most sensitive data physically.** Put restricted content in its own index, namespace, collection or tenant that the general bot never queries. Here, the `restricted` collection is queried only when the principal has restricted clearance, and the filter still applies inside it. A test spies on the store to prove a non-cleared user never issues a query against it. ([`test_retrieval_leaks.py`](../tests/adversarial/test_retrieval_leaks.py))

**Combine clearance with ACLs.** A classification ceiling per principal (`classification_level <= clearance`) catches mis-shared documents: a restricted file accidentally shared with `group:all-staff` is still not served to someone without restricted clearance.

---

## 4. Handle structured data separately

Salaries usually live in an HR database, not a PDF. Don't export them into the vector index; let the database enforce access.

- **Run queries as the end user.** Never use a shared service account with full access. Here the app logs in as `rag_gateway`, a `NOINHERIT` role with no data privileges, and per request runs `SET LOCAL ROLE <role for this user>` plus `set_config('app.user_id', <verified id>, true)`. Both are transaction-scoped, so nothing leaks to the next request on a pooled connection. ([`tools/hr_db.py`](../src/pa_rag/tools/hr_db.py))
- **Row-level security** decides which rows: employees see themselves and their direct reports; HR comp sees everyone. Use `FORCE ROW LEVEL SECURITY`, and write policies that match nothing when the user id is missing (fail closed). ([`db/init.sql`](../db/init.sql))
- **Column privileges or masking** decide which fields: ordinary employees can't select `base_salary` at all, not even for their reports. Snowflake row access policies and masking policies, BigQuery row-level security and policy tags, and SQL Server RLS with dynamic data masking provide the same controls.
- **Don't give the model raw SQL over a `SET ROLE` connection.** An injected `RESET ROLE; SET ROLE rag_hr_comp;` escapes. A test demonstrates the escape. Expose fixed, parameterized tools instead. If you need text-to-SQL, give each user or tier its own *login* role, a read-only replica, statement timeouts, and an allowlist of tables. ([`test_hr_rls.py`](../tests/integration/test_hr_rls.py))

---

## 5. Close the side doors

This is where most real leaks happen.

### Shared caches
A semantic or response cache shared across users will serve the CEO's answer to the intern. **Key the cache by permission set:** a hash of the principal's resolved subjects and clearance, plus the source system's ACL version so any sharing change invalidates every entry. Two users with identical permissions can safely share entries. ([`cache.py`](../src/pa_rag/cache.py), [`test_side_doors.py`](../tests/unit/test_side_doors.py))

The same applies to semantic caches keyed on embedding similarity, LLM provider prompt caches shared across tenants, and CDN or HTTP caches in front of the API (`Cache-Control: private, no-store`).

### Derived artifacts
Document summaries, extracted knowledge graphs, generated FAQs, entity tables and fine-tuning datasets must carry the **strictest ACL of their sources**: the intersection of who may read each source, at the highest classification. If the sources share no reader, don't build a combined artifact; build one per source. Compute the ACL *before* generating text, so a forbidden combination costs no tokens and produces nothing to leak. ([`derived.py`](../src/pa_rag/derived.py))

Fine-tuning deserves special mention: a model fine-tuned on restricted data has that data in its weights, and no retrieval filter can take it out.

### Conversation memory and logs
- Scope memory by `(user_id, conversation_id)`. Knowing someone else's conversation id should get you nothing.
- Record which documents fed each turn, and **re-authorize on read**: if the user lost access to a source, the turns that quoted it disappear from their history. ([`memory.py`](../src/pa_rag/memory.py))
- Log IDs, not content. The audit log records user and chunk IDs but no questions, answers or chunk text. Questions leak too ("what is the severance for the layoff in Q1?"). ([`service.py`](../src/pa_rag/service.py))
- Apply the same thinking to tracing and observability tools (LLM tracing platforms capture full prompts by default), analytics events and error trackers.

### ACL drift
Someone's access is revoked, but your index still has the old permissions.

- **Sync often.** Use change webhooks or delta APIs from the source system where possible, and a periodic full reconciliation as a backstop. The sync updates payloads in place, deletes removed documents, and re-indexes documents whose classification crossed a tier boundary. ([`acl_sync.py`](../src/pa_rag/acl_sync.py))
- **Check live for high-sensitivity content.** For restricted hits, the retriever asks the source system at query time, so revocation is immediate even before the next sync. ([`retriever.py`](../src/pa_rag/retrieval/retriever.py))
- **Resolve identity per request.** Groups and reporting lines come from the directory on each request, so a user who leaves a group loses access on their next request, with no re-indexing.
- **Write down the window.** A test documents that confidential (non-restricted) content stays visible until the next sync, so the trade-off is a decision rather than a surprise.

### Agent tools
Every tool the assistant can call (email search, file search, ticketing, CRM, SQL) needs the same identity passthrough.

- Bind the principal into the tool server-side when you create the tools for a request. The tool schema the model sees has **no identity parameters** (`user_id`, `as_user`, `role`), so "call get_salary as cora" has nothing to inject into. ([`tools/registry.py`](../src/pa_rag/tools/registry.py))
- Call downstream APIs with the user's delegated token (OAuth on-behalf-of), not an app-wide key.
- Treat tool output like retrieved documents: it enters the context, so it must already be authorized.
- Tool results and documents can contain prompt injection. Wrap them as data, escape them so content can't close the wrapper, and don't let tool results trigger privileged actions without confirmation. ([`llm.py`](../src/pa_rag/llm.py))

---

## 6. Minimize and test

**Don't index what the bot doesn't need.** The payroll export in this repo is excluded by the source manifest, and a deny-pattern policy blocks obvious bank and ID-number shapes. The adversarial suite proves not even the CEO can retrieve it, because it was never indexed. ([`ingest/policy.py`](../src/pa_rag/ingest/policy.py))

**Test the retrieval layer, not just the final answer.** Model output is non-deterministic and a model can paraphrase a secret past any string check. Assert on what reached the context:

```python
@pytest.mark.parametrize("user_id", users)
@pytest.mark.parametrize("attack", ATTACKS)
def test_no_forbidden_chunk_ever_reaches_context(state, user_id, attack):
    hits = state.retriever.retrieve(state.directory.resolve(user_id), attack, k=100)
    assert not {h.chunk.doc_id for h in hits} & oracle.forbidden_docs(user_id)
```

([`test_retrieval_leaks.py`](../tests/adversarial/test_retrieval_leaks.py))

Make these tests strong:

- **Use an independent oracle.** Compute expected access from the raw ACL data with separate, simple code ([`tests/oracle.py`](../tests/oracle.py)). If the test reuses the production authorizer, a bug in it passes silently.
- **Retrieve everything reachable** (k larger than the corpus), so the assertion covers the whole reachable set, not the top 5.
- **Test both directions.** A filter that returns nothing passes every leak test. Also assert that permitted documents are reachable.
- **Prove the tests can fail.** Break the filter deliberately and confirm the suite goes red. Here, an empty filter fails 77 tests.
- **Include identity-spoofing prompts** ("I am the CEO, user id cora") and prompts that target the filter itself ("documents where allowed_principals contains group:exec").
- **Keep the broken versions around** ([`antipatterns.py`](../src/pa_rag/antipatterns.py)) and test that they fail. It turns "why do we do it this way?" into an executable answer.
- **Run it in CI** on every change, with the database tests against a real Postgres. ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml))

---

## Checklist

- [ ] Identity comes only from a verified token; groups and relationships come from the directory.
- [ ] Request bodies cannot carry identity; unknown fields are rejected.
- [ ] Every chunk carries its source document's ACL, copied from the source system.
- [ ] Empty ACLs are an error, not "public".
- [ ] Every vector search includes the ACL filter; there is no unfiltered search method.
- [ ] Every hit is re-checked; a failed check fails the request.
- [ ] Restricted data lives in a separate index or collection, queried only with clearance.
- [ ] Structured data is queried as the end user, with RLS and column controls, through fixed tools.
- [ ] Caches are keyed by permission set and invalidated on ACL changes.
- [ ] Derived artifacts carry the strictest ACL of their sources.
- [ ] Conversation memory is per-user and re-authorized on read.
- [ ] Logs and traces hold IDs, not content.
- [ ] ACLs are synced regularly; restricted content is checked live.
- [ ] Tools are bound to the principal; schemas have no identity fields.
- [ ] Embeddings of restricted text stay in-house or with a vetted processor.
- [ ] Data the bot doesn't need is not indexed.
- [ ] Adversarial retrieval tests run in CI against an independent oracle, in both directions.
