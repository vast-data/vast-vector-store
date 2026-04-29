# Story 5-1: Typed Metadata Columns & Subclassing Ergonomics

## Story

**As a** consumer of `langchain-vastdb` building a domain-specific subclass (driven by integration into `vast-pipelines`),
**I want** a declarative way to add typed metadata columns and a less boilerplate-heavy subclassing surface,
**So that** common subclass needs (typed columns, custom defaults, infrastructure-only columns) don't require overriding multiple internal hooks in lockstep.

## Status

done

## Context

While integrating `langchain-vastdb` into `vast-pipelines`, several friction points surfaced in the subclassing API shipped at the end of Epic 4:

- Adding a typed metadata column required overriding `_metadata_columns`, `_select_columns`, and `_row_to_document` in coordinated ways — easy to drift, hard to review.
- The `_metadata_columns` hook recomputed static column layouts on every insert.
- The `_store_full_metadata_json` flag created two divergent code paths for typed-column extraction, doubling test surface for marginal benefit.
- Transaction handling repeated the same `tx or session.transaction()` pattern across multiple methods.
- The integration test suite was serial, making the local feedback loop painful.
- New contributors had no `.env.template` to discover required environment variables.

This story bundles the post-publication improvements that addressed those issues. All work was completed before the story was logged; this file records scope retroactively so the sprint reflects reality and the next code review has a target to score against.

## Acceptance Criteria

### AC1: Declarative typed metadata columns

- [x] `TypedColumn` dataclass added with `default`, `default_factory`, `pa_type`, and `include_in_metadata` fields
- [x] `_typed_metadata_columns: dict[str, TypedColumn]` class attribute auto-derives column layout, full-row selection, and row-to-Document conversion
- [x] `include_in_metadata=False` supports infrastructure columns (e.g. `tenant_id`, `shard_key`) that exist for DB-level filtering but stay out of `Document.metadata`
- [x] `default_factory` supports per-row dynamic defaults (e.g. timestamps)
- [x] `pa_type` drives PyArrow coercion when present
- [x] `filtered_search` example updated to demonstrate the declarative hook

### AC2: Hook surface cleanup

- [x] `_metadata_columns` renamed to `_build_metadata_columns` to reflect that it constructs the column list, not declares it
- [x] Static defaults precomputed once per instance instead of recomputed per insert
- [x] `TypedColumn.backfill` renamed to `include_in_metadata` for clearer intent
- [x] `_store_full_metadata_json` flag removed — typed columns are always popped from the JSON blob, eliminating the divergent path
- [x] `_select_columns` ordering corrected so it matches the row-to-Document expectations after the JSON-blob removal
- [x] Class docstring updated to mention `_typed_metadata_columns` as the recommended path before listing manual hooks

### AC3: Transaction ergonomics

- [x] `_ensure_tx` context manager introduced; yields the caller's `tx` if provided, otherwise opens and yields a fresh transaction
- [x] All call sites that previously inlined the `tx or session.transaction()` pattern migrated to `_ensure_tx`

### AC4: Test & DX improvements

- [x] Integration test suite parallelized via `pytest-xdist` (~7× wall-clock speedup)
- [x] `.env.template` added documenting required environment variables for local development
- [x] Unit tests added covering typed-column behavior (defaults, factories, coercion, `include_in_metadata=False`)
- [x] Stale test assertion corrected after `_select_columns` ordering fix

## Dev Notes

- **Why a class attribute, not constructor arg:** Subclassing is the documented extension point for column customization (Epic 4 README). A class attribute keeps the declarative shape adjacent to the rest of the subclass body.
- **Why `include_in_metadata` over `backfill`:** "Backfill" reads as a data-migration term; the flag actually controls read-path projection into `Document.metadata`. Old name was a stumbling block during the pipelines integration review.
- **Why drop `_store_full_metadata_json`:** The "store everything in JSON, also store typed columns" mode was the default but never the recommended path. Removing it collapses the read code to one branch and removes a footgun where typed-column writes and JSON-blob writes could disagree.
- **`_ensure_tx` shape:** Context-manager form chosen over a helper function so call sites remain `with` blocks — matches the existing transaction usage style.

## Out of Scope

- Async API surface (deferred from Epic 4)
- Connection pooling (deferred from Epic 4)
- Changes to the public `VastDBVectorStore` constructor signature
- Migration tooling for existing tables created with the pre-removal `_store_full_metadata_json=True` mode (no known external users yet — package is freshly published)
- New PyPI release; this story batches improvements for the next minor bump, not an immediate publish

### Review Findings

_Pending — to be populated by `bmad-code-review` run on branch `epic-5/post-publication-improvements`._
