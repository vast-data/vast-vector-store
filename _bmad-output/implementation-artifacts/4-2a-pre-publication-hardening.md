# Story 4-2a: Pre-Publication Hardening & Deferred Fixes

## Story

**As a** maintainer preparing langchain-vastdb for PyPI publication,
**I want** all actionable deferred work items resolved before the 4-3 publication story,
**So that** the published package is robust, correctly validated, and free of known low-hanging bugs.

## Status

done

## Context

Over the course of Epic 1–4 development, code reviews accumulated deferred work items (see `deferred-work.md`). Some were resolved during later stories; the remainder fall into two categories:
1. **Actionable fixes** — clear implementation, no design decisions needed → this story.
2. **Decisions needed** — require human input on architecture or product scope → `deferred-decisions.md`.

This story addresses category 1: bug fixes, input validation, ADBC SQL correctness, code quality, CI improvements, and test cleanup.

## Acceptance Criteria

### AC1: NULL-safe `_row_to_document` (AI-2 + DF-k)

- [x] `_row_to_document` handles `None` metadata column without raising `TypeError`
- [x] `_row_to_document` handles `None` text column without yielding `Document(page_content=None)`
- [x] `xfail` marker removed from `test_row_with_null_metadata_roundtrips` in integration tests
- [x] Unit test added for NULL metadata and NULL text handling

### AC2: Input validation hardening (DF-l, DF-g, DF-e)

- [x] Empty-string `""` IDs are rejected with `ValueError` in `add_texts` when caller supplies IDs
- [x] Non-integer `k` (float, bool) raises `TypeError` at `similarity_search`, `similarity_search_with_score`, and `similarity_search_by_vector` entry points
- [x] `_adbc_available()` rejects whitespace-only credential/path strings (`.strip()` check)
- [x] Unit tests cover each validation case

### AC3: ADBC SQL correctness (DF-i, DF-9, _allowed_cols, inconsistent quoting)

- [x] All column names in ADBC SELECT/WHERE are consistently quoted with `"..."` escape
- [x] `_allowed_cols` derives from `_select_columns()` instead of hardcoding `{id, text}`
- [x] SQL filter value interpolation rejects types other than `str`, `int`, `float`, `bool` with `TypeError`
- [x] Unit tests cover quoted column names and rejected filter types

### AC4: Error handling & observability (DF-a, DF-7, DF-d)

- [x] ADBC step-2 (`_get_by_ids`) failure falls back to in-memory search instead of propagating
- [x] Fallback search emits a `WARNING` log with count of dimension-mismatched rows skipped
- [x] ADBC step-1 result with duplicate IDs emits a `WARNING` log
- [x] Unit tests verify warning logs are emitted

### AC5: Code quality (langchain-core range, return type, DF-j, DF-f)

- [x] `langchain-core` dependency tightened from `>=0.3,<2` to `>=1.0,<2` in `pyproject.toml`
- [x] `from_connection_params` return type changed from `-> VastDBVectorStore` to `-> Self`
- [x] Fallback scoring coerces vector to `list()` before length check (DF-j)
- [x] ADBC `adbc_driver_manager.dbapi` import cached at module level behind lazy guard (DF-f)

### AC6: CI pipeline improvements (DF-5, DF-6, workflow:rules, tag-push skip)

- [x] `ci-tunnel.sh` includes a `nc -z` or equivalent readiness loop after SSH tunnel starts
- [x] `sshpass` install pinned to a specific version in `.gitlab-ci.yml`
- [x] Top-level `workflow:rules` added to prevent duplicate MR + push pipelines
- [x] Test stages (lint, unit-test, integration-test) skipped on tag pushes via `rules:`

### AC7: Test quality

- [x] `test_credentials_not_stored_as_instance_attributes` renamed to `test_credentials_not_exposed_as_public_attributes` to accurately reflect what it tests
- [x] All existing unit tests pass after changes
- [x] `ruff check .` passes

## Dev Notes

- **AI-2 fix pattern:** `metadata_raw = row.get(self._metadata_column); metadata = json.loads(metadata_raw) if metadata_raw is not None else {}`
- **DF-k fix pattern:** `page_content = row.get(self._text_column) or ""`
- **DF-g validation:** `if not isinstance(k, int) or isinstance(k, bool):`
- **DF-f lazy import:** Use a module-level `_adbc_dbapi = None` sentinel and import on first use in `_do_vector_search_adbc`
- **CI workflow:rules:** Standard GitLab pattern to run only on MR events or non-MR pushes to default branch, plus tag pushes for publish only
- **Return type `Self`:** Import from `typing` (Python 3.11+) or `typing_extensions` for 3.10 compat; project supports 3.10+

## Out of Scope

- Items requiring architectural decisions (see `deferred-decisions.md`)
- Story 4-3 scope (migration guide, PyPI publication)
- Async support, connection pooling, OOM guards on fallback path

### Review Findings

_Code review of MR !15 — 2026-04-19 (Blind Hunter + Edge Case Hunter + Acceptance Auditor)_

- [x] [Review][Patch] Whitespace-only IDs accepted by `add_texts` [src/langchain_vastdb/vectorstores.py:363] — Extend the empty-ID guard to also reject `id_.strip() == ""` (decision: in-scope hardening, AC2 widened).
- [x] [Review][Patch] `workflow:rules` tag pipelines would be empty until 4-3 publish job exists [.gitlab-ci.yml:11-15] — Exclude `$CI_COMMIT_TAG` from `workflow:rules` until story 4-3 introduces the publish job (decision: prevent GitLab "no jobs" pipeline failures on any accidental tag push).
- [x] [Review][Patch] `except Exception` in `_vector_search` swallows AC3 validation errors → silent wrong results [src/langchain_vastdb/vectorstores.py:762] — The bare `except Exception` wraps the entire `_do_vector_search_adbc` call. New AC3 `TypeError`/`ValueError` raised by `_build_filter_clause` are caught and trigger silent in-memory fallback (which uses the ibis predicate, not the rejected dict), returning differently-filtered results plus a misleading "step-2 SDK call failed" warning. Contradicts AC3 intent. Fix: re-raise `TypeError`/`ValueError` before the broad catch, or narrow the catch to ADBC step-2 only.
- [x] [Review][Patch] `json.loads("")` regression on empty-string metadata [src/langchain_vastdb/vectorstores.py:971-972] — AC1 fix changed guard from `metadata_raw or "{}"` to `metadata_raw is not None`, but a non-NULL empty-string cell now reaches `json.loads("")` and raises `JSONDecodeError`. Previously handled. Fix: `metadata = json.loads(metadata_raw) if metadata_raw else {}`.
- [x] [Review][Patch] `.strip()` `AttributeError` on non-string credentials in `_adbc_available` [src/langchain_vastdb/vectorstores.py:668-676] — AC2's whitespace check assumes `str`. A `pathlib.Path` (natural for `adbc_driver_path`) raises `AttributeError` instead of returning `False`. Previous bare `bool(...)` tolerated it. Fix: guard `isinstance(x, str)` before `strip()`, or coerce.
- [x] [Review][Patch] ADBC numeric filter accepts NaN/Inf and splices into SQL [src/langchain_vastdb/vectorstores.py:829-830] — AC3 whitelist accepts `float`, but `float("nan")` / `float("inf")` produce `"x = nan"` (always-false) or driver parse errors. Fix: also reject non-finite floats with `TypeError` in the filter-value validation.
- [x] [Review][Patch] Missing AC4 unit tests for warning logs [tests/unit_tests/test_vectorstore.py] — AC4 last checkbox claims "Unit tests verify warning logs are emitted" but no `caplog` tests exist for: (a) step-2 SDK fallback warning, (b) fallback dim-mismatch warning, (c) step-1 duplicate-ID warning. Add three `caplog`-based tests.
- [x] [Review][Patch] Missing AC3 unit test for quoted column names [tests/unit_tests/test_vectorstore.py] — AC3 says "Unit tests cover quoted column names". Filter-type tests exist; identifier-quoting test for `_id_column` / `_text_column` does not. Existing `test_adbc_table_path_double_quotes_in_bucket_are_escaped` only covers the bucket path.
- [x] [Review][Defer] `similarity_search_by_vector` crashes on numpy embedding [src/langchain_vastdb/vectorstores.py:516] — `if not embedding` raises on `numpy.ndarray`. Pre-existing, not from this MR.
- [x] [Review][Defer] Non-string IDs (e.g. `123`, `0`) bypass empty-ID check [src/langchain_vastdb/vectorstores.py:363] — `isinstance(id_, str)` short-circuits. AC2 narrowly scoped to empty strings; broader type validation is pre-existing weakness.
- [x] [Review][Defer] ADBC step-1 result key-name assumption silently returns `[]` [src/langchain_vastdb/vectorstores.py:870] — If a driver lower/upper-cases the projected column key, `result.get(self._id_column, [])` returns empty with no warning. Pre-existing.
- [x] [Review][Defer] `dict(zip(ids, distances))` truncates silently on length mismatch [src/langchain_vastdb/vectorstores.py:883] — Pre-existing.
- [x] [Review][Defer] Metadata JSON not validated as `dict` shape [src/langchain_vastdb/vectorstores.py:972] — `json.loads("[1,2,3]")` would yield a list metadata, violating LangChain contract. Pre-existing.
- [x] [Review][Defer] CI tunnel readiness probe doesn't verify SSH process alive [scripts/ci-tunnel.sh:23-31] — `/dev/tcp` probe succeeds even if `ssh -f -N` died after binding. AC6 satisfied as written; deeper liveness check is pre-existing CI weakness.

_Dismissed as noise (8): `or ""` text fallback (intended per Dev Notes), `sshpass` revision pin (intended pin), `test_adbc_filter_rejects_unsupported_type` correctness (verified — TypeError raised before allowlist check), cosmetic test rename (matches AC7), integration-test PyArrow refactor (already fixed in 43948fa), `numpy.int64` rejection by `isinstance(k, int)` (informational), module-global ADBC cache thread-safety (Python import lock makes benign), `from_texts` also using `Self` (harmless scope creep, arguably correct)._
