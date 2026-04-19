# Story 4.3: Migration Guide & PyPI Publication

Status: done

## Story

As a developer maintaining an existing VectorStore subclass,
I want a clear migration guide and a published PyPI package,
so that I can migrate my existing store to inherit from VastDBVectorStore and install it via pip.

## Acceptance Criteria

1. **AC1 — Migration guide step-by-step instructions**
   **Given** the Migration Guide document (`docs/migration-guide.md`)
   **When** a developer reads it
   **Then** it provides step-by-step instructions:
   1. Change parent class from `VectorStore` to `VastDBVectorStore`
   2. Move storage operations into hook method overrides (with mapping table showing which methods map to which hooks)
   3. Delete inherited LangChain interface methods (`similarity_search`, `add_texts`, `from_texts`, etc.)
   4. Keep all domain-specific methods unchanged
   5. Run existing test suite to validate

2. **AC2 — Before/after code comparison**
   **Given** the Migration Guide
   **When** a developer follows it for an existing store
   **Then** the guide includes a before/after code comparison showing the LOC reduction and hook override pattern

3. **AC3 — `uv build` produces valid artifacts**
   **Given** the package is ready for publication
   **When** `uv build` is run
   **Then** it produces a valid wheel and sdist with correct metadata (name: `langchain-vastdb`, version, license, dependencies, Python version)

4. **AC4 — Package installability verification**
   **Given** the built package
   **When** the wheel is installed locally with `pip install dist/langchain_vastdb-*.whl`
   **Then** `from langchain_vastdb import VastDBVectorStore` works, and the package has no dependency conflicts with other LangChain partner packages

5. **AC5 — README links to migration guide**
   **Given** the README.md
   **When** viewed by a developer
   **Then** it includes a link to the migration guide in a discoverable location (near the Subclassing Guide or Examples section)

## Tasks / Subtasks

- [x] Task 1: Create migration guide document (AC: 1, 2)
  - [x] 1.1 Create `docs/migration-guide.md` with step-by-step migration instructions
  - [x] 1.2 Add hook method mapping table (LangChain interface method -> VastDBVectorStore hook)
  - [x] 1.3 Write before/after code comparison with LOC reduction
  - [x] 1.4 Include validation checklist for post-migration testing
- [x] Task 2: Add migration guide link to README (AC: 5)
  - [x] 2.1 Add a "Migration Guide" section or link in README.md near the Subclassing Guide or Examples section
- [x] Task 3: Verify build artifacts (AC: 3)
  - [x] 3.1 Run `uv build` and confirm wheel + sdist are produced
  - [x] 3.2 Inspect wheel metadata: name, version, license, dependencies, Python requires
  - [x] 3.3 Inspect sdist contents: ensure no internal files (_bmad/, .claude/, etc.) leak
- [x] Task 4: Verify package installability (AC: 4)
  - [x] 4.1 Create a temporary venv, install the wheel, verify `from langchain_vastdb import VastDBVectorStore` succeeds
  - [x] 4.2 Verify no dependency conflicts with `pip check`

### Review Findings

_Code review of story 4-3 — 2026-04-19 (Blind Hunter + Edge Case Hunter + Acceptance Auditor)_

- [x] [Review][Patch] `from_texts` in "before" example missing `@classmethod` decorator [docs/migration-guide.md] — Added decorator to match the `cls` parameter usage.

_Dismissed as noise (2): missing import statements in "before" code snippet (intentional abbreviation), LOC claim vs shown snippet length (text clearly says "~200 LOC" for a complete implementation while showing an abridged version)._

## Dev Notes

### Migration Guide Content

The migration guide maps LangChain's `VectorStore` public interface methods to VastDBVectorStore's protected hook methods:

| LangChain VectorStore method | VastDBVectorStore hook | Purpose |
|---|---|---|
| `add_texts()` / `add_documents()` | `_insert_vectors()` | Record insertion |
| `similarity_search()` / `similarity_search_by_vector()` | `_vector_search()` | Similarity queries |
| `delete()` | `_delete_by_ids()` | Document deletion |
| `get_by_ids()` | `_get_by_ids()` | ID-based retrieval |
| (result conversion) | `_row_to_document()` | Row-to-Document mapping |

Hook signatures are already documented in README.md § "Subclassing Guide" — reference those directly, don't duplicate. The `tx: Transaction | None = None` kwarg pattern is consistent across all hooks.

### Before/After Example Structure

The before/after comparison should show a hypothetical `MyCustomVectorStore(VectorStore)` migrating to `MyCustomVectorStore(VastDBVectorStore)`. Key points to highlight:
- **Before:** subclass must implement `add_texts`, `similarity_search`, `from_texts`, `delete`, embedding logic, transaction handling, PyArrow batch building, filter conversion — ~200+ LOC of boilerplate
- **After:** subclass overrides only the hooks it needs (e.g., `_insert_vectors` for typed metadata, `_row_to_document` for custom deserialization) — ~30-50 LOC total

Use the existing `examples/subclassing.py` as a reference for the "after" pattern.

### Build Verification

The pyproject.toml is already correctly configured:
- `name = "langchain-vastdb"`, `version = "0.0.1"`, `license = "Apache-2.0"`
- `requires-python = ">=3.10"`, classifiers for 3.10-3.13
- `dependencies = ["langchain-core>=1.0,<2", "vastdb>=2.0.3"]`
- `[tool.hatch.build]` exclude list already blocks `_bmad/`, `_bmad-output/`, `.claude/`, `.cursor/`, `.opencode/`, `.github/`, `.gitlab-ci.yml`, `.idea/`, `docs/`
- `[tool.hatch.build.targets.wheel]` packages = `["src/langchain_vastdb"]`

The CI publish job in `.gitlab-ci.yml` is already configured for PyPI Trusted Publishing on `v*` tags. This story validates the build locally; actual PyPI publication happens later via CI tag push (out of scope for this story's dev work).

### Deferred Work Item

From story 4-1 review: "AC#4 requires a link to the migration guide in the README. The migration guide does not exist yet (Story 4.3). Add link when Story 4.3 is complete." — This is Task 2 above.

### Important Constraint

**Do NOT actually publish to PyPI.** This story validates build artifacts locally and verifies installability from the local wheel. The actual PyPI publication will happen via CI pipeline on a version tag push, which is a deployment operation outside story scope.

### Project Structure Notes

- Migration guide goes in `docs/migration-guide.md` — the `docs/` directory exists but is currently empty. It is excluded from wheel/sdist builds via `[tool.hatch.build]` exclude, which is correct (docs are for the repo, not the package).
- No new source files under `src/` are needed.
- No new dependencies are needed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md § Story 4.3]
- [Source: _bmad-output/planning-artifacts/architecture.md § CI/CD & Publishing]
- [Source: README.md § Subclassing Guide — hook method signatures and table]
- [Source: pyproject.toml — build config, metadata, excludes]
- [Source: .gitlab-ci.yml — publish stage configuration]
- [Source: _bmad-output/implementation-artifacts/deferred-work.md § story 4-1 deferred item]
- [Source: examples/subclassing.py — reference for "after" migration pattern]

## Dev Agent Record

### Agent Model Used

Claude Opus 4

### Debug Log References

### Completion Notes List

- Created docs/migration-guide.md with 5-step migration walkthrough, hook mapping table, before/after code comparison (~200 LOC before -> ~40 LOC after), and post-migration checklist.
- Added "Migration Guide" section to README.md between Examples and Development sections with link to docs/migration-guide.md.
- Verified `uv build` produces valid wheel (langchain_vastdb-0.0.1-py3-none-any.whl) and sdist with correct metadata: name=langchain-vastdb, version=0.0.1, license=Apache-2.0, requires-python>=3.10, deps=[langchain-core>=1.0,<2, vastdb>=2.0.3].
- Verified sdist excludes internal files (_bmad/, .claude/, .cursor/, etc.).
- Verified wheel install succeeds in isolated venv, `from langchain_vastdb import VastDBVectorStore` works, `pip check` reports no dependency conflicts.
- All 66 unit tests pass, linter clean.

### File List

- docs/migration-guide.md (new)
- README.md (modified — added Migration Guide section)

