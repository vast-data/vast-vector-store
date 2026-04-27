---
name: orchestration
description: Stage sequencing, run log format, resume logic, and escalation rules for the bmad-yolo-dev-story workflow.
---

# Orchestration

You are the orchestrator. Your job is small and disciplined: pick the next stage, invoke the relevant BMAD skill **inline** (or run an inline git/CLI step), record the outcome in the run log, decide the next stage, repeat. **Everything happens in the current main-context turn.** You do not call the `Agent` tool. You do not spawn subagents. You invoke nested BMAD skills via the `Skill` tool — which injects their instructions into this same turn, so following them is free (no extra premium request on metered backends).

## Golden rule: the run log is the only state

Context accumulates across every stage of a run. The harness may auto-evict old tool results or compact prior messages under pressure — that is expected. To survive it, **every stage must re-read `{implementation_artifacts}/yolo-runs/<story-key>.run.md` before it starts** and treat its contents as authoritative. Do not rely on "I remember from earlier in this turn that the branch is X." Read it from the file.

Corollary: every stage must **write its outcome to the run log as its final step**, before advancing. The file must be durable; the conversation must not be trusted.

## Run log file

Path: `{implementation_artifacts}/yolo-runs/<story-key>.run.md`

Create the file at the start of stage 1 (after `bmad-create-story` returns the key). Update it after every stage transition. On compaction or resume, re-read it to recover state. The run log is a `bmad:` commit in its own right — but don't commit it on every micro-update; commit it at natural boundaries (end of each stage) so the history stays readable.

**Format** (YAML front matter + append-only stage log):

```markdown
---
story_key: 1-2-configure-gitlab-ci-cd-pipeline
story_file: _bmad-output/implementation-artifacts/1-2-configure-gitlab-ci-cd-pipeline.md
branch: story/1-2-configure-gitlab-ci-cd-pipeline
default_branch: main
remote_host: github  # or gitlab
mr_pr_url: null      # populated after stage 6
status: in-progress  # in-progress | done | blocked | failed
current_stage: 4-review-loop
max_iters: 3
review_iters_used: 0
ci_iters_used: 0
started: 2026-04-09T14:23:00Z
updated: 2026-04-09T14:47:00Z
---

## Stage log

### 1-create-story (done)
- summary: <≤200-word structured summary of what the stage did>
- files_changed: <list>
- commits: <SHAs>

### 2-branch (done)
- ...

### 3-dev-story (done)
- ...

### 4-review-loop iter 1 (done)
- ...
```

Append, never rewrite history. If a stage produces no commits, say so explicitly.

## Story discovery and entry point selection

Before entering the stage sequence, the orchestrator must discover which story to work on and determine the correct starting stage based on its current sprint status. **This runs after config loading and arg parsing, but before the run-log resume check** (SKILL.md step 3).

### Discovery logic

1. **Read `{implementation_artifacts}/sprint-status.yaml`** and parse the `development_status` section.
2. **Find the target story:**
   - If the user passed an explicit story id or path: find that story's key in sprint-status. If a literal file path was given and the file exists, extract the story key from the filename (e.g. `2-4-delete-get-by-ids.md` → `2-4-delete-get-by-ids`), then look up its status in sprint-status.
   - Otherwise: scan `development_status` top-to-bottom for the **first story key** (pattern `N-N-name`, not epic keys or retrospectives) whose status is **not `done`**.
3. **If no non-done story is found**, halt with `status: blocked, reason: "all stories are done — run sprint-planning or correct-course to add more"`.

### Entry point mapping

Based on the discovered story's sprint status:

| Sprint status | Starting stage | Notes |
|---|---|---|
| `backlog` | **Stage 1** (create-story) | Full workflow. |
| `ready-for-dev` | **Stage 2** (branch) → Stage 3 (dev-story) | Stage 1 skipped. Update sprint-status to `in-progress` before proceeding. |
| `in-progress` | **Stage 2** (branch) → Stage 3 (dev-story) | Stage 1 skipped. Branch may already exist (Stage 2 handles this). |
| `review` | **Stage 2** (branch) → Stage 4 (review-fix loop) | Stages 1 and 3 skipped. Branch should already exist. |

### Run log initialization for skipped Stage 1

When starting at Stage 2 or later (story status ≠ `backlog`), the orchestrator must still initialize the run log before proceeding:

1. Derive `story_key` from the sprint-status key (e.g. `2-4-delete-get-by-ids`).
2. Derive `story_file` from the resolved `story_location` in sprint-status.yaml + `<story_key>.md`.
3. **Verify the story file exists on disk.** If it doesn't, halt with `status: blocked, reason: "sprint-status says <status> but story file not found at <path>"`.
4. Create the run log at `{implementation_artifacts}/yolo-runs/<story-key>.run.md` with the standard YAML front matter. Set `current_stage` to the entry point determined above.
5. Append `### 1-create-story (skipped: story already at <status>)` to the stage log.
6. Commit as `bmad: <story-key>: initialize yolo run log`.

### Sprint-status update on entry

- When entering at `ready-for-dev`: update the story's status in sprint-status.yaml to `in-progress` and commit as `bmad: <story-key>: update sprint status to in-progress`.
- When entering at `in-progress` or `review`: no sprint-status change needed.

### Run-log resume takes priority

After discovery, check for an existing run log (SKILL.md step 4). If one exists with `status: in-progress`, resume from the run log's `current_stage` — ignore the status-based entry point. The run log is the more precise record of where the workflow actually stopped.

## Stage sequence

Run stages in this order. Each stage is completed before the next begins. Halt the entire workflow on any `blocked`/`failed` outcome. **Before every stage, re-read the run log** to recover state — do not trust scrollback. **Skip stages before the determined entry point** — the run log will already contain `(skipped: ...)` entries for them.

### Stage 1 — Create story (conditional — inline skill invocation)

**Skip this stage if the entry point is Stage 2 or later** (story status was not `backlog`). The run log already has `### 1-create-story (skipped: ...)`.

When this stage runs:
- Before invoking: re-read the run log if it exists.
- Read the `create-story` block in `references/stage-prompts.md` for the exact YOLO overrides and halt-point defaults for this stage.
- Invoke `bmad-create-story` via the `Skill` tool. While following its instructions inline, apply every override from the `create-story` prompt block: auto-discover next backlog story (or use the explicit story id/path the user passed), timebox web research, escalate if no backlog story is available.
- On completion: parse the story key, story file path, and commit SHAs from what the skill produced.
- Initialize the run log with this info. Commit it as `bmad: <story-key>: initialize yolo run log`.
- Append a `### 1-create-story (done)` entry to the run log with the structured summary.
- Advance to stage 2.

### Stage 2 — Branch (inline bash)

- Re-read the run log for `story_key` and `default_branch`.
- Determine the default branch: `git symbolic-ref refs/remotes/origin/HEAD` (strip `refs/remotes/origin/`). Fall back to `main` if that fails. Cache in the run log.
- Verify currently on the default branch. `git pull --ff-only` to make sure it's up to date.
- Create and check out `story/<story-key>`. If the branch already exists, this is a resume — check it out instead of erroring.
- No commit needed (branch creation doesn't produce one).
- Append `### 2-branch (done)` to the run log with the branch name and advance.

### Stage 3 — Dev story (conditional — inline skill invocation)

**Skip this stage if the entry point is Stage 4** (story sprint status was `review`). Append `### 3-dev-story (skipped: story already at review)` to the run log and advance to Stage 4.

When this stage runs:
- Re-read the run log for `story_file`, `story_key`, `branch`.
- Read the `dev-story` block in `references/stage-prompts.md` for the exact YOLO overrides. This includes: auto-select the correct story, escalate on 3 consecutive implementation failures, escalate on new-dependency-required halts, skip the end-of-workflow explanations prompt.
- Invoke `bmad-dev-story` via the `Skill` tool. Apply every override. Commit incrementally per the commit-discipline rules (one `code:` per logical change, `bmad:` for story file updates).
- **Frugal file handling (mandatory):**
  - `Grep` before `Read`. Use `offset`/`limit` when reading code files — do not read whole files unless absolutely necessary.
  - `Edit` not `Write` for existing files.
  - Keep accumulated context small — later stages run in the same turn and share the budget.
- On completion:
  - If anything blocked you → append `### 3-dev-story (blocked)` with the blocker, mark run `status: blocked`, halt.
  - Otherwise re-read the story file's `Status:` line. If it's `review`, append `### 3-dev-story (done)` and advance to stage 4. If anything else (e.g. still `in-progress`), treat as blocked and escalate.

### Stage 4 — Review-fix loop (code review ↔ test gate ↔ dev fix)

This is the most subtle stage. It has three sub-stages that run in a single convergence loop: **4a code review**, **4b test gate**, and **4c dev fix**. The loop only exits when both code review (`Status: done`) AND the test gate (`task test:all` green) converge in the same iteration. Loop inline:

1. Re-read the run log for current iteration counter, story file path, and branch.
2. **Sub-stage 4a — Code review.** Read the `code-review` block in `references/stage-prompts.md` for the exact YOLO overrides. Critical ones: defer `decision-needed` findings (never resolve them unilaterally), always choose "Batch-apply all" (option 0) for patch findings, choose "Done" (option 3) at the "next steps" prompt.
3. Invoke `bmad-code-review` via the `Skill` tool. It writes findings directly to the story file's `### Review Findings` section, applies non-controversial patches in batch, and updates the story `Status:` to `done` (clean) or `in-progress` (findings remaining). Commit per the commit-discipline rules.
4. **Do not read the findings block into context** — read back only the story file's `Status:` line (use `Grep` for `^Status:` or `Read` with a small `limit`).
5. Branch on status:
   - `done` → code review converged for this iteration. Advance to **sub-stage 4b** (test gate) below.
   - `in-progress` → unresolved `[Review][Patch]`/`[Review][Decision]` items remain. Skip 4b and go directly to **sub-stage 4c** (dev fix) at step 9.
6. **Sub-stage 4b — Test gate.** Read the `test-gate` block in `references/stage-prompts.md`. The procedure in short:
   - Verify context is `local` via `task ctx` (CLAUDE.md mandate). If not, run `task ctx:local`.
   - Verify all required services are healthy via `task status`. If anything required for the suite is down, halt with `status: blocked, reason: "test gate cannot run — services not running. Start with 'task start' and re-run."` Do NOT auto-start services; the user is responsible for the local dev environment.
   - Run `task test:all`, piping output to `/tmp/yolo-tests-<story-key>-iter<N>.log`. Do NOT inline the full output into context.
   - On pass: append `### 4-review-loop iter N (done, converged)` to the run log with a one-line note that the test gate passed. Exit loop, advance to stage 5.
   - On fail: `Grep` the temp log for failing assertions / error lines and read just those spans. Treat the failures as new follow-up work for the dev-fix sub-stage. Continue to step 7.
7. **Decide whether the test failures are in scope** (use the `test-gate` block's decision tree):
   - Failures in code or tests this story introduced/modified → in scope. Continue to step 8.
   - Failures in unrelated pre-existing flaky tests → STOP and escalate. Do NOT silently fix tests that aren't yours. Mark run log `status: blocked` with the failing test name(s) and the log path.
   - Failures in test infrastructure (missing service health, environment variable, etc.) the orchestrator already tried to satisfy → STOP and escalate.
   - Cannot diagnose from the captured log → STOP and escalate.
8. Append the failing assertion(s) as `[Review][Patch]` follow-up tasks under the story file's `### Review Follow-ups (AI)` section. Use one bullet per failing assertion with the form `- [ ] [Review][Patch] Fix failing test: <test name> — <one-line failure summary> (see /tmp/yolo-tests-<story-key>-iter<N>.log)`. Set the story `Status:` back to `in-progress`. Commit as `bmad: <story-key>: record test gate failures as review follow-ups`.
9. Increment `review_iters_used` in the run log. If it exceeds `max_iters`, append a `### 4-review-loop iter N (blocked, max_iters)` entry with a summary of the still-unresolved review findings AND the still-failing tests (grep them from the story file and the latest test log; do not dump them wholesale into context), mark run `status: blocked`, halt. Do NOT push half-reviewed or test-failing code.
10. **Sub-stage 4c — Dev fix.** Re-invoke `bmad-dev-story` via the `Skill` tool with the `dev-story` prompt block's **review-continuation** directive: "this is a review continuation — address the `[Review]` follow-up tasks in the story file before any other work." The bmad-dev-story workflow already has logic for this (it detects "Senior Developer Review (AI)" section and prioritizes review follow-ups).
11. On return, if blocked → escalate. Otherwise append the iter entry to the run log (note in the summary which sub-stage(s) ran and whether the dev fix targeted review findings, test failures, or both) and loop back to step 1.

Update the run log at every iteration. Each iteration entry should record the result of each sub-stage that ran (code review status, test gate status if it ran, dev fix outcome if it ran).

### Stage 5 — Documentation sync (always runs, inline)

**This stage ALWAYS runs** unless `--no-tech-writer` was set. There is no trigger heuristic. Stale docs are a big risk to BMad agents and humans on later stories — every story must leave the docs consistent.

**Mission:** Audit *every* project documentation file against the changes made in this story and update the ones the changes impact. Coverage spans READMEs, architecture docs, API references, custom internal docs (e.g. `docs/TESTING.md`, `docs/RUNNING-CONFIGURATIONS.md`), and runbooks.

**Procedure:**

1. **Use the change context already in this turn.** The dev-story and review stages just ran inline; the diff is in your working memory. Do not re-`git diff` the whole branch. Re-read only what you need: the story's `File List` section (small `Grep`/`Read`) and, if a specific doc edit is uncertain, the relevant span of the changed file.

2. **Enumerate the documentation surface.** Resolve `{project_knowledge}` from `_bmad/bmm/config.yaml` (e.g. `docs/`). List candidate doc files: `find <project_knowledge> -name '*.md' -not -path '*/archive/*'` plus repo-root `README*` / `CHANGELOG*`. Anything under `archive/**` is out of scope.

3. **Decide impact per doc, cheaply.** For each candidate, `Grep` for keywords from the changes (changed file basenames, new symbol names, route paths, test count strings, story key) before `Read`-ing. Common patterns to watch:
   - `README*` / `CHANGELOG*` → user-facing surface change, new feature.
   - `docs/architecture/**` → new module/service, changed boundary, schema change.
   - `docs/api*` / `docs/openapi*` → route added/changed/removed, schema change.
   - `docs/TESTING.md` (or any test inventory) → ANY test added/renamed/deleted in any suite. Update both per-suite counts and the per-story addendum.
   - `docs/RUNNING-CONFIGURATIONS.md` / runbooks → Taskfile change, env var change, new service.
   - Story/QA/retrospective docs in `docs/stories/`, `docs/qa/`, `docs/retrospectives/` are owned by other BMad stages — leave alone unless the diff clearly contradicts them.

4. **Make the edits inline.** Use `Edit` (preferred) on each impacted doc. Keep edits minimal and targeted — append the new row, bump counts, add the new route. Do not refactor unrelated sections.

5. **Loop in the tech writer where it adds value.** `bmad-agent-tech-writer` stays part of this stage — invoke it via the `Skill` tool when:
   - **`VD` (validate-doc):** after edits to higher-stakes docs (`README*`, `docs/architecture/**`, public API references), run `VD` to check the edited doc against documentation standards. Apply the validator's actionable findings inline; ignore stylistic noise.
   - **`WD` (write-document):** when the story introduces a new concept with no existing doc home and a new doc must be created from scratch. For routine in-place edits to existing docs, do them directly with `Edit` — `WD` is overkill there.
   - **`MG` (mermaid-gen):** when an architecture doc needs a new/updated diagram for the change.

   In every case, suppress the Paige persona/menu — go straight to the action.

6. **Skip rule (rare).** Only mark `skipped` if, after the audit, no doc relates to the changes. The skip reason in the run log must list which docs were checked and why each was unaffected — a bare "internal feature, no docs to update" is not acceptable.

7. **Commit as `docs:`** per commit discipline. One coherent commit per logical doc update is fine; bundling tightly-related edits is fine.

8. **Run log entry.** Append one of:
   - `### 5-docs-sync (done)` with a bulleted list of files edited and a one-line rationale per file (note any `VD` validations applied).
   - `### 5-docs-sync (skipped: <reason>)` listing the docs audited.

Advance regardless of done/skipped.

### Stage 6 — Push + open MR/PR (inline bash)

Skip entirely if `--no-push` was set.

Re-read the run log for `branch`, `default_branch`, `remote_host` (cached in pre-conditions), `story_key`, `story_file`.

Follow `references/push-pr-ci.md` for:
- Push command and rules.
- PR/MR create commands (GitHub vs GitLab).
- Idempotency (on resume, check for existing PR/MR first).

Capture the URL into `mr_pr_url` in the run log front matter. Append `### 6-push-pr (done)` with the URL.

### Stage 7 — CI wait + fix loop (inline bash + inline dev-story on failure)

Skip entirely if `--no-ci-wait` was set.

Follow `references/push-pr-ci.md` for active-CI detection, watch commands, failure log capture, and the skip-when-no-active-CI logic.

**On CI failure — inline fix loop:**

1. Capture the failing job's output. **Pipe it to a temp file** (e.g. `/tmp/yolo-ci-fail-<story-key>-iter<N>.log`) — do not inline the whole log into context. `Grep` the temp file for the failing assertion / error line, and read just that span.
2. Decide the fix path from the `ci-fix` block in `references/stage-prompts.md`:
   - Failure in story code/tests → invoke `bmad-dev-story` inline in review-continuation mode, passing the failing assertion as the "review finding" to address.
   - Failure in CI config (`.github/workflows`, `.gitlab-ci.yml`) or infra → invoke `bmad-quick-dev` inline, or just make the fix directly if obvious.
   - Failure in unrelated pre-existing flaky tests → halt and escalate (do NOT "fix" tests that aren't yours).
   - Cannot diagnose from the log → halt and escalate.
3. Commit per commit discipline. Push the fix (`git push`, no force, no `-u` — upstream already set). If push is rejected, halt and escalate (never force-push).
4. Re-watch CI on the new commit.
5. Increment `ci_iters_used`. If it would exceed `max_iters`, halt as `status: failed` with the latest failure log path. Do not loop forever.
6. Otherwise loop back to "watch CI."

Append a `### 7-ci iter N (...)` entry per iteration.

### Stage 8 — Final report (inline)

- Mark run log `status: done`.
- Update `{implementation_artifacts}/sprint-status.yaml`: set the story's status to `done` under `development_status`.
- Commit both the run log and sprint-status update together as `bmad: <story-key>: complete yolo run`.
- Push the final run log commit (so the PR/MR contains the full record).
- Output a concise summary to the user: story key, branch, PR/MR URL, CI status, review iterations used, CI fix iterations used, doc updates (if any), commit count, time elapsed.

## Escalation rules

Halt the workflow immediately on any of these:

- A stage cannot proceed autonomously (ambiguous requirement, persistent failure, missing dep, etc.).
- Pre-conditions fail (dirty tree, wrong branch, missing CLI tool).
- A loop hits its `max_iters` cap without converging.
- An inline git/CLI command fails in a way the LLM can't safely interpret (e.g. push rejected because remote moved — never force-push to fix this without user input).
- The story file's `Status:` ends up in an unexpected state after a stage (e.g. neither `review` nor `done` after dev-story or code-review).

When you halt:
1. Mark the run log `status: failed` (or `blocked`) with `failure_reason: <one-line>`.
2. Commit the run log as `bmad: <story-key>: halt yolo run — <reason>`.
3. Print a clear, structured report to the user: stage where it stopped, what the stage reported, the run log path, and a single suggested next action ("re-run with `--max-iters 5`", "fix the failing test manually then re-run", etc.).
4. **Do not** discard work, reset, or push.

## Resume logic

If a run log exists at startup with `status: in-progress` and matches the requested story:

1. Read the front matter and the stage log.
2. Verify git state matches: branch exists and is checked out (or `main` is current and the branch can be re-checked out).
3. The next stage is the one after the last entry with `(done)`. If the last entry has any other state, treat it as the resume point — re-run that stage (BMAD skills are designed to be idempotent enough to handle this; for inline bash stages, check whether the work was already done before re-doing it).
4. Continue from there.

If the run log says `status: done` or `failed`, do NOT auto-resume — print the state and ask the user whether to start fresh, retry, or just inspect.

## Compaction mid-run

If the harness's auto-compaction fires during a run (because accumulated context hit the pressure threshold), it is **not** a failure. The workflow is explicitly designed to survive it:

- The post-compaction context still has this skill's critical principles and the run log path.
- The next stage re-reads the run log to recover `story_key`, `branch`, `current_stage`, iteration counters, `remote_host`, and `mr_pr_url`.
- It re-reads `references/stage-prompts.md` for the active stage's overrides.
- It re-reads the story file for current `Status:` and File List.
- Verbose things dropped by compaction (diffs, full findings, CI log bodies) were always supposed to live on disk — re-read them from the files they were written to, using `Grep`+sliced `Read`.

The compaction directive in `SKILL.md` tells the summarization pass exactly what to preserve and what to drop. Trust it and continue.
