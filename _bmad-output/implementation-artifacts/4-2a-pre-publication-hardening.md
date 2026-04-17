# Story 4-2a: Pre-Publication Hardening & Deferred Fixes

## Story

**As a** maintainer preparing langchain-vastdb for PyPI publication,
**I want** all actionable deferred work items resolved before the 4-3 publication story,
**So that** the published package is robust, correctly validated, and free of known low-hanging bugs.

## Status

review

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
