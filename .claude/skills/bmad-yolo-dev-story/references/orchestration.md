---
name: orchestration
description: Stage sequencing, run log format, resume logic, and escalation rules for the bmad-yolo-dev-story workflow.
---

# Orchestration

You are the orchestrator. Your job is small and disciplined: pick the next stage, dispatch a subagent (or run an inline git/CLI step), record the outcome in the run log, decide the next stage, repeat. **You do not implement code, run reviews, or write docs yourself** — that work belongs to subagents.

## Run log: the source of truth

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
- subagent summary: <paste the ≤200-word summary returned>
- commits: <SHAs>

### 2-branch (done)
- ...

### 3-dev-story (done)
- ...

### 4-review-loop iter 1 (done)
- ...
```

Append, never rewrite history. If a stage produces no commits, say so explicitly.

## Stage sequence

Run stages in this order. Each stage is completed before the next begins. Halt the entire workflow on any `blocked`/`failed` outcome.

### Stage 1 — Create story

- Spawn subagent using the `create-story` template in `references/subagent-prompts.md`.
- Pass: explicit story id/path if user provided one; otherwise instruct it to auto-discover from `sprint-status.yaml`.
- On return, parse the summary for: `story_key`, `story_file`, `commit_shas`.
- Initialize the run log with this info. Commit the run log file as `bmad: <story-key>: initialize yolo run log` (inline — this is the one place the orchestrator commits, since the subagent doesn't know the run log exists yet).
- Advance to stage 2.

### Stage 2 — Branch (inline)

- Determine the default branch: `git symbolic-ref refs/remotes/origin/HEAD` (strip `refs/remotes/origin/`). Fall back to `main` if that fails.
- Verify currently on the default branch. `git pull --ff-only` to make sure it's up to date.
- Create and check out `story/<story-key>`. If the branch already exists, this is a resume — check it out instead of erroring.
- Inline; no commit needed (branch creation doesn't produce one).
- Update the run log with `branch:` and advance.

### Stage 3 — Dev story

- Spawn subagent using the `dev-story` template.
- Pass: `story_file`, `story_key`, `branch`, `max_iters` value (informational; this stage doesn't loop), and the **commit discipline + halt-on-unsolvable + yolo-override** directives from `references/subagent-prompts.md`.
- On return:
  - If `status: blocked` → mark run failed, report, halt entire workflow.
  - Otherwise read the story file's `Status:` line. If it's `review`, advance to stage 4. If anything else (e.g. still `in-progress`), the subagent didn't finish — treat as blocked and escalate.

### Stage 4 — Review-fix loop

This is the most subtle stage. Loop:

1. Spawn `code-review` subagent (template in `references/subagent-prompts.md`). It runs `bmad-code-review`, which writes findings to the story file's `### Review Findings` section, applies non-controversial patches in batch (option 0), and updates the story `Status:` to `done` (clean) or `in-progress` (findings remaining).
2. On return, re-read the story file's `Status:`:
   - `done` → review converged. Exit the loop, advance to stage 5.
   - `in-progress` → there are unresolved `[Review][Patch]` items in `Tasks/Subtasks → Review Follow-ups (AI)` (or unresolved `[Review][Decision]` items). Continue.
3. Increment `review_iters_used`. If it exceeds `max_iters`, halt the run as `blocked` with a summary of the still-unresolved findings. Do NOT push half-reviewed code.
4. Spawn `dev-story` subagent again (same template, but include directive: "this is a review continuation — address the `[Review]` follow-up tasks in the story file before any other work"). The bmad-dev-story workflow already has logic for this (it detects "Senior Developer Review (AI)" section and prioritizes review follow-ups).
5. On return, if `status: blocked` → escalate. Otherwise loop back to step 1.

Update the run log at every iteration.

### Stage 5 — Tech writer (conditional)

Skip entirely if `--no-tech-writer` was set.

**Trigger heuristic** (orchestrator decides, not the subagent):
- Read the story file's `File List` section.
- Trigger if any of: a file matching `README*`, `CHANGELOG*`, `docs/**`, `examples/**`; a new public module/class/function in package source (e.g. `src/**/__init__.py`, anything not under `tests/`); a new CLI entry point (`pyproject.toml` `[project.scripts]` change); a new public configuration knob.
- Otherwise skip and log "no doc-worthy changes detected".

If triggered, spawn the `tech-writer` subagent template with:
- The story file path
- The File List
- The directive: "Update or create the relevant project documentation for the changes in this story. Make the actual edits — do not propose. If nothing meaningful needs updating, return `status: skipped` with a one-line reason."

The subagent commits its own `docs:` (and possibly `bmad:`) commits. On return, advance regardless of skipped/done.

### Stage 6 — Push + open MR/PR (inline)

Skip entirely if `--no-push` was set.

Detect remote host:
- `git remote get-url origin` → parse host. `github.com` → `gh`. `gitlab.com` or any host containing `gitlab` → `glab`. Otherwise: halt with a clear message ("unsupported remote host: <host>").

Push: `git push -u origin story/<story-key>`. Do not force-push.

Open the PR/MR (use story title from the story file as the PR title; body should reference the story file path and acceptance criteria summary):
- GitHub: `gh pr create --title "<title>" --body "$(cat <<'EOF' ... EOF)" --base <default-branch>`
- GitLab: `glab mr create --title "<title>" --description "$(cat <<'EOF' ... EOF)" --target-branch <default-branch> --source-branch story/<story-key>`

Capture the URL into `mr_pr_url` in the run log.

If the PR/MR already exists (re-push on resume), don't try to create a duplicate — just capture the existing URL via `gh pr view --json url` or `glab mr view`.

### Stage 7 — CI wait + fix loop

Skip entirely if `--no-ci-wait` was set.

**Detect active CI** (per the user's "wait only if there's an active CI" directive):
- GitHub: `gh run list --branch story/<story-key> --limit 1 --json status,databaseId` — if no run exists or no active workflow file is configured, skip the wait stage entirely and log it.
- GitLab: `glab ci status --branch story/<story-key>` — same logic.

If a run exists, watch it to completion:
- GitHub: `gh run watch <run-id> --exit-status`
- GitLab: `glab ci view --branch story/<story-key>` (poll until complete)

**On success:** Update run log, mark `status: done`, advance to stage 8.

**On failure:** Begin the CI fix loop.
1. Capture failure context: `gh run view <run-id> --log-failed` or equivalent `glab ci trace`. Truncate aggressively — pass only the failing test/job output to the subagent, not the entire log.
2. Spawn the `ci-fix` subagent template (in `references/subagent-prompts.md`). Pass the failure log + story file path + branch name. Direct it to use either `bmad-dev-story` (if the failure is in tests/code already covered by the story) or `bmad-quick-dev` (if it's a test-only or CI-config fix). Subagent commits + pushes.
3. After it returns, watch CI again on the new commit.
4. Increment `ci_iters_used`. If it exceeds `max_iters`, halt as `blocked` with the latest failure log. Do not loop forever.
5. Otherwise repeat from CI watch.

If CI passes, advance to stage 8.

### Stage 8 — Final report

- Mark run log `status: done`.
- Commit the final run log update as `bmad: <story-key>: complete yolo run` (inline orchestrator commit).
- Push the final run log commit (so the PR/MR contains the full record).
- Output a concise summary to the user: story key, branch, PR/MR URL, CI status, review iterations used, CI fix iterations used, doc updates (if any), commit count, time elapsed.

## Escalation rules

Halt the workflow immediately on any of these:

- A subagent returns `status: blocked`. Surface the blocker verbatim to the user.
- Pre-conditions fail (dirty tree, wrong branch, missing CLI tool).
- A loop hits its `max_iters` cap without converging.
- An inline git/CLI command fails in a way the LLM can't safely interpret (e.g. push rejected because remote moved — never force-push to fix this without user input).
- The story file's `Status:` ends up in an unexpected state after a stage (e.g. neither `review` nor `done` after dev-story or code-review).

When you halt:
1. Mark the run log `status: failed` (or `blocked`) with `failure_reason: <one-line>`.
2. Commit the run log as `bmad: <story-key>: halt yolo run — <reason>`.
3. Print a clear, structured report to the user: stage where it stopped, what the subagent (or command) reported, the run log path, and a single suggested next action ("re-run with `--max-iters 5`", "fix the failing test manually then re-run", etc.).
4. **Do not** discard work, reset, or push.

## Resume logic

If a run log exists at startup with `status: in-progress` and matches the requested story:

1. Read the front matter and the stage log.
2. Verify git state matches: branch exists and is checked out (or `main` is current and the branch can be re-checked out).
3. The next stage is the one after the last entry with `(done)`. If the last entry has any other state, treat it as the resume point — re-run that stage (subagents are designed to be idempotent enough to handle this; for inline stages, check whether the work was already done before re-doing it).
4. Continue from there.

If the run log says `status: done` or `failed`, do NOT auto-resume — print the state and ask the user whether to start fresh, retry, or just inspect.
