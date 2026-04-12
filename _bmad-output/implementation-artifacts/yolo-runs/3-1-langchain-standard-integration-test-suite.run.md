---
story_key: 3-1-langchain-standard-integration-test-suite
story_file: _bmad-output/implementation-artifacts/3-1-langchain-standard-integration-test-suite.md
branch: story/3-1-langchain-standard-integration-test-suite
default_branch: main
remote_host: gitlab
mr_pr_url: null
status: in-progress
current_stage: 4-review-loop
max_iters: 3
review_iters_used: 0
ci_iters_used: 0
started: 2026-04-12T00:00:00Z
updated: 2026-04-12T00:00:00Z
---

## Stage log

### 1-create-story (skipped: story already at ready-for-dev)

### 2-branch (done)
- summary: Created and checked out branch story/3-1-langchain-standard-integration-test-suite from main (up to date).
- branch: story/3-1-langchain-standard-integration-test-suite
- commits: none (branch creation produces no commit)

### 3-dev-story (done)
- summary: Created tests/integration_tests/test_vectorstore.py with TestVastDBVectorStoreSync inheriting VectorStoreIntegrationTests. VECTOR_DIM=6 matches langchain-tests EMBEDDING_SIZE. Per-test isolated tables via vastdb.connect + create_table with VectorIndexSpec("vector","cosine"). has_async=False disables 13 async tests (sync-only SDK). Added AI-1, AI-2 (xfail), AI-3 deferred-finding tests. Fixed _row_to_document to set Document.id (correctness bug required for standard suite equality assertions). Removed allow_failure from .gitlab-ci.yml. Added AI-2 deferred-work entry. ruff clean; 29 unit tests green; 28 integration tests skip cleanly without env vars.
- files_changed: tests/integration_tests/test_vectorstore.py (NEW), src/langchain_vastdb/vectorstores.py (MODIFIED), .gitlab-ci.yml (MODIFIED), _bmad-output/implementation-artifacts/deferred-work.md (MODIFIED)
- commits: 78e0f8a, ab0805d, 4b6b290
- next_action_hint: story status=review, advance to 4-review-loop
