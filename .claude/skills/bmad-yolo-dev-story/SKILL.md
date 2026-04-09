---
name: bmad-yolo-dev-story
description: "Autonomously develops next BMAD story end-to-end. Use when the user says 'yolo dev story', 'auto-develop next story', 'run yolo workflow', or '/bmad-yolo-dev-story'."
---

# bmad-yolo-dev-story

## Overview

Develops a BMAD story end-to-end without human intervention. Chains `bmad-create-story` → git branch → `bmad-dev-story` → `bmad-code-review` (loop) → optional `bmad-agent-tech-writer` → push → MR/PR → CI wait + fix loop, in a single command.

**Each stage runs in a fresh `general-purpose` subagent.** Verbose execution stays out of main context — only a ≤200-word structured summary returns per stage. Subagents commit their own work in granular `code:` / `bmad:` / `docs:` commits as they go (not at stage boundaries). Subagents halt and escalate when they hit a problem they can't solve autonomously.

**Args:** `[story-id-or-path]` (optional — auto-discovers next backlog story if omitted), `--max-iters N` (default `3`; applies to both review-fix loop and CI-fix loop independently), `--no-tech-writer`, `--no-push`, `--no-ci-wait`.

## On Activation

1. **Load config.** Read `{project-root}/_bmad/bmm/config.yaml` and `{project-root}/_bmad/bmb/config.yaml` (with `config.user.yaml` overlays if present). Resolve at minimum: `implementation_artifacts`, `planning_artifacts`, `user_name`, `communication_language`, `project_knowledge`. Fall back to sensible defaults if any key is missing.

2. **Parse args.** Extract optional story id/path and the flags above. Defaults: `max_iters=3`, all stages enabled.

3. **Detect fresh run vs resume.** Check `{implementation_artifacts}/yolo-runs/` for an in-progress run log matching the requested story. If one exists with status not in `{done, failed}`, this is a resume — recover state from that file before continuing.

4. **Verify pre-conditions** (fail fast, do NOT just barrel through):
   - Working tree clean (`git status --porcelain` empty). If dirty, halt with a clear message. Do not stash or discard.
   - On the project's default branch (usually `main`) OR current branch is a `story/*` branch matching a resume scenario. Otherwise halt.
   - `gh` or `glab` available and authenticated for the detected remote (only required if `--no-push` is not set).

5. **Load `references/orchestration.md`** for the stage sequence, run log format, resume logic, and escalation rules. Route to per-stage references (`references/subagent-prompts.md`, `references/push-pr-ci.md`) on demand.

## Stages (high level — full details in `references/orchestration.md`)

| # | Stage | Runs in | Returns |
|---|-------|---------|---------|
| 1 | Create story (`bmad-create-story`) | subagent | story key + file path |
| 2 | Branch (`story/<key>` from default) | inline | branch name |
| 3 | Dev story (`bmad-dev-story`) | subagent | files modified, status |
| 4 | Review-fix loop (`bmad-code-review` ↔ `bmad-dev-story`, max `max_iters`) | subagent per call | iterations, final status |
| 5 | Tech writer (`bmad-agent-tech-writer`) — conditional on user-facing changes | subagent | docs updated or skipped |
| 6 | Push + open MR/PR (auto-detect `gh`/`glab`) | inline | remote ref + PR url |
| 7 | CI wait + fix loop (skip if no active CI; max `max_iters` fix passes) | inline + subagent on failure | CI status |
| 8 | Final report | inline | full run summary |

## Critical principles

- **Subagents own their work.** Each subagent invoked by this skill receives explicit instructions to (a) run the named BMAD skill, (b) commit incrementally as it completes logical chunks, (c) halt and escalate if it can't proceed autonomously, (d) return a ≤200-word structured summary. The exact prompt templates are in `references/subagent-prompts.md` — use them verbatim with placeholder substitution.

- **Commit discipline (enforced inside every subagent).** Three families, never mixed in one commit:
  - `code: <story-key>: <imperative summary>` — anything under repo source/tests/configs/build files
  - `bmad: <story-key>: <imperative summary>` — anything under `_bmad-output/**` (story file, sprint-status.yaml, deferred-work.md, run logs)
  - `docs: <story-key>: <imperative summary>` — anything under `{project_knowledge}/**` or root README/CHANGELOG
  - One commit per logical change, not one commit per stage. Use HEREDOC commit messages. Never `--amend`. Never `--no-verify`. Never `git add -A`/`git add .`.

- **Subagents halt on unsolvable problems.** Their summary must include `status: blocked` and a clear description of the problem. The orchestrator marks the run failed, writes the reason to the run log, reports to the user, and stops — it does NOT retry blindly or paper over the issue.

- **YOLO overrides are explicit, not implicit.** Each stage's subagent prompt (in `references/subagent-prompts.md`) names every BMAD-skill halt point and dictates the autonomous default. Without these overrides, BMAD skills will hang waiting for input that will never come.

- **Run log is the recovery oracle.** Every stage transition writes to `{implementation_artifacts}/yolo-runs/<story-key>.run.md`. If main context compacts mid-run, the next turn re-reads this file to determine the next stage. Treat the log as authoritative state.

- **Never push broken work.** If any stage returns `status: blocked` or `status: failed`, stop. Do not advance to push, PR, or CI stages.
