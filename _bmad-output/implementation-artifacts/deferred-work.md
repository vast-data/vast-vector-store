# Deferred Work

## Deferred from: code review of story 1-1-initialize-package-scaffold-with-uv-and-hatchling (2026-04-09)

- ~~`langchain-tests` dev dependency is unpinned — risk of breaking changes from upstream. Consider pinning to a range like `langchain-tests>=1.1,<2` before running integration tests (Story 3.1).~~ **RESOLVED** — pinned to `>=1.1,<2` in pyproject.toml.
- ~~sdist build has no exclude configuration — `_bmad/`, `_bmad-output/`, `docs/`, `.gitlab-ci.yml`, `.cursor/`, `.opencode/` would be included in a source distribution. Add `[tool.hatch.build.targets.sdist]` exclude before PyPI publication (Story 4.3).~~ **RESOLVED** — `[tool.hatch.build]` exclude list added in pyproject.toml.
- `langchain-core>=0.3` allows a wide version range spanning 0.x to 1.x. The lockfile resolves 1.2.28. Consider tightening to `>=1.0,<2` when Epic 2 implements real VectorStore methods. **→ Story 4-2a**
- ~~`readme = "README.md"` currently points at GitLab boilerplate containing the internal corporate URL `https://git.vastdata.com/genai/vast-vector-store.git`. Story 4.1 will rewrite the README — ensure internal URLs are removed before publication.~~ **RESOLVED** — README rewritten in Story 4-1; internal URLs removed.
- ~~No `py.typed` marker file (PEP 561) — type checkers will ignore inline annotations. Add `src/langchain_vastdb/py.typed` when Epic 2 introduces typed method signatures.~~ **RESOLVED** — `py.typed` marker exists.

## Deferred from: code review of story 1-2-configure-gitlab-ci-cd-pipeline (2026-04-09)

- No `workflow:rules` directive to prevent duplicate pipelines -- without top-level workflow rules, pushing to an MR branch may trigger two pipelines (one for push, one for MR). Consider adding workflow:rules when pipeline complexity increases. **→ Story 4-2a**
- Test stages (lint, unit-test, integration-test) also run on tag pushes alongside publish -- this wastes CI minutes but is not incorrect. Consider adding rules to skip test stages on tag pushes if CI costs become a concern. (Deferred: requires human judgment on team preference.) **→ Story 4-2a**

## Deferred from: code review of story 2-1-constructor-session-management-and-table-access (2026-04-09)

- Thread-safety: `_metadata_loaded` flag in `VastDBVectorStore._get_table()` has no synchronization. Two threads calling `_get_table` simultaneously when `_metadata_loaded=False` could both call `load(tx)`. Benign in practice since VastDB SDK is sync-only and `load()` is idempotent, but should be considered if future async support introduces concurrency. **→ Decisions artifact (architectural)**

## Deferred from: code review of story 2-2-add-texts-and-document-insertion (2026-04-09)

- ~~Float64 inference in RecordBatch: `pa.RecordBatch.from_pydict()` infers float64 for Python float lists in the vector column; VastDB table schema likely uses float32. VastDB SDK handles type coercion on insert. Will be validated in integration tests (Story 3.1).~~ **RESOLVED** — explicit `pa.list_(pa.float32())` type used in `_insert_vectors`.

## Deferred from: code review of story 2-3-similarity-search-operations (2026-04-09)

- Metadata None safety in `_row_to_document`: if a row has `None` for the metadata column (e.g., inserted by subclass or external tool), `json.loads(None)` raises TypeError. Base class `_insert_vectors` always writes `json.dumps({})`, so this only affects externally-inserted data. Will be validated in integration tests (Story 3.1). **→ Story 4-2a (AI-2 fix)**

## Deferred from: code review of story 3-1-langchain-standard-integration-test-suite (2026-04-12)

- ~~`from vastdb._internal import VectorIndexSpec` uses a private module. `VectorIndexSpec` is not exported from the `vastdb` public API, so `_internal` is the only import path. Should be revisited if a future `vastdb` release exposes this via a public API.~~ **RESOLVED** — `VectorIndexSpec` no longer imported anywhere in the codebase.
- ~~`test_add_documents_with_ids_is_idempotent` and `test_add_documents_by_id_with_mutation` in the standard suite require upsert/overwrite semantics. Whether VastDB's `table.insert()` handles duplicate `id` values idempotently (or raises an error, or creates duplicates) is unknown without live-cluster testing. If these tests fail in CI, `_insert_vectors` may need a delete-then-insert upsert pattern and the fix should target a follow-up Epic 3 corrective story.~~ **RESOLVED** — upsert implemented via delete-then-insert in Story 3-1a.

- **AI-2 (NULL metadata in _row_to_document):** `json.loads(None)` raises `TypeError` when a row's metadata column is NULL (inserted externally bypassing VastDBVectorStore). Test `test_row_with_null_metadata_roundtrips` in `tests/integration_tests/test_vectorstore.py` is marked `@pytest.mark.xfail` for this bug. Proposed fix in `_row_to_document`: replace `json.loads(row.get(self._metadata_column, "{}"))` with `json.loads(metadata_raw) if (metadata_raw := row.get(self._metadata_column)) is not None else {}`. Deferred to a follow-up Epic 3 corrective story. **→ Story 4-2a**

## Deferred from: code review of story 3-1 live-cluster fix branch (2026-04-13)

- `_metadata_loaded` flag remains without synchronization — re-raised after fix commits added the VectorIndex fallback write inside the same block. Still benign because VastDB SDK is sync-only, but now the cached state includes a potentially patched `_vector_index`, making any future async support more fragile. **→ Decisions artifact (same as 2-1 thread-safety item)**
- `_delete_by_ids` / `_insert_vectors` hook contract: the base class now calls them with `tx=tx` to preserve upsert atomicity, but subclasses that override these methods without honoring the `tx` kwarg silently break atomicity. Document in the hook API contract and defer enforcement to a future refactor (e.g., make `tx` a positional required arg or validate at call site). **→ Decisions artifact (API design)**
- Elysium (sorted) tables use `decimal128(38,0)` for `$row_id` instead of `uint64`. The new `_delete_by_ids` path (`table.select(..., internal_row_id=True).read_all()` → `table.delete(rows)`) may type-mismatch for sorted tables. Vector tables are typically unsorted, so this is a corner case. Revisit when Elysium compatibility is in scope. **→ Decisions artifact (edge case)**

## Deferred from: code review of story 3-1a-live-cluster-correctness-fixes (2026-04-15)

- **DF1.** `_do_vector_search_fallback` reads the full table via `read_all().to_pylist()`. OOM risk on large tables. Needs a streaming top-k heap or a server-side `LIMIT` with a sampled scan. **→ Decisions artifact (architectural)**
- **DF2.** `_do_vector_search_adbc` opens a fresh ADBC connection per call. Acceptable for test volume; not for production throughput. Pool or cache per-store. **→ Decisions artifact (architectural)**
- **DF3.** Upsert atomicity depends on the SDK's transaction isolation level. If it is not serializable, concurrent writers can interleave between the delete and insert legs. Document the guarantee or pick a locking strategy. **→ Decisions artifact (needs SDK info)**
- **DF4.** CI stores `VASTDB__ENDPOINT_PASSWORD` as a plain GitLab variable. Rotate to masked/protected or move to a vault. **→ Decisions artifact (ops/security)**
- **DF5.** `sshpass` is apt-installed in CI without version pinning; supply-chain drift risk. Pin or vendor. **→ Story 4-2a**
- **DF6.** `ci-tunnel.sh` backgrounds `ssh -f -N` and returns immediately; tests can race the tunnel coming up. Add a `nc -z localhost 18151` readiness loop. **→ Story 4-2a**
- **DF7.** `_do_vector_search_fallback` silently skips dim-mismatched rows. A corrupted table would return "0 results" with no operator signal. Emit a counter + warning. **→ Story 4-2a**
- **DF8.** `VectorIndex` fallback hardcodes `l2sq`. If the real index on the table is cosine/dot-product, results are wrong and only a warning log fires. Consider a config override on the store. **→ Decisions artifact (API design)**
- **DF9.** SQL injection in `_do_vector_search_adbc` filter interpolation — listed here as a reminder that even after the P1 patch, the ADBC SQL path is still string-concatenation-based. A proper parameterized query API via the ADBC driver would be safer long-term. **→ Story 4-2a (type whitelist)**

## Deferred from: code review of story 3-1a-live-cluster-correctness-fixes (2026-04-15, second pass)

- **DF-a.** ADBC step-2 SDK `_get_by_ids` failure is outside the ADBC try-block. If step 1 succeeds but step 2 fails, the exception propagates past the fallback. Rare but asymmetric with step-1 handling. (`vectorstores.py:789-795`) **→ Story 4-2a**
- **DF-b.** `_table_metadata._vector_index = VectorIndex(...)` writes a single-underscore private attribute of `vastdb.table_metadata`. Any library refactor breaks it. No public setter available. (`vectorstores.py:247-259`) **→ Decisions artifact (SDK dependency)**
- **DF-c.** `OSError` in the ADBC catch tuple is broader than ADBC-specific errors. Can mask disk/permission/network errors into a silent fallback. Narrow once the driver exposes specific connect errors. (`vectorstores.py:673-677`) **→ Decisions artifact (needs driver info)**
- **DF-d.** Duplicate IDs in ADBC step-1 result collapse silently via `dict(zip)`. If the one-row-per-id invariant is ever violated, `len(results) < k` with no signal. Add a counter + warning. (`vectorstores.py:788-795`) **→ Story 4-2a**
- **DF-e.** `_adbc_available()` does not reject whitespace-only credential strings. A misconfigured env var (`VASTDB__ADBC_ENDPOINT=" "`) takes the ADBC path, fails, then falls back once per query. (`vectorstores.py:602-608`) **→ Story 4-2a**
- **DF-f.** `from adbc_driver_manager import dbapi` imports inside `_do_vector_search_adbc` (per-call). Micro-perf; move to module top or lazy-cache. (`vectorstores.py:718`) **→ Story 4-2a**
- **DF-g.** Non-int `k` (float 4.0, bool) bypasses the `k <= 0` guard. Add `isinstance(k, int) and not isinstance(k, bool)` at the entry points. (`vectorstores.py:400, 451`) **→ Story 4-2a**
- **DF-h.** Very large `k` (e.g. `10**9`) is interpolated directly into `LIMIT` with no server-side cap. Consider a sane ceiling or explicit caller responsibility doc. (`vectorstores.py:768`) **→ Decisions artifact (product decision)**
- **DF-i.** `_id_column` / `_text_column` / `_metadata_column` constructor args are not quoted in the ADBC SELECT. A constructor-time column name containing `"` or SQL keywords breaks the query. Quote with the same `"..."` escape used elsewhere. (`vectorstores.py:761-764`) **→ Story 4-2a**
- **DF-j.** Fallback scoring loop assumes `isinstance(vec, list)`. If the Arrow reader returns a numpy array or tuple for a fixed_size_list column on some vastdb version, every row is silently skipped. Coerce via `list(vec)` before the length check. (`vectorstores.py:819-823`) **→ Story 4-2a**
- **DF-k.** `row[text_column]` returning None yields `Document(page_content=None)` — pydantic rejects. Symmetric with the AI-2 NULL metadata xfail; fold into that fix. (`vectorstores.py:862-865`) **→ Story 4-2a**
- **DF-l.** Empty-string id `""` is accepted by the None-replace path. Row is inserted with an empty id, then can't be safely round-tripped. Reject empty strings in the caller-supplied ids loop. (`vectorstores.py:314-317`) **→ Story 4-2a**

## Deferred from: code review of story 4-1-readme-with-quickstart-configuration-and-subclassing-guide (2026-04-17)

- ~~AC#4 requires a link to the migration guide in the README. The migration guide does not exist yet (Story 4.3). Add link when Story 4.3 is complete.~~ **Belongs in Story 4-3** — migration guide creation is the scope of that story.

## Deferred from: code review of example scripts fix (2026-04-17)

- ADBC `_allowed_cols` in `_do_vector_search_adbc` hardcodes `{id, text}` — subclass typed columns (e.g., category, level) are rejected when ADBC is enabled. Should derive allowed columns from `_select_columns()` or make it overridable. Not triggered today (examples don't configure ADBC; macOS has no ADBC driver). **→ Story 4-2a**
- `from_connection_params` return type annotation is `-> VastDBVectorStore` but uses `cls(...)`, so subclass callers get the wrong static type. Should be `-> Self` (typing_extensions). **→ Story 4-2a**
- `test_credentials_not_stored_as_instance_attributes` test name is misleading — credentials ARE stored as `_access_key`/`_secret_key` (documented behavior). Test only checks there's no *public* attribute. **→ Story 4-2a**
- ADBC SQL path inconsistently quotes column names — `_id_column` is unquoted in SELECT while `_vector_column` is quoted. Edge-case breakage if column name is a SQL keyword. **→ Story 4-2a (folded into DF-i)**
- ADBC SQL filter value interpolation uses bare `str(val)` for non-string/non-bool types. A type whitelist (str, int, float, bool) would close the injection edge case. **→ Story 4-2a (folded into DF-9)**

## Deferred from: code review of 4-2a-pre-publication-hardening (2026-04-19)

- `similarity_search_by_vector` raises `ValueError` on `numpy.ndarray` embedding due to `if not embedding` truth-value check at `vectorstores.py:516`. Pre-existing.
- Non-string IDs (e.g. ints `123`, `0`) bypass the empty-ID check at `vectorstores.py:363` because `isinstance(id_, str)` short-circuits. AC2 was narrowly scoped to empty strings.
- ADBC step-1 result-shape assumption: `result.get(self._id_column, [])` at `vectorstores.py:870` returns `[]` (and the caller returns no results with no warning) if a driver lower/upper-cases the projected column key.
- `dict(zip(ids, distances))` at `vectorstores.py:883` truncates silently if step-1 arrays have mismatched lengths.
- Metadata JSON shape not validated as `dict` at `vectorstores.py:972`. `json.loads("[1,2,3]")` would yield a list metadata, violating LangChain's `metadata: dict` contract.
- CI tunnel readiness probe (`scripts/ci-tunnel.sh:23-31`) uses `/dev/tcp` which succeeds even if `ssh -f -N` died after binding the local port. AC6 satisfied as written; deeper liveness check (PID capture / `pgrep`) deferred.

## Deferred from: project-wide holistic review (2026-04-19)

Whole-project sweep covering code, architecture, UX, tests, and docs. Items already captured in `deferred-decisions.md` (DD-8 hardcoded l2sq, DD-9 private `_vector_index` write) are referenced, not duplicated.

### Docs / packaging inconsistencies

- **PWR-1.** `README.md:80-81` states: *"Credentials are passed directly to `vastdb.connect()` and are **not** stored on the instance."* This contradicts `from_connection_params` at `vectorstores.py:189-199`, which forwards `access_key`/`secret_key` into `__init__` where they are stored as `self._access_key`/`self._secret_key` (documented at `vectorstores.py:116-123`). Either fix the README to match reality, or make `from_connection_params` only retain credentials when `adbc_driver_path` is set (the only consumer). The misleading-test-name item at deferred-work line 76 is adjacent but the README-level contradiction is the user-visible half.
- **PWR-2.** `README.md:10,21` says `langchain-core >= 0.3`, but `pyproject.toml:27` now pins `langchain-core>=1.0,<2` (resolved during Story 4-2a per deferred-work line 7). README compatibility line is stale — pip will resolve 1.x regardless, so the README misinforms pre-install readers. Single-line fix.

### Correctness consistency

- **PWR-3.** Filter-column validation is asymmetric between search paths. The ADBC path validates filter keys against `_select_columns()` (`vectorstores.py:817-825`), but the in-memory fallback builds an ibis predicate via `_build_predicate` (`vectorstores.py:647-668`) with **no** column-name validation. Same `filter_dict` is accepted on one path and rejected on the other depending on whether ADBC is available. Either validate up-front in `similarity_search*` before branching, or add the same allowlist check in the fallback path. Folds naturally with DF-i-style quoting audits.

### Code quality / DRY

- **PWR-4.** Tx-open/reuse boilerplate is copy-pasted in four hooks: `_insert_vectors` (`vectorstores.py:423-431`), `_delete_by_ids` (`vectorstores.py:577-591`), `_get_by_ids` (`vectorstores.py:637-645`), `_vector_search` (`vectorstores.py:709-713`). Each has an identical `if tx is not None: ... else: with self._session.transaction() as new_tx: ...` pattern. A small internal `@contextmanager _with_tx(tx)` would halve those methods and reduce drift risk if the tx lifecycle ever changes. Defer to next refactor pass — low risk but touches every hook.
- **PWR-5.** k/NaN/inf validation is triplicated across `similarity_search`, `similarity_search_with_score`, `similarity_search_by_vector` (`vectorstores.py:454-461, 483-490, 515-522`). Extract `_validate_k(k)` and `_validate_query_vector(vec)` helpers. Pure mechanical cleanup.
- **PWR-6.** Dead defensive guard at `vectorstores.py:411-412`: `_insert_vectors` starts with `if not embeddings: return ids`, but `add_texts` already early-returns on empty `texts_list` at line 345. Embeddings cannot be empty on this call path. Either delete the inner guard or make it the sole guard (remove the one in `add_texts`). Either direction, not both.

### DX / API ergonomics

- **PWR-7.** `filter` is a `**kwargs` key on `similarity_search`, `similarity_search_with_score`, `similarity_search_by_vector`. Discoverable only via prose docs — does not show up in IDE autocomplete or type hints. Promote to an explicit keyword: `filter: dict | None = None`. Zero behavior change; improves discovery.
- **PWR-8.** `ssl_verify=True` default on `from_connection_params` is the right default, but every bundled example (`examples/basic_usage.py:73`, etc.) and integration fixture (`tests/integration_tests/test_vectorstore.py:89`) overrides to `False`. Signals that real clusters often use self-signed certs. README quickstart uses bare `http://` which dodges the issue. Add a one-liner callout in the quickstart or config reference so users hit this in docs, not at runtime.
- **PWR-9.** Constructor surface is asymmetric: `from_connection_params` accepts `ssl_verify` but plain `__init__` does not (users build their own session, so they pass it there). Correct but surprising. One README sentence would prevent the DX trip.

### Tests

- **PWR-10.** `tests/unit_tests/test_vectorstore.py` is 932 lines in one module. Works today but split-by-concern (construction, add_texts, search, adbc, hooks, row-to-doc) would improve navigation and parallelize future additions. Not urgent.

