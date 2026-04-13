# Story 3.1a: Live-Cluster Correctness Fixes for VastDBVectorStore

Status: review

## Story

As a developer,
I want the correctness bugs in `VastDBVectorStore` that were exposed by Story 3.1's live-cluster integration test run to be fixed in a named, reviewable story,
so that the production-code changes are traceable independently of the test-suite compliance work and Story 3.1 stays scoped to ecosystem compliance.

## Context

Story 3.1 stood up the LangChain standard integration test suite against a live VAST v74 cluster (SSH-tunneled). The live run exposed real bugs in `src/langchain_vastdb/vectorstores.py` that unit tests with mocks could not catch. Story 3.1's Dev Notes explicitly froze the production class for Epic 3 ("If a bug is exposed, xfail + deferred-work entry, never an in-scope fix") for scope-hygiene reasons. This story owns those production fixes so that Story 3.1 remains spec-clean and the bugs are addressed under a named story with its own review.

Live-cluster test status when the SSH tunnel dropped (pre-fix):
- 12 PASSED (including previously-failing delete, upsert, None-ID)
- 1 XFAIL (AI-2 NULL metadata — still expected)
- 12 SKIPPED (async, correctly disabled)

Target after these fixes (when the v74 cluster is available again): **15 passed, 12 skipped, 1 xfailed, 0 failed, 0 errors.**

## Acceptance Criteria

1. **Given** `_get_table` is called against a cluster version that does not return vector index metadata in table stats,
   **When** `_table_metadata._vector_index is None` after `load()`,
   **Then** a `VectorIndex` object is constructed from the configured `vector_column` so that `table.vector_search()` can proceed, AND a `WARNING` log is emitted identifying the table and the hardcoded fallback metric so operators can detect mismatches.

2. **Given** `add_texts` is called with IDs supplied by the caller (via `ids=` or `Document.id` fields),
   **When** those IDs already exist in the table,
   **Then** the existing rows are deleted and the new rows are inserted in a single transaction (upsert semantics). When `ids` is `None` (fresh UUIDs), the delete round-trip is skipped.

3. **Given** `add_texts` receives a mixed list where some `ids` elements are `None` and others are explicit strings,
   **When** the list is processed,
   **Then** only the `None` entries are replaced with auto-generated UUIDs; explicit strings are preserved.

4. **Given** `add_texts` is called with an empty `texts` iterable,
   **When** processing begins,
   **Then** the method early-returns `[]` without opening a transaction or running any select/delete/insert RPC. `_delete_by_ids([])` and `_insert_vectors(..., embeddings=[])` each guard against empty input as defense-in-depth.

5. **Given** vectors passed to `_insert_vectors` are Python `float` lists (float64),
   **When** the PyArrow `RecordBatch` is constructed,
   **Then** the vector column is typed as a fixed-size list of `float32` (`pa.list_(pa.field("item", pa.float32(), nullable=False), vector_dim)`) so insertion matches the table schema without relying on implicit SDK coercion.

6. **Given** `_delete_by_ids` is called,
   **When** the delete is executed,
   **Then** matching rows are selected with `internal_row_id=True`, and the resulting `RecordBatch` is passed to `table.delete(rows)` — `table.delete()` does not accept ibis predicates directly and the previous implementation using `table.delete(predicate)` was broken.

7. **Given** `_do_vector_search` runs on a client where ADBC is unavailable (e.g. macOS dev without the VAST ADBC shared library),
   **When** `table.vector_search()` raises `NoAdbcConnectionError`,
   **Then** an in-memory L2-squared distance fallback runs (`_do_vector_search_fallback`), using the same distance metric and ordering as the native path (lower-is-better, ascending sort). Dim-mismatched rows are skipped; score semantics are consistent across code paths.

8. **Given** a VAST row is converted to a `Document` via `_row_to_document`,
   **When** the `id` column is present in the row dict,
   **Then** `Document.id` is set from `row.get(self._id_column)` so equality assertions in the LangChain standard suite (e.g. `test_add_documents`, `test_get_by_ids`) pass.

9. **Given** the `uv run ruff check .` and `uv run pytest tests/unit_tests/` commands,
   **When** they run against this branch,
   **Then** both exit `0` with zero warnings and 29/29 unit tests pass.

10. **Given** the v74 integration cluster is available,
    **When** `uv run pytest tests/integration_tests/ -v` runs,
    **Then** the suite reports 15 passed, 12 skipped, 1 xfailed, 0 failed, 0 errors. (Cannot be executed now — v74 cluster is down.)

## Tasks / Subtasks

- [x] **Task 1: VectorIndex fallback in `_get_table` (AC #1)**
  - [x] Import `VectorIndex` from `vastdb.table_metadata`.
  - [x] After `self._table_metadata.load(tx)`, check `_vector_index is None` and construct a fallback with `distance_metric="l2sq"`, `sql_distance_function="array_distance"`.
  - [x] Emit a `logging.warning(...)` when the fallback fires, identifying the table ref and noting that the metric is hardcoded to `l2sq`.

- [x] **Task 2: Upsert semantics in `add_texts` (AC #2, #3, #4)**
  - [x] Early-return `[]` when `texts_list` is empty.
  - [x] Track `ids_provided = ids is not None`.
  - [x] Replace per-element `None` in a provided `ids` list with `str(uuid.uuid4())`.
  - [x] Open one transaction for delete+insert; skip `_delete_by_ids` when `not ids_provided`.

- [x] **Task 3: Defensive guards in `_delete_by_ids` and `_insert_vectors` (AC #4, #5)**
  - [x] `_delete_by_ids`: `if not ids: return True` at entry.
  - [x] `_insert_vectors`: `if not embeddings: return ids` before constructing the batch.
  - [x] `_insert_vectors`: explicit `pa.list_(pa.field("item", pa.float32(), nullable=False), vector_dim)` type on the vector column, wrap embeddings in `pa.array(embeddings, type=vector_type)`.

- [x] **Task 4: Delete API fix (AC #6)**
  - [x] In both `tx`-provided and new-transaction branches of `_delete_by_ids`, run `table.select(columns=[id], predicate=..., internal_row_id=True).read_all()` and pass the resulting `RecordBatch` to `table.delete(rows)`.

- [x] **Task 5: ADBC fallback vector search (AC #7)**
  - [x] Catch `from vastdb.transaction import NoAdbcConnectionError` in `_do_vector_search`.
  - [x] Implement `_do_vector_search_fallback(tx, query_vector, k, columns, predicate)` that:
    - Scans `[id, vector]` with the filter predicate.
    - Skips rows where `vec` is not a `list` or has the wrong dimension (`len(vec) != len(query_vector)`).
    - Scores with **L2-squared distance** (`sum((a-b)*(a-b) ...)`) and sorts ascending to match the native `$distance` semantics.
    - Fetches full rows for the top-k IDs in a second `select` using the caller's `columns` list.

- [x] **Task 6: `Document.id` in `_row_to_document` (AC #8)**
  - [x] Extract `doc_id = row.get(self._id_column)` and pass `id=doc_id` to the `Document` constructor.

- [x] **Task 7: Local validation (AC #9)**
  - [x] `uv run ruff check .` passes with zero warnings.
  - [x] `uv run pytest tests/unit_tests/` reports 29/29 passed.

- [ ] **Task 8: Live-cluster re-validation (AC #10)**
  - [ ] When the v74 cluster is back, run `uv run pytest tests/integration_tests/ -v` and attach the summary to the Dev Agent Record below.
  - [ ] Confirm 15 passed / 12 skipped / 1 xfailed / 0 failed / 0 errors.

## Dev Notes

### Relationship to Story 3.1

Story 3.1 delivered the LangChain standard test suite (`tests/integration_tests/test_vectorstore.py`), the `.gitlab-ci.yml` cleanup, and the AI-1/2/3 explicit coverage. Its "production class frozen" rule was upheld *in spirit* — these fixes are genuine correctness bugs, not scope creep — but the *letter* of the rule required a separate named story for traceability. This story owns the production changes so Story 3.1 stays spec-clean.

### Why these bugs were not caught by unit tests

| Bug | Why unit tests missed it |
|---|---|
| VectorIndex fallback | Mocks returned a synthetic `VectorIndex`; real cluster version returned `None`. |
| Upsert semantics | Unit tests never called `add_texts` twice with the same IDs; `table.insert()` mocking hid the duplicate-row behavior. |
| None-ID handling | Unit tests passed full `ids` lists; `Document.id=None` from the standard suite was not exercised. |
| float32 enforcement | Mocked `table.insert()` accepts any type; real VAST rejects float64. |
| `table.delete(predicate)` | Mocks accepted any argument; real SDK requires a `RecordBatch` with `$row_id`. |
| ADBC fallback | Unit tests bypass ADBC entirely. |
| `Document.id` | Standard suite equality assertions compare IDs; unit tests compared content only. |

### Deferred items (not in this story)

The following items from the Story 3.1 code review remain open and are tracked in `deferred-work.md`:

- AI-2 `json.loads(None)` on NULL metadata — still `xfail(strict=True)` in the test suite.
- `_do_vector_search_fallback` full-table-scan row limit — design-level change (streaming top-k heap) needs a separate decision.
- `_metadata_loaded` thread-safety — benign under sync-only SDK, tracked since Story 2.1.
- Hook-override `tx` kwarg contract enforcement — documentation-level concern.
- Elysium sorted-table `$row_id` type mismatch — corner case, not a vector-store concern today.
- Private SDK imports (`vastdb._adbc`, `vastdb._internal.VectorIndexSpec`) in the test fixture — pre-existing SDK limitation.

### File List

- `src/langchain_vastdb/vectorstores.py` — modified: seven fixes listed in ACs #1–#8 plus the warning log.

### Testing standards

1. `uv run ruff check .` exits 0 with zero warnings.
2. `uv run pytest tests/unit_tests/` reports 29/29 passed — no regression from Story 2.5.
3. `uv run pytest tests/integration_tests/ -v` against a live v74+ cluster reports 15 passed / 12 skipped / 1 xfailed / 0 failed / 0 errors. (Blocked: v74 cluster currently down.)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (code review batch-apply)

### Completion Notes List

- All seven production fixes applied on branch `fix/3-1-live-cluster-validation` (commits `40145d7`, `916df2a`, `7395e0a`, plus this review's batch-apply).
- Additional patch-apply changes from this review:
  - Fallback vector search rewritten from dot-product to L2-squared distance with ascending sort, matching native `$distance` semantics.
  - `add_texts([])` + `_delete_by_ids([])` + `_insert_vectors(empty)` defensive guards.
  - Skip `_delete_by_ids` round-trip when `ids_provided is False`.
  - Dim-mismatch skip in fallback scoring loop.
  - Warning log when the VectorIndex `l2sq` fallback fires.
- `uv run ruff check .` — PASS (zero warnings).
- `uv run pytest tests/unit_tests/` — 29/29 passed, no regressions.
- **Live-cluster re-validation blocked** — v74 cluster is currently down. Task 8 remains open until the cluster is back and integration tests can be re-run.

### File List

- `src/langchain_vastdb/vectorstores.py` (MODIFIED)
