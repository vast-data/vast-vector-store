# Story 1.2: Configure GitLab CI/CD Pipeline

Status: in-progress

## Story

As a developer,
I want a GitLab CI/CD pipeline that runs linting, unit tests, integration tests, and handles PyPI publishing,
so that every merge request is validated automatically and releases are published securely.

## Acceptance Criteria

1. **Pipeline stages run on every MR** in this order:
   - **lint**: `uv run ruff check .` passes with zero warnings.
   - **unit-test**: `uv run pytest tests/unit_tests/` passes.
   - **integration-test**: `uv run pytest tests/integration_tests/` runs against the VAST cluster.

2. **Integration test stage** connects to the always-available VAST cluster using CI/CD environment variables: `VASTDB_ENDPOINT`, `VASTDB_ACCESS_KEY`, `VASTDB_SECRET_KEY`, `VASTDB_TEST_BUCKET`, `VASTDB_TEST_SCHEMA`.

3. **Release publish stage** triggers only when a release tag is pushed (e.g., `v0.1.0`). It builds the package with `uv build` and publishes to PyPI using Trusted Publishing (OIDC tokens, no stored secrets).

4. **Python version matrix**: unit tests run against Python 3.10, 3.11, 3.12, and 3.13.

5. **Ruff check passes**: `uv run ruff check .` exits zero after the pipeline file is in place (i.e., the `.gitlab-ci.yml` itself does not introduce any ruff regressions).

6. **Import smoke test still works**: `uv run python -c "from langchain_vastdb import VastDBVectorStore; print(VastDBVectorStore)"` continues to succeed (no scaffold regressions).

## Tasks / Subtasks

- [ ] **Task 1: Replace `.gitlab-ci.yml` with project-specific pipeline (AC: #1, #2, #3, #4)**
  - [ ] Read the existing `.gitlab-ci.yml` (it is an Auto-DevOps placeholder with no project-specific logic) and **replace it entirely** with a custom pipeline.
  - [ ] Define four stages: `lint`, `test`, `integration-test`, `publish`.
  - [ ] Use the official uv Docker image `ghcr.io/astral-sh/uv:$UV_VERSION-python$PYTHON_VERSION-$BASE_LAYER` as the base image for all jobs. Pin `UV_VERSION` to a recent stable version (e.g., `0.7` or later). Use `trixie-slim` or `bookworm-slim` as the base layer.
  - [ ] Configure uv caching: set `UV_CACHE_DIR: .uv-cache`, cache it between runs keyed on `uv.lock`, and prune with `uv cache prune --ci` in `after_script`.
  - [ ] Set `UV_LINK_MODE: copy` as a global variable (required for Docker environments).

- [ ] **Task 2: Implement lint job (AC: #1)**
  - [ ] Create a `lint` job in the `lint` stage.
  - [ ] Script: `uv sync --locked` then `uv run ruff check .`.
  - [ ] Use a single Python version (3.12 is fine for linting).

- [ ] **Task 3: Implement unit-test job with Python matrix (AC: #1, #4)**
  - [ ] Create a `unit-test` job in the `test` stage.
  - [ ] Use `parallel:matrix` to run against Python 3.10, 3.11, 3.12, and 3.13.
  - [ ] Override the `PYTHON_VERSION` variable per matrix entry and use the corresponding uv Docker image.
  - [ ] Script: `uv sync --locked` then `uv run pytest tests/unit_tests/ -v`.
  - [ ] This job has no cluster dependency -- it uses mocked VastDB SDK.

- [ ] **Task 4: Implement integration-test job (AC: #1, #2)**
  - [ ] Create an `integration-test` job in the `integration-test` stage.
  - [ ] Use a single Python version (3.12).
  - [ ] Script: `uv sync --locked` then `uv run pytest tests/integration_tests/ -v`.
  - [ ] Require CI/CD variables to be set at the project level in GitLab: `VASTDB_ENDPOINT`, `VASTDB_ACCESS_KEY`, `VASTDB_SECRET_KEY`, `VASTDB_TEST_BUCKET`, `VASTDB_TEST_SCHEMA`. These are read by the test fixtures at runtime (Story 3.1 will implement the test fixtures).
  - [ ] The job should be configured to **allow failure** (`allow_failure: true`) until Story 3.1 implements the integration tests -- otherwise the pipeline will block on an empty test directory. Add a `# TODO: remove allow_failure after Story 3.1` comment.

- [ ] **Task 5: Implement publish job with Trusted Publishing (AC: #3)**
  - [ ] Create a `publish` job in the `publish` stage.
  - [ ] Run only on tag pushes matching `v*` pattern (e.g., `v0.1.0`): use `rules: - if: $CI_COMMIT_TAG =~ /^v/`.
  - [ ] Configure `id_tokens` section with `PYPI_ID_TOKEN` using `aud: pypi` for PyPI OIDC Trusted Publishing.
  - [ ] Script: `uv build` then `uv publish --token $PYPI_ID_TOKEN`.
  - [ ] Add a comment noting that the project must be registered as a trusted publisher on PyPI, linked to the GitLab project path, before the first publish will work.

- [ ] **Task 6: Validate pipeline locally (AC: #5, #6)**
  - [ ] Run `uv run ruff check .` to confirm zero warnings (no regressions from editing `.gitlab-ci.yml`).
  - [ ] Run `uv run python -c "from langchain_vastdb import VastDBVectorStore; print(VastDBVectorStore)"` to confirm the import smoke test still passes.
  - [ ] Review the `.gitlab-ci.yml` visually for YAML syntax correctness (proper indentation, no tabs, valid GitLab CI syntax).

## Dev Notes

### Critical: this story ONLY writes `.gitlab-ci.yml`

The **only file you create or modify** in this story is `.gitlab-ci.yml` at the project root. Do NOT touch `pyproject.toml`, source code, or test files. Story 2.5 writes unit tests, Story 3.1 writes integration tests.

### Existing `.gitlab-ci.yml` -- replace entirely

The current `.gitlab-ci.yml` is an Auto-DevOps placeholder generated by GitLab. It includes the `Auto-DevOps.gitlab-ci.yml` template and has stages like `build`, `deploy`, `staging`, `canary`, `production` that are irrelevant to this Python library project. **Replace the entire file** -- do not try to extend it.

### Previous story intelligence (Story 1.1)

Key learnings from Story 1.1 that affect this story:

- **ruff exclude list**: The `pyproject.toml` already has a ruff exclude for `.claude`, `.cursor`, `.opencode`, `.github`, `_bmad`, `_bmad-output`, `docs` directories. No changes to ruff config needed in this story.
- **uv.lock is committed**: The lockfile is tracked in git. Use `uv sync --locked` in CI to install from the lockfile deterministically.
- **Python version**: `.python-version` is set to `3.10`. The CI matrix will test all supported versions (3.10-3.13) using different Docker images.
- **Build backend**: Hatchling is configured. `uv build` will produce the wheel and sdist.

### uv Docker images for GitLab CI

The official uv Docker images follow this naming pattern:

```
ghcr.io/astral-sh/uv:{UV_VERSION}-python{PYTHON_VERSION}-{BASE_LAYER}
```

- Use variables to make the image configurable.
- For the Python matrix, override `PYTHON_VERSION` per matrix entry.
- Use `bookworm-slim` or `trixie-slim` as the base Debian layer.

### uv CI best practices

- Set `UV_LINK_MODE: copy` in global variables -- required in Docker containers where hard/soft links may not work.
- Set `UV_CACHE_DIR: .uv-cache` and cache it between runs with a key based on `uv.lock`.
- Run `uv cache prune --ci` in `after_script` to reduce cache size.
- Use `uv sync --locked` to install dependencies from the lockfile. The `--locked` flag ensures the lockfile matches `pyproject.toml` and fails fast if not.

### PyPI Trusted Publishing with GitLab CI

PyPI supports GitLab CI as an OIDC trusted publisher. The mechanism:

1. **On PyPI**: Register a "trusted publisher" linked to the GitLab project path, environment name, and ref pattern.
2. **In `.gitlab-ci.yml`**: Add an `id_tokens` section to the publish job that requests an OIDC token with `aud: pypi`.
3. **In the script**: `uv publish` can accept the OIDC token via `--token $PYPI_ID_TOKEN`.

This eliminates the need for stored PyPI API tokens -- the CI job proves its identity via OIDC.

**Important**: The trusted publisher must be configured on PyPI (https://pypi.org/manage/account/publishing/) before the first publish. This is a manual one-time setup step performed by the project maintainer, not by CI. Document it with a comment in the YAML.

### Canonical `.gitlab-ci.yml` structure

Use this as the authoritative reference for the pipeline structure:

```yaml
variables:
  UV_VERSION: "0.7"
  PYTHON_VERSION: "3.12"
  BASE_LAYER: "bookworm-slim"
  UV_CACHE_DIR: ".uv-cache"
  UV_LINK_MODE: "copy"

stages:
  - lint
  - test
  - integration-test
  - publish

# -- Lint job: ruff check on a single Python version --
lint:
  stage: lint
  image: ghcr.io/astral-sh/uv:${UV_VERSION}-python${PYTHON_VERSION}-${BASE_LAYER}
  cache:
    - key:
        files:
          - uv.lock
      paths:
        - ${UV_CACHE_DIR}
  script:
    - uv sync --locked
    - uv run ruff check .
  after_script:
    - uv cache prune --ci

# -- Unit tests: Python version matrix --
unit-test:
  stage: test
  image: ghcr.io/astral-sh/uv:${UV_VERSION}-python${PYTHON_VERSION}-${BASE_LAYER}
  parallel:
    matrix:
      - PYTHON_VERSION: ["3.10", "3.11", "3.12", "3.13"]
  cache:
    - key:
        files:
          - uv.lock
      paths:
        - ${UV_CACHE_DIR}
  script:
    - uv sync --locked
    - uv run pytest tests/unit_tests/ -v
  after_script:
    - uv cache prune --ci

# -- Integration tests: real VAST cluster --
integration-test:
  stage: integration-test
  image: ghcr.io/astral-sh/uv:${UV_VERSION}-python${PYTHON_VERSION}-${BASE_LAYER}
  # TODO: remove allow_failure after Story 3.1 implements integration tests
  allow_failure: true
  cache:
    - key:
        files:
          - uv.lock
      paths:
        - ${UV_CACHE_DIR}
  script:
    - uv sync --locked
    - uv run pytest tests/integration_tests/ -v
  after_script:
    - uv cache prune --ci
  # These variables must be set at the GitLab project level:
  # VASTDB_ENDPOINT, VASTDB_ACCESS_KEY, VASTDB_SECRET_KEY,
  # VASTDB_TEST_BUCKET, VASTDB_TEST_SCHEMA

# -- Publish to PyPI: only on version tags --
publish:
  stage: publish
  image: ghcr.io/astral-sh/uv:${UV_VERSION}-python${PYTHON_VERSION}-${BASE_LAYER}
  id_tokens:
    PYPI_ID_TOKEN:
      aud: pypi
  rules:
    - if: $CI_COMMIT_TAG =~ /^v/
  script:
    - uv build
    - uv publish --token $PYPI_ID_TOKEN
  # NOTE: Before first publish, register this project as a trusted publisher
  # on PyPI at https://pypi.org/manage/account/publishing/
  # Link it to this GitLab project's path, environment, and tag pattern.
```

**Adapt this reference** -- do not copy blindly. Verify the image tag format, variable interpolation syntax (`${VAR}` vs `$VAR`), and GitLab CI features (`parallel:matrix`, `id_tokens`, `rules`) are valid for the target GitLab version.

### Environment variables required at GitLab project level

| Variable | Description | Used by |
|---|---|---|
| `VASTDB_ENDPOINT` | VAST cluster endpoint URL (e.g., `https://vast.example.com:443`) | integration-test job |
| `VASTDB_ACCESS_KEY` | VAST S3 access key | integration-test job |
| `VASTDB_SECRET_KEY` | VAST S3 secret key (mark as **masked** and **protected**) | integration-test job |
| `VASTDB_TEST_BUCKET` | VAST bucket for integration test tables | integration-test job |
| `VASTDB_TEST_SCHEMA` | VAST schema for integration test tables | integration-test job |

These are **not** set in the `.gitlab-ci.yml` file -- they are configured in the GitLab project settings (Settings > CI/CD > Variables). The `.gitlab-ci.yml` only documents which variables are expected.

### Architecture compliance summary

| Constraint | Source | What this story does |
|---|---|---|
| CI platform = GitLab CI/CD | architecture.md#CI/CD & Publishing | Replace Auto-DevOps with custom `.gitlab-ci.yml` |
| Lint on every MR | architecture.md#CI/CD & Publishing | `lint` stage runs `ruff check .` |
| Unit tests on every MR | architecture.md#CI/CD & Publishing | `unit-test` stage with Python matrix |
| Integration tests on every MR | architecture.md#CI/CD & Publishing | `integration-test` stage (allow_failure until 3.1) |
| Python 3.10-3.13 matrix | NFR10, epics.md#Story 1.2 | `parallel:matrix` with 4 Python versions |
| PyPI Trusted Publishing | architecture.md#CI/CD & Publishing | `publish` stage with OIDC `id_tokens` |
| Development commands: `uv sync`, `uv run ruff check .`, `uv run pytest` | architecture.md#Development Workflow | All CI jobs use these exact commands |

### Anti-patterns and pitfalls

- Do NOT keep the Auto-DevOps `include: - template: Auto-DevOps.gitlab-ci.yml` -- replace the entire file.
- Do NOT use `pip install` or `pip` commands -- use `uv sync --locked` and `uv run`.
- Do NOT store PyPI tokens as CI/CD variables -- use Trusted Publishing OIDC tokens instead.
- Do NOT hardcode VAST cluster credentials in the pipeline file -- they come from GitLab CI/CD variables.
- Do NOT run integration tests without `allow_failure: true` until Story 3.1 implements them -- the test directory is empty and pytest will exit with error code on no tests collected.
- Do NOT add a `before_script` that runs `uv sync` globally -- keep sync in each job's script for clarity and to avoid cache invalidation issues.
- Do NOT modify `pyproject.toml` in this story -- the build configuration is already correct from Story 1.1.

### What this story does NOT cover

- Writing unit tests -- **Story 2.5**.
- Writing integration test fixtures (VAST cluster connection, table lifecycle) -- **Story 3.1**.
- README updates -- **Story 4.1**.
- Actual PyPI registration as trusted publisher (manual step) -- **Story 4.3**.
- `uv publish` execution (happens when a tag is pushed after Story 4.3) -- **Story 4.3**.

### Project Structure Notes

This story modifies exactly one file at the project root:

```
langchain-vastdb/
+-- .gitlab-ci.yml              # REPLACED: Auto-DevOps -> custom pipeline
```

No structural changes to the rest of the project. All other files remain as Story 1.1 left them.

### References

- Story requirements and ACs: [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2: Configure GitLab CI/CD Pipeline]
- CI/CD architecture decision: [Source: _bmad-output/planning-artifacts/architecture.md#CI/CD & Publishing]
- Development workflow commands: [Source: _bmad-output/planning-artifacts/architecture.md#Development Workflow]
- Python version matrix requirement: NFR10 in [Source: _bmad-output/planning-artifacts/epics.md#NonFunctional Requirements]
- Test directory structure: [Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure]
- uv GitLab CI guide: https://docs.astral.sh/uv/guides/integration/gitlab/
- PyPI Trusted Publishing: https://docs.pypi.org/trusted-publishers/

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List