---
title: 'Align env vars to single-underscore and AWS standard names'
type: 'refactor'
created: '2026-05-03'
status: 'done'
baseline_commit: '57fbd18b9126c565d84f0b8e52875f2dcc037d84'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The codebase uses a double-underscore convention (`VASTDB__FOO`) for all env vars, which diverges from both AWS standard names (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_ENDPOINT_URL`) that `vastdb.connect` already reads natively and from the simpler single-underscore style preferred going forward.

**Approach:** Rename all `VASTDB__*` env vars to single-underscore equivalents; for the three connection credential vars (endpoint, access key, secret key) adopt the AWS standard names that `vastdb.connect` picks up automatically when None is passed; make `endpoint`, `access_key`, and `secret_key` optional (`None` default) in `from_connection_params` so callers can omit them entirely and let the SDK resolve them from env.

## Boundaries & Constraints

**Always:**
- Keep `VASTDB_ALLOW_FALLBACK` unchanged (it already uses single underscore).
- For tunnel-specific CI vars (SSH jump host, username, password), use single-underscore `VASTDB_*` names (they have no AWS equivalent).
- The `__init__` env-var fallbacks (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) added by the user must be preserved as-is.
- All code changes must be consistent across source, tests, examples, CI config, and `.env.template`.

**Ask First:** None anticipated — the mapping is fully deterministic.

**Never:**
- Don't change any behavior — this is a rename only.
- Don't add new env var reads beyond what's needed to complete the rename.
- Don't modify `_bmad-output/` planning/implementation artifact markdown files — they are historical records.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| All AWS env vars set | `AWS_S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `VASTDB_BUCKET` in env | `from_connection_params()` with no credential args builds session, tests pass | N/A |
| Only `VASTDB_BUCKET` missing | Required vars absent | pytest skips integration tests with clear missing-var message | Skip via `pytestmark` |
| Legacy double-underscore vars set (old .env) | `VASTDB__ENDPOINT` etc. in env | Not picked up — no backwards-compat shim | User must update `.env` |

</frozen-after-approval>

## Code Map

- `src/langchain_vastdb/vectorstores.py` -- `from_connection_params`: make `endpoint`, `access_key`, `secret_key` optional
- `tests/integration_tests/test_vectorstore.py` -- rename all `VASTDB__*` to new names
- `examples/basic_usage.py` -- rename env vars
- `examples/rag_pipeline.py` -- rename env vars
- `examples/subclassing.py` -- rename env vars
- `examples/filtered_search.py` -- rename env vars
- `.env.template` -- rename all var names, add AWS-standard names for connection params
- `.gitlab-ci.yml` -- rename CI vars in comments and `export` statement
- `scripts/ci-tunnel.sh` -- rename tunnel-specific vars

## Tasks & Acceptance

**Execution:**
- [x] `src/langchain_vastdb/vectorstores.py` -- Change `endpoint: str`, `access_key: str`, `secret_key: str` to `| None = None` in `from_connection_params`; update the docstring to reflect that each falls back to `AWS_S3_ENDPOINT_URL` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` respectively (via `vastdb.connect` env fallback)
- [x] `tests/integration_tests/test_vectorstore.py` -- Replace all `VASTDB__ENDPOINT` → `AWS_S3_ENDPOINT_URL`, `VASTDB__ACCESS_KEY` → `AWS_ACCESS_KEY_ID`, `VASTDB__SECRET_KEY` → `AWS_SECRET_ACCESS_KEY`, `VASTDB__BUCKET` → `VASTDB_BUCKET`, `VASTDB__ADBC_DRIVER_PATH` → `VASTDB_ADBC_DRIVER_PATH`, `VASTDB__ADBC_ENDPOINT` → `VASTDB_ADBC_ENDPOINT`; update docstring references
- [x] `examples/basic_usage.py` -- Apply same env var rename (endpoint/access/secret → AWS names, bucket/ADBC → single-underscore VASTDB)
- [x] `examples/rag_pipeline.py` -- Same renames as basic_usage.py
- [x] `examples/subclassing.py` -- Same renames
- [x] `examples/filtered_search.py` -- Same renames
- [x] `.env.template` -- Rewrite with new var names: `AWS_S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `VASTDB_BUCKET`, `VASTDB_ADBC_ENDPOINT`, `VASTDB_ADBC_DRIVER_PATH`
- [x] `.gitlab-ci.yml` -- In the `export` line change `VASTDB__ENDPOINT` → `AWS_S3_ENDPOINT_URL`; update the Required CI/CD variables comment block to use new names (`AWS_*` for creds, `VASTDB_SSH_JUMP_HOST`, `VASTDB_ENDPOINT_USERNAME`, `VASTDB_ENDPOINT_PASSWORD`, `VASTDB_BUCKET`)
- [x] `scripts/ci-tunnel.sh` -- Rename `VASTDB__ENDPOINT` → `AWS_S3_ENDPOINT_URL` (the raw host:port tunnel target), `VASTDB__SSH_JUMP_HOST` → `VASTDB_SSH_JUMP_HOST`, `VASTDB__ENDPOINT_USERNAME` → `VASTDB_ENDPOINT_USERNAME`, `VASTDB__ENDPOINT_PASSWORD` → `VASTDB_ENDPOINT_PASSWORD`; update header comment; after tunnel is up the calling shell exports `AWS_S3_ENDPOINT_URL` (not `VASTDB__ENDPOINT`)

**Acceptance Criteria:**
- Given `from_connection_params` is called with no `endpoint`, `access_key`, or `secret_key` args, when `AWS_S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` are set in the environment, then `vastdb.connect` picks them up automatically (no `TypeError` for missing required args).
- Given the REQUIRED_ENV list in `test_vectorstore.py`, when any of `AWS_S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or `VASTDB_BUCKET` is absent, then the integration test module is skipped with a clear message naming the missing vars.
- Given `.env.template` and example scripts, when a developer copies the template and sets values, then running any example with the new var names connects successfully (no reference to old `VASTDB__*` names).
- Given the CI pipeline, when GitLab CI/CD variables use the new names, then the tunnel script and integration test job use them without the double-underscore pattern.

## Design Notes

**Env var mapping (old → new):**

| Old | New | Notes |
|-----|-----|-------|
| `VASTDB__ENDPOINT` | `AWS_S3_ENDPOINT_URL` | Full URL used by `vastdb.connect` and integration tests |
| `VASTDB__ENDPOINT` (CI GitLab var, raw `host:port` tunnel target) | `AWS_S3_ENDPOINT_URL` | CI-only; parsed by `ci-tunnel.sh` to set up SSH tunnel; after tunnel is up, CI exports `AWS_S3_ENDPOINT_URL=https://localhost:18151` |
| `VASTDB__ACCESS_KEY` | `AWS_ACCESS_KEY_ID` | |
| `VASTDB__SECRET_KEY` | `AWS_SECRET_ACCESS_KEY` | |
| `VASTDB__BUCKET` | `VASTDB_BUCKET` | |
| `VASTDB__ADBC_DRIVER_PATH` | `VASTDB_ADBC_DRIVER_PATH` | |
| `VASTDB__ADBC_ENDPOINT` | `VASTDB_ADBC_ENDPOINT` | |
| `VASTDB__SSH_JUMP_HOST` | `VASTDB_SSH_JUMP_HOST` | |
| `VASTDB__ENDPOINT_USERNAME` | `VASTDB_ENDPOINT_USERNAME` | |
| `VASTDB__ENDPOINT_PASSWORD` | `VASTDB_ENDPOINT_PASSWORD` | |

`VASTDB__ENDPOINT` was overloaded: as a full URL in application code and as a raw `host:port` in the CI tunnel script. The rename splits these into two distinct vars with unambiguous purposes.

## Verification

**Commands:**
- `grep -rn "VASTDB__" --include="*.py" --include="*.sh" --include="*.yml" --include="*.yaml" --include="*.template" .` -- expected: zero matches (confirms all double-underscore refs are gone)
- `uv run pytest tests/unit_tests/ -v` -- expected: all pass (no behavioral change)
