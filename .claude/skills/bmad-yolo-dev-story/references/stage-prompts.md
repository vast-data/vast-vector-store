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
   - (c) If the choice asks for clarification on requirements that are genuinely ambiguous and you cannot infer the answer from existing project artifacts → STOP and escalate (see rule 4).

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

## Stage 1 — Create story (`bmad-create-story`)

**Mission:** Run `bmad-create-story` to create the next story file for this project.

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
- `done` → review converged, exit loop, advance to stage 5
- `in-progress` → unresolved findings remain, loop will run dev-story again (in review-continuation mode)

Set `next_action_hint` in the run log entry:
- `review_converged` if Status: done
- `needs_dev_fix: <count> findings` if Status: in-progress

---

## Stage 5 — Tech writer (`bmad-agent-tech-writer`)

**Mission:** Update or create project documentation for the changes made in this story.

**Context to have in hand before invoking:**
- `story_file`, `story_key`
- File List from the story (grep it out of the story file; do not read the whole story)
- `{project_knowledge}` path
- Triggering signals (why the orchestrator decided docs likely need updating — record these in the run log)

**YOLO overrides for this stage:**
- Use the `WD` (write-document) capability. **Do NOT enter the Paige persona greeting / menu loop.** Go directly to making documentation edits.
- If after inspecting the changes you conclude that no documentation actually needs updating (e.g. internal refactor with no public surface change), return `status: skipped` with a one-line reason in the run log. Do NOT invent doc updates just to have done something.
- If you do update docs, MAKE THE EDITS — do not propose them, do not write a plan.

**Scope guardrails:**
- Only update docs that relate to the changes in this story. Do not refactor unrelated documentation.
- Prefer editing existing docs over creating new ones. Create a new doc only if the story introduces a fundamentally new concept that has no existing doc home.
- README / CHANGELOG / quickstart updates are in scope if user-facing surface changed.

**Commit granularity:**
- One `docs:` commit per coherent doc update (e.g. one for README, one for a new concept doc).

**Definition of done:** Either meaningful doc edits are committed, or the run log entry is `(skipped: <reason>)`.

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
