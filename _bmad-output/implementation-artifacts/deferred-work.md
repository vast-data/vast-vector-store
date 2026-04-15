# Deferred Work

## Deferred from: code review of story 1-1-initialize-package-scaffold-with-uv-and-hatchling (2026-04-09)

- `langchain-tests` dev dependency is unpinned — risk of breaking changes from upstream. Consider pinning to a range like `langchain-tests>=1.1,<2` before running integration tests (Story 3.1).
- sdist build has no exclude configuration — `_bmad/`, `_bmad-output/`, `docs/`, `.gitlab-ci.yml`, `.cursor/`, `.opencode/` would be included in a source distribution. Add `[tool.hatch.build.targets.sdist]` exclude before PyPI publication (Story 4.3).
- `langchain-core>=0.3` allows a wide version range spanning 0.x to 1.x. The lockfile resolves 1.2.28. Consider tightening to `>=1.0,<2` when Epic 2 implements real VectorStore methods.
- `readme = "README.md"` currently points at GitLab boilerplate containing the internal corporate URL `https://git.vastdata.com/genai/vast-vector-store.git`. Story 4.1 will rewrite the README — ensure internal URLs are removed before publication.
- No `py.typed` marker file (PEP 561) — type checkers will ignore inline annotations. Add `src/langchain_vastdb/py.typed` when Epic 2 introduces typed method signatures.

## Deferred from: code review of story 1-2-configure-gitlab-ci-cd-pipeline (2026-04-09)

- No `workflow:rules` directive to prevent duplicate pipelines -- without top-level workflow rules, pushing to an MR branch may trigger two pipelines (one for push, one for MR). Consider adding workflow:rules when pipeline complexity increases.
- Test stages (lint, unit-test, integration-test) also run on tag pushes alongside publish -- this wastes CI minutes but is not incorrect. Consider adding rules to skip test stages on tag pushes if CI costs become a concern. (Deferred: requires human judgment on team preference.)

## Deferred from: code review of story 2-1-constructor-session-management-and-table-access (2026-04-09)

- Thread-safety: `_metadata_loaded` flag in `VastDBVectorStore._get_table()` has no synchronization. Two threads calling `_get_table` simultaneously when `_metadata_loaded=False` could both call `load(tx)`. Benign in practice since VastDB SDK is sync-only and `load()` is idempotent, but should be considered if future async support introduces concurrency.

## Deferred from: code review of story 2-2-add-texts-and-document-insertion (2026-04-09)

- Float64 inference in RecordBatch: `pa.RecordBatch.from_pydict()` infers float64 for Python float lists in the vector column; VastDB table schema likely uses float32. VastDB SDK handles type coercion on insert. Will be validated in integration tests (Story 3.1).

## Deferred from: code review of story 2-3-similarity-search-operations (2026-04-09)

- Metadata None safety in `_row_to_document`: if a row has `None` for the metadata column (e.g., inserted by subclass or external tool), `json.loads(None)` raises TypeError. Base class `_insert_vectors` always writes `json.dumps({})`, so this only affects externally-inserted data. Will be validated in integration tests (Story 3.1).

## Deferred from: code review of story 3-1-langchain-standard-integration-test-suite (2026-04-12)

- `from vastdb._internal import VectorIndexSpec` uses a private module. `VectorIndexSpec` is not exported from the `vastdb` public API, so `_internal` is the only import path. Should be revisited if a future `vastdb` release exposes this via a public API.
- `test_add_documents_with_ids_is_idempotent` and `test_add_documents_by_id_with_mutation` in the standard suite require upsert/overwrite semantics. Whether VastDB's `table.insert()` handles duplicate `id` values idempotently (or raises an error, or creates duplicates) is unknown without live-cluster testing. If these tests fail in CI, `_insert_vectors` may need a delete-then-insert upsert pattern and the fix should target a follow-up Epic 3 corrective story.

- **AI-2 (NULL metadata in _row_to_document):** `json.loads(None)` raises `TypeError` when a row's metadata column is NULL (inserted externally bypassing VastDBVectorStore). Test `test_row_with_null_metadata_roundtrips` in `tests/integration_tests/test_vectorstore.py` is marked `@pytest.mark.xfail` for this bug. Proposed fix in `_row_to_document`: replace `json.loads(row.get(self._metadata_column, "{}"))` with `json.loads(metadata_raw) if (metadata_raw := row.get(self._metadata_column)) is not None else {}`. Deferred to a follow-up Epic 3 corrective story.

## Deferred from: code review of story 3-1 live-cluster fix branch (2026-04-13)

- `_metadata_loaded` flag remains without synchronization — re-raised after fix commits added the VectorIndex fallback write inside the same block. Still benign because VastDB SDK is sync-only, but now the cached state includes a potentially patched `_vector_index`, making any future async support more fragile.
- `_delete_by_ids` / `_insert_vectors` hook contract: the base class now calls them with `tx=tx` to preserve upsert atomicity, but subclasses that override these methods without honoring the `tx` kwarg silently break atomicity. Document in the hook API contract and defer enforcement to a future refactor (e.g., make `tx` a positional required arg or validate at call site).
- Elysium (sorted) tables use `decimal128(38,0)` for `$row_id` instead of `uint64`. The new `_delete_by_ids` path (`table.select(..., internal_row_id=True).read_all()` → `table.delete(rows)`) may type-mismatch for sorted tables. Vector tables are typically unsorted, so this is a corner case. Revisit when Elysium compatibility is in scope.

## Deferred from: code review of story 3-1a-live-cluster-correctness-fixes (2026-04-15)

- **DF1.** `_do_vector_search_fallback` reads the full table via `read_all().to_pylist()`. OOM risk on large tables. Needs a streaming top-k heap or a server-side `LIMIT` with a sampled scan.
- **DF2.** `_do_vector_search_adbc` opens a fresh ADBC connection per call. Acceptable for test volume; not for production throughput. Pool or cache per-store.
- **DF3.** Upsert atomicity depends on the SDK's transaction isolation level. If it is not serializable, concurrent writers can interleave between the delete and insert legs. Document the guarantee or pick a locking strategy.
- **DF4.** CI stores `VASTDB__ENDPOINT_PASSWORD` as a plain GitLab variable. Rotate to masked/protected or move to a vault.
- **DF5.** `sshpass` is apt-installed in CI without version pinning; supply-chain drift risk. Pin or vendor.
- **DF6.** `ci-tunnel.sh` backgrounds `ssh -f -N` and returns immediately; tests can race the tunnel coming up. Add a `nc -z localhost 18151` readiness loop.
- **DF7.** `_do_vector_search_fallback` silently skips dim-mismatched rows. A corrupted table would return "0 results" with no operator signal. Emit a counter + warning.
- **DF8.** `VectorIndex` fallback hardcodes `l2sq`. If the real index on the table is cosine/dot-product, results are wrong and only a warning log fires. Consider a config override on the store.
- **DF9.** SQL injection in `_do_vector_search_adbc` filter interpolation — listed here as a reminder that even after the P1 patch, the ADBC SQL path is still string-concatenation-based. A proper parameterized query API via the ADBC driver would be safer long-term.
