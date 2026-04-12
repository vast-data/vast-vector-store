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

## Deferred from: story 3-1-langchain-standard-integration-test-suite (2026-04-12)

- **AI-2 (NULL metadata in _row_to_document):** `json.loads(None)` raises `TypeError` when a row's metadata column is NULL (inserted externally bypassing VastDBVectorStore). Test `test_row_with_null_metadata_roundtrips` in `tests/integration_tests/test_vectorstore.py` is marked `@pytest.mark.xfail` for this bug. Proposed fix in `_row_to_document`: replace `json.loads(row.get(self._metadata_column, "{}"))` with `json.loads(metadata_raw) if (metadata_raw := row.get(self._metadata_column)) is not None else {}`. Deferred to a follow-up Epic 3 corrective story.
