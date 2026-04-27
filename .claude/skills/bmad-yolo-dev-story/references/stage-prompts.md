---
name: stage-prompts
description: Per-stage YOLO override directives, halt-point defaults, commit granularity rules, and escalation triggers for each stage of bmad-yolo-dev-story. Read the relevant section before invoking that stage's BMAD skill inline.
---

# Stage Prompts

Every stage of `bmad-yolo-dev-story` runs **inline in the main-context turn**. When the orchestrator reaches a stage, it reads the relevant section of this file, then invokes the stage's BMAD skill via the `Skill` tool — which injects that skill's instructions into the current turn. The orchestrator follows those instructions directly, while applying the overrides below at every halt point.

**Why these overrides exist.** BMAD skills are designed for an interactive human at the keyboard. They contain explicit `HALT` / `<ask>` decision points. Without the overrides below, the inline invocation will stall on instructions to "ask the user" when there is no separate user to ask. The overrides pre-commit to the most autonomous choice at every known halt and specify when it is actually correct to stop and escalate.

---

## Inline operating contract (shared — applies to every stage)

When following a BMAD skill's instructions inline within a yolo run, these rules apply on top of whatever the skill says:

1. **Autonomous defaults at every halt.** The BMAD skill will instruct you to HALT and ask the user to choose options. You choose the most autonomous option in every case. Stage-specific overrides below are authoritative — follow them exactly. For any halt not covered there, use this hierarchy:
   - (a) If the choice is "apply automatically vs leave as action items vs walk through" → ALWAYS pick "apply automatically" / "batch-apply all".
   - (b) If the choice is "what would you like to do next" at the end of a workflow → treat the workflow as complete and move on.
   - (c) If the choice asks for clarification on requirements that are genuinely ambiguous and you cannot infer the answer from existing project artifacts → either ask via `AskUserQuestion` if the answer would change the work and you are at/near a stage boundary (see rule 1a below), otherwise STOP and escalate (see rule 4).

   1a. **Asking via `AskUserQuestion` (Claude Code only).** When a clarifying question would meaningfully change the output — and only then — you may use the `AskUserQuestion` tool. Constraints:
      - **Claude Code only.** On opencode, Cursor, or any harness without a structured-question tool, skip this entirely and fall back to autonomous defaults or rule 4 escalation. Do NOT ask via plain assistant text.
      - **Batch at gates.** Strongly prefer collecting questions and asking them in a single `AskUserQuestion` call at natural boundaries — before stage 1 (create-story) and before stage 3 (dev-story implementation) are the canonical gates. Asking mid-stage is allowed but should be rare.
      - **High bar.** Ask only if the answer changes what gets built or how. Do not ask to confirm autonomous decisions, validate progress, or hedge. When unsure, do not ask — proceed and record the assumption in the run log.
      - **Not a substitute for escalation.** Genuine blockers (rejected push, repeated test failures, missing deps) still go through rule 4 — `AskUserQuestion` is for forward-looking clarification, not for handing over a broken run.

2. **Commit discipline — incremental, granular, family-separated.** Commit as you go, not at the end. After each logically coherent change (one task complete, one bug fixed, one section of docs written), make a commit. Three commit families, NEVER mixed in the same commit:
   - `code: <story-key>: <imperative summary>` — for source/tests/configs/build files
   - `bmad: <story-key>: <imperative summary>` — for anything under `_bmad-output/**` (story file, sprint-status.yaml, run logs, etc.)
   - `docs: <story-key>: <imperative summary>` — for anything under `{project_knowledge}/**` or root README/CHANGELOG
   Use `git commit` with HEREDOC messages. Stage files explicitly by path (NEVER `git add -A` or `git add .`). Never `--amend`. Never `--no-verify`. Never force-push. Do NOT push from inside a stage — pushing happens in stage 6 (and stage 7 CI fix iterations).

3. **Work only on the current branch.** You are on branch `<branch from run log>`. Verify with `git rev-parse --abbrev-ref HEAD` before committing. If you are not on the expected branch, stop and escalate.

4. **Escalate when blocked — do not guess, do not loop.** Stop immediately and mark the run log `status: blocked` with a clear `failure_reason` if any of the following happen:
   - A test failure that you've tried to fix three times without success
   - The BMAD skill asks for clarification on a requirement you cannot infer
   - You'd need to install a new dependency not listed in the story or project config
   - You'd need to modify files outside the scope of this story
   - A git operation fails in a way that needs human judgment (push rejected, merge conflict)
   - Anything else that would make a competent human stop and ask

   Do NOT silently work around blockers. Do NOT mark tasks complete that aren't. The orchestrator surfaces your blocker to the human verbatim.

5. **Frugal file handling — mandatory.** Every stage shares one context with all the others in this turn. Keep your footprint small:
   - `Grep` before `Read`. Never `Read` a whole file "for reference" — find the span you need first, then `Read` with `offset`/`limit`.
   - `Edit` not `Write` for existing files.
   - When the BMAD skill writes long outputs (findings, reports, logs), let them land on disk and re-read only the parts you need.
   - Pipe large command outputs (CI logs, test output) to temp files and `Grep`-slice them.

6. **Write a structured summary to the run log when the stage ends.** After the stage's work is done, append to `{implementation_artifacts}/yolo-runs/<story-key>.run.md`:

   ```markdown
   ### <stage-number>-<stage-name> (<status>)
   - summary: <2-4 sentences describing what you actually accomplished>
   - files_changed: <list of paths, or "none">
   - commits: <list of SHAs, or "none">
   - blocker: <only if status=blocked — description + what would unblock>
   - next_action_hint: <optional one-liner for the next stage>
   ```

   Keep the summary ≤200 words. This is what the run log preserves when the conversation gets compacted.

---

## Stage 1 — Create story (`bmad-create-story`) — conditional

**This stage only runs when the discovered story's sprint status is `backlog`.** If the story is already at `ready-for-dev`, `in-progress`, or `review`, the orchestrator skips this stage entirely — see `references/orchestration.md` § "Story discovery and entry point selection" for details. The run log will contain `### 1-create-story (skipped: story already at <status>)`.

**Mission (when running):** Run `bmad-create-story` to create the next story file for this project.

**Context to have in hand before invoking:**
- Project root, `{implementation_artifacts}`, `{planning_artifacts}`, `{project_knowledge}` from config.
- Sprint status path: `{implementation_artifacts}/sprint-status.yaml`
- If the user passed an explicit story id/path, use that. Otherwise auto-discover the next backlog story from sprint-status.yaml.

**YOLO overrides for this stage:**
- **Step 1 (target story)**: if the skill asks "Choose option [1], provide epic-story number, ..." because no sprint status exists or no backlog story is found, STOP and escalate (status: blocked, reason: "no backlog story available"). Do NOT make one up.
- **Step 4 (web research)**: perform reasonable research with WebFetch/WebSearch but timebox aggressively — do not spend more than 2–3 lookups. The story context is more important than exhaustive research.
- **Commits produced by this stage**: the skill writes the story file and updates sprint-status.yaml. Commit as:
  - `bmad: <story-key>: create story file` (+ sprint-status update, acceptable to combine into one `bmad:` commit since they're one logical change)

**Definition of done:** A story file exists, sprint-status.yaml reflects the new status, and both are committed. The orchestrator needs `story_key` and `story_file` to initialize the run log.

---

## Stage 3 — Dev story (`bmad-dev-story`)

**Mission:** Run `bmad-dev-story` to implement the story end-to-end on the current branch.

**Context to have in hand before invoking:**
- `story_file`, `story_key`, `branch` (all from the run log)
- Whether this is a fresh invocation or a **review continuation** (set when called from within the stage 4 loop)

**YOLO overrides for this stage:**
- **Step 1 (story selection)**: if no story file is found, STOP and escalate. Do not pick an arbitrary story.
- **Step 5 (implementation loop)**:
  - If the "3 consecutive implementation failures" HALT triggers, STOP and escalate with the failures captured in the run log.
  - If the "new dependencies required beyond story specifications" HALT triggers, STOP and escalate. Do not silently add deps.
- **Step 10 (end-of-workflow prompt)**: when the workflow finishes and asks "ask if user needs any explanations" — skip, treat the workflow as complete.
- **Review continuation mode** (when invoked from stage 4 loop): the story file already has a "Senior Developer Review (AI)" section with action items. Prioritize the unchecked Review Follow-ups (AI) tasks before any other work. The `bmad-dev-story` workflow has built-in logic for this in step 3 — let it detect and handle the continuation.

**Commit granularity:**
- One `code:` commit per task in Tasks/Subtasks once that task's tests pass. Not one giant commit at the end.
- One `bmad:` commit when you update the story file's File List, Dev Agent Record, or status transitions. These can be batched if they happen in the same step.
- The story file gets updated multiple times during a dev-story run. Commit it at natural punctuation: after marking a task complete, after the final status change.

**Frugal file handling (extra emphasis for this stage — it's the biggest context hog):**
- `Grep` for the specific function/class/import you need to modify before `Read`ing a file. Use `offset`/`limit` on `Read`.
- `Edit` for every modification. Never `Write` an existing file.
- Don't load the entire test suite into context to "understand" it — grep for the test that covers the behavior you're changing.
- If you need to check patterns across the codebase, `Grep` with `output_mode: "files_with_matches"` first, then read only the top 1–2 relevant files.

**Definition of done:** The story file's `Status:` line reads `review` (or `done` if this is a fix iteration that landed everything cleanly). All relevant tasks/subtasks checked. File List populated. Tests pass. Escalate otherwise.

---

## Stage 4a — Code review (`bmad-code-review`)

**Mission:** Run `bmad-code-review` against the current branch's changes for this story.

**Context to have in hand before invoking:**
- `story_file`, `story_key`, `branch`, current iteration number, `max_iters`

**YOLO overrides for this stage — CRITICAL:**
- **step-04-present.md section 4 ("Resolve decision-needed findings")**: the skill will HALT and ask "Reply with only the number". For each `decision-needed` finding, **DEFER** it (mark as deferred with reason "autonomous yolo run — requires human judgment, deferred for review"). Do NOT attempt to resolve decision-needed items yourself; they exist precisely because the answer is ambiguous.
- **step-04-present.md section 5 ("Handle patch findings")**: the skill will HALT with options 0/1/2/3. ALWAYS choose option **0 (Batch-apply all)** — apply every non-controversial patch automatically. Skip any individual patch that genuinely requires judgment, but apply the rest.
- **step-04-present.md section 7 ("Next steps")**: when the skill asks what to do next (1/2/3), choose option **3 (Done)** — your job is finished.

**Commit granularity:**
- One `code:` commit per coherent group of patches applied (you can group patches that touch the same file or solve the same class of issue).
- One `bmad:` commit when the story file gets the `### Review Findings` section appended and Status updated.
- One `bmad:` commit when deferred-work.md gets new entries.

**Frugal file handling:**
- After the skill completes, do NOT read the full findings block into context. Use `Grep` for `^Status:` in the story file (with small `Read`) to get the post-review status. Use `Grep` for `- \[ \] \[Review\]` to count unresolved review follow-ups if you need to report a count. Never `Read` the entire story file just to see the findings.
- The run log summary should describe *how many* findings were resolved/deferred, not quote them.

**Critical post-stage check:** After the skill completes, read back the story file's `Status:` line and write it to the run log. The orchestrator uses it to decide the loop:
- `done` → code review converged for this iteration. Advance to **Stage 4b (test gate)** below — do NOT exit the loop yet.
- `in-progress` → unresolved findings remain. Skip 4b and go to **Stage 4c (dev fix)** which re-invokes `bmad-dev-story` in review-continuation mode.

Set `next_action_hint` in the run log entry:
- `review_converged_run_test_gate` if Status: done
- `needs_dev_fix: <count> findings` if Status: in-progress

---

## Stage 4b — Test gate (`task test:all`)

**Mission:** After code review converges (Status: done), prove the changes haven't broken anything by running the full local test suite. The test gate is part of the dev↔code-review convergence loop — failures here drive another dev-fix iteration just like unresolved review findings would, until both code review AND tests are green in the same iteration (or `max_iters` is exhausted).

**Why it lives in Stage 4 and not Stage 5/6/7:** Catching broken tests *before* push and *before* CI saves a full CI cycle (and a wasted PR notification) per failure. CI is still the source of truth in Stage 7, but the local test gate gives us a fast convergence loop without round-tripping through GitHub/GitLab.

**Context to have in hand before invoking:**
- `story_key`, `story_file`, `branch`, current iteration number, `max_iters`, `review_iters_used`
- The story file's current `Status:` (must be `done` from the just-completed Stage 4a; otherwise this stage doesn't run)

**Procedure:**

1. **Verify context is `local`** — CLAUDE.md mandates this before any `task test:*`, `task start*`, or `task start-backend`:
   - Run `task ctx`. If it isn't `local`, run `task ctx:local`. If switching fails, halt and escalate (`status: blocked, reason: "could not switch to local context"`).
2. **Restart all services** via `task restart` — this stops and starts all services (backend, mobile, tablet), ensuring the latest code changes are loaded. Running processes don't pick up code changes until restarted, so always do this before running the suite even if services appear healthy. If `task restart` fails, halt and escalate with `status: blocked, reason: "task restart failed — <error>. Fix the service startup issue and re-run."`.
3. **Run the full suite**: `task test:all > /tmp/yolo-tests-<story-key>-iter<N>.log 2>&1`. Capture the exit code. **Do NOT inline the full output into context** — pipe it to disk and `Grep`-slice it.
4. **On success (exit code 0):**
   - `Grep` the log for the final summary line(s) for each suite (e.g. `Tests:`, `passed`, `failed`) for a one-line confirmation. Do not read the whole log.
   - Append `### 4-review-loop iter N (done, converged)` to the run log with:
     - summary: "Code review converged (Status: done) and test gate passed (`task test:all` clean)."
     - test_summary: a one-line aggregated count from grepped output (e.g. "API=235 Worker=48 Mobile=405 Tablet=218 E2E=N").
     - log_path: `/tmp/yolo-tests-<story-key>-iter<N>.log`
   - Exit Stage 4. Advance to Stage 5.
5. **On failure (non-zero exit code):**
   - `Grep` the temp log for failing assertions / error lines (`FAIL`, `failed`, `AssertionError`, `Error:`, etc.) and read just those spans. Do NOT inline the whole log.
   - Apply the **decision tree** below to classify the failures.

**Decision tree (matches Stage 7 ci-fix decision tree, but at the local-test layer):**

- Failures in code or tests this story introduced/modified → **in scope for the dev↔CR cycle.** Append the failing assertions to the story file's `### Review Follow-ups (AI)` section as `[Review][Patch]` items, set Status back to `in-progress`, and let the orchestrator's Stage 4 loop send it to Stage 4c (`bmad-dev-story` in review-continuation mode). For genuinely missing tests on new functionality, the dev-story agent will write them as part of the fix; the QA agent (`bmad-agent-qa` / `bmad-qa-generate-e2e-tests`) is reserved for cases where bulk new test generation is needed and dev-story cannot infer scope — in practice, prefer dev-story unless the failure is "feature has no tests at all and dev-story already declined to add them."
- Failures in CI configuration or infra files (`.github/workflows`, `.gitlab-ci.yml`, `Taskfile.yml`, etc.) — these usually only show up in Stage 7 (CI), but if the local suite fails because of a misconfigured Taskfile or env var, halt and escalate. Do NOT silently rewrite infra here; that's a different review loop.
- Failures in unrelated pre-existing flaky tests → STOP and escalate. Do NOT "fix" tests that aren't part of this story's scope. Mark run log `status: blocked` with the failing test names and the log path.
- Cannot diagnose the failure from the captured log → STOP and escalate.

**Writing test failures into the story file (in-scope path):**

When recording failures as review follow-ups (decision-tree branch 1), use this exact bullet format under `### Review Follow-ups (AI)`:

```
- [ ] [Review][Patch] Fix failing test: <suite>/<test name> — <one-line failure summary> (see /tmp/yolo-tests-<story-key>-iter<N>.log)
```

One bullet per failing assertion. Keep the summary terse — the dev-fix sub-stage will re-`Grep` the log for the specific assertion. Do NOT paste full stack traces into the story file.

**Commit granularity:**
- One `bmad: <story-key>: record test gate failures as review follow-ups` commit when Status is flipped back to `in-progress` and follow-ups are appended.
- The dev-fix sub-stage (4c) will produce its own `code:` commits for the actual fixes.
- On the success path, no commit is needed for the test gate itself — the convergence is recorded only in the run log entry written at iteration end.

**Frugal file handling (extra emphasis — full test logs can be massive):**
- ALWAYS pipe `task test:all` output to `/tmp/yolo-tests-<story-key>-iter<N>.log`. Never let test stdout flow into the conversation directly.
- `Grep` the log file with `output_mode: "content"` and a tight pattern (`FAIL|AssertionError|Error:`) before any targeted `Read`.
- For pytest-style failures, the relevant span is usually the `=== FAILURES ===` block and the per-test traceback summary. `Grep` for `FAILED` to get test names, then read 20-30 line windows around each.
- For Jest, `Grep` for `●` and `✕` markers.
- For Playwright, `Grep` for `Error:` and `expect(...)`.

**Run log entry — set `next_action_hint`:**
- `tests_passed_advance_to_stage_5` if exit code 0 (and this iteration is also the converged one)
- `tests_failed_loop_to_dev_fix: <count> failures` if exit code non-zero and in-scope
- `blocked_<reason>` if escalating

**Definition of done (for this sub-stage):**
- Exit code 0 + grepped summary written to run log → Stage 4 converged, advance to Stage 5.
- Exit code non-zero + in-scope failures written into story file as review follow-ups + Status flipped to `in-progress` → loop continues into Stage 4c (dev fix) with `review_iters_used` incremented.
- Out-of-scope failure or undiagnosable → halt, escalate, do not push.

---

## Stage 5 — Documentation sync

**Mission:** Audit every project documentation file against the changes made in this story and update the ones the changes impact. Always runs unless `--no-tech-writer` was set. Full procedure in `references/orchestration.md` § "Stage 5"; this block is the per-stage operating contract.

**Context to have in hand:**
- `story_file`, `story_key`
- File List from the story (grep it out — do not read the whole story)
- `{project_knowledge}` path (resolved from `_bmad/bmm/config.yaml`)
- The changes themselves: rely on this turn's context from dev-story / review stages. Re-`Read` a specific changed file only as targeted reinforcement; do not re-`git diff` the whole branch.

**YOLO overrides:**
- For inline `Edit` work: just do it. Do not propose, do not write a plan.
- For `bmad-agent-tech-writer` invocations (`VD`, `WD`, `MG`): **suppress the Paige persona greeting and menu**. Go directly to the requested action.
- For `VD` (validate-doc): apply actionable findings inline; ignore stylistic noise.

**When to use the tech writer vs direct `Edit`:**
- `Edit` directly for routine in-place updates (counts, table rows, new route entries, runbook lines).
- `bmad-agent-tech-writer` `VD` after edits to higher-stakes docs (`README*`, `docs/architecture/**`, public API references).
- `bmad-agent-tech-writer` `WD` only when creating a brand-new doc because the story introduced a concept with no existing doc home.
- `bmad-agent-tech-writer` `MG` when an architecture doc needs a new/updated Mermaid diagram.

**Scope guardrails:**
- Only edit docs the story's changes actually impact. Do not refactor unrelated docs.
- Story/QA/retrospective docs in `docs/stories/`, `docs/qa/`, `docs/retrospectives/` are owned by other BMad stages — leave alone unless the diff clearly contradicts them.
- Anything under `archive/**` is out of scope.

**Commit granularity:**
- `docs:` commits per the commit discipline. One coherent commit per logical doc update; bundling tightly-related edits is fine.

**Skip rule (rare):** Only skip if no doc in the project relates to the changes. The skip reason must list the docs audited and why each was unaffected — a bare "internal feature, no docs to update" is NOT acceptable.

**Definition of done:** Either meaningful doc edits are committed, or the run log entry is `(skipped: <reason with audit list>)`.

---

## Stage 7 — CI fix (inline, on CI failure)

**Mission:** The CI for the current branch failed. Diagnose the failure from the captured log and fix it inline. After the fix, push the branch so the fix loop can poll CI on the new commit.

**Context to have in hand before invoking the fix:**
- `story_file`, `story_key`, `branch`, current CI iteration number, `max_iters`
- Path to the temp file containing the failing job's log (e.g. `/tmp/yolo-ci-fail-<story-key>-iter<N>.log`)
- The specific failing assertion / error (already `Grep`-sliced from the temp file — do NOT inline the whole log)

**Decision tree:**
- Failure in code or tests this story introduced/modified → invoke `bmad-dev-story` inline in **review-continuation mode**, passing the failing assertion as the "review finding" to address. (Or just fix it directly if it's a one-line obvious fix — don't invoke the full BMAD skill for trivial cases.)
- Failure in CI configuration (`.github/workflows`, `.gitlab-ci.yml`, etc.) or infra flakes not related to story code → invoke `bmad-quick-dev` inline, or make the fix directly.
- Failure in test code unrelated to this story (pre-existing flakes) → STOP and escalate. Do NOT "fix" tests that aren't yours.
- Cannot diagnose the failure from the captured log → STOP and escalate.

**Commit granularity:**
- `code:` for source/test fixes
- `bmad:` for story file updates (e.g. updated File List with new test files)

**Push (this stage is the one exception where the orchestrator pushes mid-workflow):**
- After committing, run `git push` (no force, no `-u` since upstream is already set).
- If push is rejected (remote moved), STOP and escalate — never force-push.

**Run log entry — set `next_action_hint`:**
- `ci_fix_pushed` → orchestrator re-watches CI on the new commit
- `needs_human` → orchestrator halts and escalates
