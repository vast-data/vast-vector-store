# Story 1.1: Initialize Package Scaffold with uv and Hatchling

Status: done

## Story

As a developer,
I want a properly scaffolded Python package with src-layout, correct dependencies, and ruff linting,
so that I have a working build system and can begin implementing the `VastDBVectorStore` class.

## Acceptance Criteria

1. **Directory structure exists** under the project root with the src-layout shape:
   - `src/langchain_vastdb/__init__.py` exports `VastDBVectorStore` (a stub class inheriting from `langchain_core.vectorstores.VectorStore`).
   - `src/langchain_vastdb/vectorstores.py` contains the stub `VastDBVectorStore` class.
   - `tests/unit_tests/__init__.py` and `tests/integration_tests/__init__.py` exist (empty files are fine).
   - `examples/` directory exists (an empty `.gitkeep` is acceptable to keep it tracked).
   - `LICENSE` file at project root contains the full Apache-2.0 license text.
   - `.gitignore` is configured for Python projects (covers `__pycache__/`, `*.pyc`, `.venv/`, `dist/`, `build/`, `*.egg-info/`, `.pytest_cache/`, `.ruff_cache/`, plus existing `.idea/` and `.claude/settings.local.json` entries).
   - `.python-version` specifies a Python interpreter that satisfies `>=3.10` (recommend `3.10`).

2. **`pyproject.toml` is configured** with:
   - Build backend: `hatchling` (`[build-system] requires = ["hatchling"]`, `build-backend = "hatchling.build"`).
   - Project name: `langchain-vastdb` (note the hyphen — module name is `langchain_vastdb`).
   - `requires-python = ">=3.10"`.
   - License metadata set to Apache-2.0 (`license = { text = "Apache-2.0" }` or `license = "Apache-2.0"` if Hatchling/PEP 639 supports it in the installed version — fall back to text if uncertain).
   - Runtime dependencies: `langchain-core>=0.3`, `vastdb>=2.0.3`.
   - Dev dependencies (under `[dependency-groups] dev = [...]` per uv convention, OR `[project.optional-dependencies] dev = [...]`): `ruff`, `pytest`, `pytest-asyncio`, `langchain-tests`.
   - Hatchling package source pointer so the wheel picks up `src/langchain_vastdb/` (e.g. `[tool.hatch.build.targets.wheel] packages = ["src/langchain_vastdb"]`).
   - Minimal `[tool.ruff]` block (line-length 100, target `py310`) so ruff has explicit config.

3. **`uv sync` installs cleanly** and produces a `uv.lock` file at the project root.

4. **`uv run ruff check .`** passes with **zero warnings**.

5. **Import smoke test:** running `uv run python -c "from langchain_vastdb import VastDBVectorStore; print(VastDBVectorStore)"` succeeds and prints the class object (i.e. `VastDBVectorStore` is importable and is a class).

## Tasks / Subtasks

- [x] **Task 1: Reconcile current project state with target scaffold (AC: #1, #2)**
  - [x] Read existing `pyproject.toml` — it currently declares `name = "vast-vector-store"`, `requires-python = ">=3.13"`, no deps. This must be **rewritten** in place; do NOT run `uv init --lib langchain-vastdb` literally because that creates a *sub*-directory and we are already inside the project root.
  - [x] Confirm there is no existing `src/`, `tests/`, or `examples/` directory before creating them. If any exist with content, STOP and surface the conflict — do not overwrite user work.
  - [x] Leave existing files alone unless explicitly modified by this story: `README.md`, `.gitlab-ci.yml` (Story 1.2 will replace it), `_bmad/`, `_bmad-output/`, `docs/`, `.git/`, `.venv/`, `.cursor/`, `.opencode/`, `.github/`, `.idea/`, `.claude/`.

- [x] **Task 2: Create the src-layout package (AC: #1)**
  - [x] Create `src/langchain_vastdb/__init__.py` that re-exports the stub class: `from langchain_vastdb.vectorstores import VastDBVectorStore` and `__all__ = ["VastDBVectorStore"]`.
  - [x] Create `src/langchain_vastdb/vectorstores.py` with a minimal stub:
    ```python
    """VastDBVectorStore — LangChain VectorStore backed by VAST Database.

    Stub implementation. Full implementation lands in Epic 2.
    """

    from langchain_core.vectorstores import VectorStore


    class VastDBVectorStore(VectorStore):
        """LangChain VectorStore backed by VAST Database.

        Stub class — concrete methods are implemented in Epic 2 stories
        (constructor, add_texts, similarity_search, delete, get_by_ids,
        from_texts, and the 5 protected hook methods).
        """
    ```
  - [x] Do NOT implement any abstract methods yet — the stub is intentionally incomplete. The import smoke test only constructs the *class object*, not an instance, so abstract-method errors will not fire.

- [x] **Task 3: Create test and example skeletons (AC: #1)**
  - [x] Create empty `tests/unit_tests/__init__.py` and `tests/integration_tests/__init__.py`.
  - [x] Create `examples/.gitkeep` (empty file) so the directory is tracked in git. No example scripts in this story — those are Epic 4.

- [x] **Task 4: Write `pyproject.toml` (AC: #2)**
  - [x] Replace the existing `pyproject.toml` with one structured exactly as the canonical example below (see Dev Notes → "Canonical pyproject.toml").
  - [x] Verify `name`, `requires-python`, build-system, dependencies, dev dependency group, hatch wheel packages pointer, and `[tool.ruff]` block are all present.

- [x] **Task 5: Write LICENSE, .gitignore, .python-version (AC: #1)**
  - [x] Create `LICENSE` at project root with the **full Apache-2.0 license text** (not just the SPDX identifier). Source: <https://www.apache.org/licenses/LICENSE-2.0.txt>. Set the year to `2026` and copyright holder to `VAST Data` (or leave generic if unsure — do not invent a name).
  - [x] **Append** standard Python entries to the existing `.gitignore` (do not delete the existing two lines `/.idea/*` and `/.claude/settings.local.json`). Add at minimum: `__pycache__/`, `*.py[cod]`, `*.egg-info/`, `dist/`, `build/`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`, `htmlcov/`, `uv.lock` should **NOT** be in `.gitignore` (lockfiles are committed for libraries+apps in uv's recommended workflow).
  - [x] Create `.python-version` containing `3.10` (single line, no trailing characters).

- [x] **Task 6: Sync and validate (AC: #3, #4, #5)**
  - [x] Run `uv sync` from the project root. Confirm `uv.lock` is generated and `.venv/` is populated. If `uv sync` fails because the existing `.venv/` was created against Python 3.13, delete `.venv/` and retry.
  - [x] Run `uv run ruff check .` and confirm zero warnings. Fix any issues that surface (the stub file should be clean by construction).
  - [x] Run `uv run python -c "from langchain_vastdb import VastDBVectorStore; print(VastDBVectorStore)"` and confirm the class prints.

- [x] **Task 7: Final verification**
  - [x] `git status` — confirm only the expected new/modified files appear: `pyproject.toml`, `.gitignore`, `LICENSE`, `.python-version`, `src/...`, `tests/...`, `examples/.gitkeep`, `uv.lock`.
  - [x] Update the **File List** section below with every file created or modified.

## Dev Notes

### Critical pre-existing state — read this before touching anything

The repo working directory `/Users/omer.mazig/vast-vector-store/` is **already** a `uv`-initialized Python project with placeholder content from an earlier `uv init`. You are NOT scaffolding into an empty directory.

What already exists at the project root (do not delete unless this story explicitly says to modify it):

- `pyproject.toml` — minimal placeholder: `name = "vast-vector-store"`, `requires-python = ">=3.13"`, empty `dependencies = []`. **This story rewrites it.**
- `.gitignore` — two lines (`/.idea/*`, `/.claude/settings.local.json`). **Append to it; do not replace it.**
- `.gitlab-ci.yml` — Auto-DevOps placeholder. **Story 1.2 replaces it. Leave it alone in this story.**
- `README.md` — populated by an earlier planning step. **Leave it alone.**
- `_bmad/`, `_bmad-output/`, `docs/`, `.git/`, `.venv/`, `.cursor/`, `.opencode/`, `.github/`, `.idea/`, `.claude/` — leave alone.

What does **not** yet exist (you will create these): `src/`, `tests/`, `examples/`, `LICENSE`, `.python-version`, `uv.lock`.

> **Why we are not running `uv init --lib langchain-vastdb`:** that command creates a *new sub-directory* called `langchain-vastdb/`. We are already inside the project root and the `_bmad-output/` planning artifacts live here. Running it would either fail or nest the package one level too deep. Instead, manually rewrite `pyproject.toml` and create the `src/langchain_vastdb/` tree by hand. The Architecture's "First Implementation Priority" command snippet ([Source: _bmad-output/planning-artifacts/architecture.md#Implementation Handoff]) is a *conceptual* recipe — the project root has already been initialized; we are completing the rest of the scaffold here.

### Package name vs. module name

- **Distribution name** (PyPI / `pip install` / `pyproject.toml::project.name`): `langchain-vastdb` — hyphenated.
- **Import name / module folder**: `langchain_vastdb` — underscored.

This dual naming is the LangChain partner-package convention ([Source: _bmad-output/planning-artifacts/epics.md#Story 1.1] and [Source: _bmad-output/planning-artifacts/architecture.md#Code Organization]). Do not use `vast-vector-store` anywhere in `pyproject.toml` — that name is left over from the placeholder `uv init`.

### Canonical `pyproject.toml`

Use this as the authoritative shape. Keep it minimal — Story 1.2 will add ruff/pytest CI-specific configuration if needed.

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "langchain-vastdb"
version = "0.0.1"
description = "LangChain VectorStore integration for VAST Database"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "Apache-2.0" }
authors = [
    { name = "VAST Data" },
]
keywords = ["langchain", "vastdb", "vector-store", "vector-database", "rag"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]
dependencies = [
    "langchain-core>=0.3",
    "vastdb>=2.0.3",
]

[dependency-groups]
dev = [
    "ruff",
    "pytest",
    "pytest-asyncio",
    "langchain-tests",
]

[tool.hatch.build.targets.wheel]
packages = ["src/langchain_vastdb"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Why `[dependency-groups]` not `[project.optional-dependencies]`:** uv's native dev-dependency mechanism is the PEP 735 `[dependency-groups]` table. `uv add --dev <pkg>` writes here. `uv sync` installs the `dev` group by default. If your installed `uv` version does not yet support PEP 735, fall back to `[project.optional-dependencies] dev = [...]` — both satisfy the AC.

### File reference: `src/langchain_vastdb/__init__.py`

```python
"""langchain-vastdb — LangChain VectorStore integration for VAST Database."""

from langchain_vastdb.vectorstores import VastDBVectorStore

__all__ = ["VastDBVectorStore"]
```

### Anti-patterns and pitfalls

- ❌ Do NOT run `uv init --lib langchain-vastdb` — see explanation above.
- ❌ Do NOT use `name = "vast-vector-store"` in `pyproject.toml` — the package is `langchain-vastdb`.
- ❌ Do NOT set `requires-python = ">=3.13"` — the project supports `>=3.10` ([Source: _bmad-output/planning-artifacts/architecture.md#Architectural Decisions Provided by Starter] and NFR10 in epics.md).
- ❌ Do NOT delete the existing `.gitignore` entries — append to them.
- ❌ Do NOT delete or rewrite `.gitlab-ci.yml` in this story — that is Story 1.2's job.
- ❌ Do NOT add `uv.lock` to `.gitignore` — uv recommends committing the lockfile for both libraries and apps so CI is reproducible.
- ❌ Do NOT implement any concrete behavior on `VastDBVectorStore` — it is a stub. Real methods come in Epic 2 (Stories 2.1–2.4).
- ❌ Do NOT import `vastdb` in the stub `vectorstores.py`. The import smoke test should not require the VastDB SDK to be installed yet — although it *will* be after `uv sync`, keeping the stub import-light avoids hidden dependencies.
- ❌ Do NOT add `__init__.py` inside `tests/` itself (only inside `tests/unit_tests/` and `tests/integration_tests/`). Pytest test discovery works either way and the canonical layout has subdirectory inits only.
- ❌ Do NOT scaffold any `_utils.py`, helper modules, or example scripts. The architecture explicitly mandates a single-file implementation in `vectorstores.py` ([Source: _bmad-output/planning-artifacts/architecture.md#File Organization Patterns]).

### What this story does NOT cover

- `.gitlab-ci.yml` rewrite — **Story 1.2**.
- `VastDBVectorStore` constructor or methods — **Story 2.1+**.
- Unit tests — **Story 2.5**.
- Integration tests — **Story 3.1**.
- README content updates — **Story 4.1**.
- Example scripts — **Story 4.2**.
- PyPI publication — **Story 4.3**.

Stay narrowly scoped. The goal is a clean, lintable, importable scaffold — nothing more.

### Architecture compliance summary (the parts that bind this story)

| Constraint | Source | What this story does |
|---|---|---|
| Build backend = `hatchling` | architecture.md#Build System | `[build-system].build-backend = "hatchling.build"` |
| Linter = `ruff` | architecture.md#Linting & Formatting | `ruff` in dev deps + `[tool.ruff]` block |
| Test framework = `pytest` + `langchain-tests` | architecture.md#Testing Framework | both in dev deps |
| Python `>=3.10`, target 3.10–3.13 | architecture.md, NFR10 | `requires-python`, classifiers |
| Runtime deps `langchain-core>=0.3`, `vastdb>=2.0.3` | architecture.md, NFR8/NFR9 | `[project].dependencies` |
| src-layout `src/langchain_vastdb/` | architecture.md#Code Organization, #Complete Project Directory Structure | created in Task 2 |
| Single public export `VastDBVectorStore` from `langchain_vastdb` | architecture.md#Architectural Boundaries, FR26 | `__init__.py` re-export |
| Single-file implementation (`vectorstores.py`) | architecture.md#File Organization Patterns | only `vectorstores.py` is created in this story |
| License = Apache-2.0 | architecture.md#Complete Project Directory Structure, epics.md Story 1.1 | full license text in `LICENSE` |

### Testing standards (for this story)

There are no automated tests to write in this story. The "tests" are:

1. `uv sync` succeeds and produces `uv.lock`.
2. `uv run ruff check .` exits with code 0 and zero warnings.
3. `uv run python -c "from langchain_vastdb import VastDBVectorStore; print(VastDBVectorStore)"` exits with code 0 and prints the class repr.

Run all three before marking the story complete.

### Project Structure Notes

This story creates the directory tree exactly as specified in [Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure], minus the files owned by later stories (`.gitlab-ci.yml` rewrite, README updates, example scripts, real `vectorstores.py` content, real test files). No structural variances expected.

The one **detected variance** from the ideal greenfield scaffold: the project root already contains BMAD planning output (`_bmad/`, `_bmad-output/`, `docs/`) and a placeholder `uv init` `pyproject.toml`. Both are intentional and pre-existing — work *around* them, do not delete them.

### References

- Story requirements and ACs: [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1: Initialize Package Scaffold with uv and Hatchling]
- Starter command and rationale: [Source: _bmad-output/planning-artifacts/architecture.md#Selected Starter: Hybrid (uv init + LangChain conventions)]
- Directory tree: [Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure]
- Package boundary (single export): [Source: _bmad-output/planning-artifacts/architecture.md#Architectural Boundaries]
- Single-file implementation rule: [Source: _bmad-output/planning-artifacts/architecture.md#File Organization Patterns]
- NFRs that constrain dependencies: NFR8 (langchain-core>=0.3), NFR9 (vastdb>=2.0.3), NFR10 (Python 3.10–3.13), NFR15 (ruff zero-warnings) — [Source: _bmad-output/planning-artifacts/epics.md#NonFunctional Requirements]
- FR coverage: FR25 (pip/uv installable), FR26 (single public class export) — [Source: _bmad-output/planning-artifacts/epics.md#FR Coverage Map]
- Implementation readiness sign-off: [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-04-07.md#Recommendations]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Deleted existing `.venv/` (Python 3.13) before `uv sync` to match `requires-python = ">=3.10"` / `.python-version = 3.10`.
- Added ruff `exclude` for `.claude`, `.cursor`, `.opencode`, `.github`, `_bmad`, `_bmad-output`, `docs` directories — these contain BMAD/tool files with Python that are not part of the package and fail linting.

### Completion Notes List

- All 7 tasks completed successfully.
- `pyproject.toml` rewritten with hatchling build backend, langchain-vastdb package name, correct dependencies, and dev dependency group.
- Stub `VastDBVectorStore` class created inheriting from `langchain_core.vectorstores.VectorStore` — no methods implemented per story scope.
- All 3 validation checks pass: `uv sync` (produces `uv.lock`), `ruff check .` (zero warnings), import smoke test (class prints).
- Added ruff `exclude` list for non-package directories that contain Python files from BMAD tooling — minor deviation from canonical `pyproject.toml` to achieve the AC requirement of zero ruff warnings.

### File List

**Created:**
- `src/langchain_vastdb/__init__.py` — re-exports `VastDBVectorStore`
- `src/langchain_vastdb/vectorstores.py` — stub `VastDBVectorStore` class
- `tests/unit_tests/__init__.py` — empty init for unit test package
- `tests/integration_tests/__init__.py` — empty init for integration test package
- `examples/.gitkeep` — placeholder to track examples directory
- `LICENSE` — full Apache-2.0 license text, copyright 2026 VAST Data
- `.python-version` — contains `3.10`
- `uv.lock` — generated lockfile

**Modified:**
- `pyproject.toml` — rewritten with langchain-vastdb package configuration
- `.gitignore` — appended standard Python entries

### Review Findings

- [x] [Review][Defer] `langchain-tests` dev dependency unpinned — risk of breakage on upstream upgrade [pyproject.toml:41] — deferred, pre-existing (matches canonical spec)
- [x] [Review][Defer] sdist has no exclude config — will leak `_bmad/`, `_bmad-output/`, `docs/`, `.gitlab-ci.yml` if published [pyproject.toml] — deferred, address before PyPI publication (Story 4.3)
- [x] [Review][Defer] `langchain-core>=0.3` allows wide version range (0.x to 1.x) — lockfile resolves 1.2.28 [pyproject.toml:31] — deferred, tighten when Epic 2 implements real API usage
- [x] [Review][Defer] `readme = "README.md"` embeds GitLab boilerplate with internal URL — deferred, Story 4.1 will rewrite README
- [x] [Review][Defer] No `py.typed` marker (PEP 561) for type checker support — deferred, add when Epic 2 introduces typed signatures

## Change Log

- 2026-04-09: Story 1.1 implemented — package scaffold with src-layout, pyproject.toml, LICENSE, .gitignore, .python-version, test/example skeletons. All ACs satisfied.
- 2026-04-09: Code review complete — 0 patches, 5 deferred, 8 dismissed. All ACs verified. Story marked done.