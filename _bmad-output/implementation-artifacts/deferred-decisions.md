# Deferred Decisions

Items from `deferred-work.md` that require architectural decisions or human input before implementation. These were excluded from Story 4-2a to avoid blocking the pre-publication cleanup.

## DD-1: Thread-safety of `_metadata_loaded` flag

**Source:** Story 2-1, Story 3-1 fix branch
**Location:** `vectorstores.py:250`

The `_metadata_loaded` flag in `_get_table()` has no synchronization. Two threads calling `_get_table` simultaneously when `_metadata_loaded=False` could both call `load(tx)`. After the Story 3-1a fix, the cached state also includes a potentially patched `_vector_index`.

**Why this needs a decision:** Benign today because VastDB SDK is sync-only and `load()` is idempotent. But if async support is ever added, this becomes a race condition. The question is whether to add a threading lock now (small overhead, future-proofing) or explicitly document "sync-only" as a contract.

**Options:**
1. Add `threading.Lock` around the metadata-load block
2. Document sync-only contract in docstrings and README; defer locking to an async story
3. Leave as-is (current behavior)

---

## DD-2: Hook `tx` parameter contract

**Source:** Story 3-1 fix branch
**Location:** `vectorstores.py:362-370, 518-561`

`_delete_by_ids` / `_insert_vectors` are called with `tx=tx` to preserve upsert atomicity, but subclasses that override these methods without honoring the `tx` kwarg silently break atomicity.

**Why this needs a decision:** Making `tx` a positional required arg is a breaking API change. Validating at call site adds complexity. Documenting is the lightest option but doesn't prevent bugs.

**Options:**
1. Document in hook docstrings that `tx` must be honored for atomicity
2. Make `tx` positional-only (breaking change for subclasses)
3. Add runtime check + warning if subclass signature lacks `tx`

---

## DD-3: Elysium (sorted) tables `$row_id` type mismatch

**Source:** Story 3-1 fix branch
**Location:** `vectorstores.py:548-560`

Elysium (sorted) tables use `decimal128(38,0)` for `$row_id` instead of `uint64`. The `_delete_by_ids` path may type-mismatch for sorted tables.

**Why this needs a decision:** Vector tables are typically unsorted, so this is a corner case. Do we need to support sorted tables at all?

**Options:**
1. Document "unsorted tables only" as a known limitation
2. Add type coercion for `$row_id` in `_delete_by_ids`
3. Defer until Elysium compatibility is in scope

---

## DD-4: Fallback search reads full table (OOM risk)

**Source:** DF1 from Story 3-1a review
**Location:** `vectorstores.py:850-851`

`_do_vector_search_fallback` calls `read_all().to_pylist()` on the full table. On large tables this can OOM the process.

**Why this needs a decision:** The proper fix (streaming top-k heap or server-side LIMIT) is a significant redesign of the fallback path. A simpler mitigation (row count warning, configurable limit) is possible but arbitrary.

**Options:**
1. Add a configurable `max_fallback_rows` parameter with a reasonable default (e.g. 100K) and raise ValueError if exceeded
2. Add a warning log when row count exceeds a threshold but process all rows
3. Rewrite fallback to use streaming with a top-k heap (most correct but complex)
4. Document the limitation and recommend ADBC for large tables

---

## DD-5: ADBC connection-per-call overhead

**Source:** DF2 from Story 3-1a review
**Location:** `vectorstores.py:807-817`

`_do_vector_search_adbc` opens a fresh ADBC connection per call via `adbc_dbapi.connect(...)`. Acceptable for low-volume use; not for production throughput.

**Why this needs a decision:** Connection pooling involves lifecycle management, thread-safety decisions, and API surface changes (e.g. `close()` method on the store).

**Options:**
1. Cache one connection per store instance (simplest; break on fork)
2. Use a connection pool (complex; needs lifecycle management)
3. Document per-call overhead as a known limitation
4. Accept a connection factory callable in the constructor

---

## DD-6: Upsert atomicity guarantees

**Source:** DF3 from Story 3-1a review
**Location:** `vectorstores.py:354-359`

Upsert atomicity depends on the SDK's transaction isolation level. If it is not serializable, concurrent writers can interleave between the delete and insert legs.

**Why this needs a decision:** Requires understanding VastDB SDK's transaction guarantees. If not serializable, we may need application-level locking.

**Options:**
1. Document that upsert is not safe under concurrent writes (honest)
2. Add application-level locking (complex, limits scalability)
3. Confirm SDK isolation level with VAST team and document accordingly

---

## DD-7: CI credential management

**Source:** DF4 from Story 3-1a review
**Location:** `.gitlab-ci.yml:93-96`

`VASTDB__ENDPOINT_PASSWORD` is stored as a plain GitLab CI/CD variable. Should be masked/protected or moved to a vault.

**Why this needs a decision:** This is an ops/security concern that depends on the team's GitLab tier and security posture. Not a code change.

**Options:**
1. Mark variable as Masked + Protected in GitLab CI/CD settings (manual step)
2. Move to HashiCorp Vault or GitLab Premium secrets
3. Accept current risk with documentation

---

## DD-8: VectorIndex fallback hardcodes `l2sq`

**Source:** DF8 from Story 3-1a review
**Location:** `vectorstores.py:258-270`

The VectorIndex fallback hardcodes `l2sq` as the distance metric. If the real index uses cosine or dot-product, search results are silently wrong (only a warning log fires).

**Why this needs a decision:** Adding a config override changes the constructor API. The alternative is to always use ADBC (which computes distance server-side without needing to know the index metric).

**Options:**
1. Add `distance_metric` constructor parameter (API change)
2. Document that fallback always uses L2Sq; recommend ADBC for other metrics
3. Try to detect the metric from table metadata (may not be available)

---

## DD-9: Writing private `_vector_index` attribute

**Source:** DF-b from Story 3-1a second pass
**Location:** `vectorstores.py:266`

`self._table_metadata._vector_index = VectorIndex(...)` writes a single-underscore private attribute of `vastdb.table_metadata.TableMetadata`. Any upstream refactor breaks this.

**Why this needs a decision:** No public setter is available in the VastDB SDK. This is a necessary workaround. The only action is to file a feature request upstream.

**Options:**
1. File a feature request for a public `set_vector_index()` API on `TableMetadata`
2. Accept the risk and add a comment pointing to the upstream issue
3. Wrap in a try/except with a clear error message if the attribute disappears

---

## DD-10: `OSError` too broad in ADBC catch

**Source:** DF-c from Story 3-1a second pass
**Location:** `vectorstores.py:711-715`

`OSError` in the ADBC exception catch tuple can mask disk/permission/network errors, routing them into the silent fallback path instead of raising.

**Why this needs a decision:** We need to know what specific exceptions the ADBC driver raises on connection failure. Until the driver documents its exception hierarchy, narrowing the catch may cause unexpected crashes.

**Options:**
1. Remove `OSError` from the catch tuple (may break fallback on some systems)
2. Narrow to `ConnectionError` (subclass of OSError, more specific)
3. Keep `OSError` but log at WARNING level with a note about the broad catch
4. Wait for ADBC driver to document its exception hierarchy

---

## DD-11: Very large `k` limit

**Source:** DF-h from Story 3-1a second pass
**Location:** `vectorstores.py:805`

Very large `k` (e.g. `10**9`) is interpolated directly into `LIMIT` with no cap. Could cause server-side resource exhaustion.

**Why this needs a decision:** What's a reasonable ceiling? This is a product decision. LangChain's standard tests typically use k=1..20. Production RAG uses k=3..10. But some users may want k=1000 for reranking pipelines.

**Options:**
1. Add a cap (e.g. `k <= 10_000`) with a ValueError
2. Document that large k values may cause performance issues
3. Add a configurable `max_k` parameter
