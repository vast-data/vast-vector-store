---
name: bmad-yolo-dev-story
description: "Autonomously develops next BMAD story end-to-end. Use when the user says 'yolo dev story', 'auto-develop next story', 'run yolo workflow', or '/bmad-yolo-dev-story'."
---

# bmad-yolo-dev-story

## Overview

Develops a BMAD story end-to-end without human intervention. Chains `bmad-create-story` → git branch → `bmad-dev-story` → `bmad-code-review` (loop) → optional `bmad-agent-tech-writer` → push → MR/PR → CI wait + fix loop, all in a **single main-context turn**.

**Every stage runs inline in the main context.** No `Agent` / subagent spawns. The orchestrator invokes each BMAD skill directly via the `Skill` tool (or by following its `SKILL.md` inline) and performs git/gh/glab operations via `Bash`. The entire workflow is one user turn → one premium request on metered backends (e.g., Copilot-proxied Claude Code).

**Args:** `[story-id-or-path]` (optional — auto-discovers next backlog story if omitted), `--max-iters N` (default `3`; applies to both review-fix loop and CI-fix loop independently), `--no-tech-writer`, `--no-push`, `--no-ci-wait`, `--remote-host github|gitlab` (escape hatch when auto-detection is ambiguous).

## On Activation

1. **Load config.** Read `{project-root}/_bmad/bmm/config.yaml` and `{project-root}/_bmad/bmb/config.yaml` (with `config.user.yaml` overlays if present). Resolve at minimum: `implementation_artifacts`, `planning_artifacts`, `user_name`, `communication_language`, `project_knowledge`. Fall back to sensible defaults if any key is missing.

2. **Parse args.** Extract optional story id/path and the flags above. Defaults: `max_iters=3`, all stages enabled.

3. **Discover story and determine entry point.** See `references/orchestration.md` § "Story discovery and entry point selection" for full logic. In short: find the first non-`done` story in sprint-status.yaml (or the one matching the explicit arg), check its status, and pick the starting stage:
   - `backlog` → Stage 1 (create-story, full workflow)
   - `ready-for-dev` / `in-progress` → Stage 2 (branch) → Stage 3 (dev-story)
   - `review` → Stage 2 (branch) → Stage 4 (review-fix loop)

4. **Detect fresh run vs resume.** Check `{implementation_artifacts}/yolo-runs/` for an in-progress run log matching the discovered story. If one exists with status not in `{done, failed}`, this is a resume — recover state from that file before continuing. **Run-log resume takes priority over status-based entry** — if a run log exists, resume from the run log's current stage regardless of sprint-status.

5. **Verify pre-conditions** (fail fast, do NOT just barrel through):
   - Working tree clean (`git status --porcelain` empty). If dirty, halt with a clear message. Do not stash or discard.
   - On the project's default branch (usually `main`) OR current branch is a `story/*` branch matching a resume scenario. Otherwise halt.
   - **Detect remote host FIRST**, then verify only the matching CLI tool. Detection rules in `references/push-pr-ci.md` under "Remote detection" — apply them in order. Cache the result in the run log so later stages don't re-detect. If `--remote-host` was passed, skip detection and use that value verbatim. Then verify the matching tool (`gh auth status` for github, `glab auth status` for gitlab) succeeds. **Do not run `gh auth status` unless detection said github.** Skip this entire check if `--no-push` is set.

6. **Load `references/orchestration.md`** for the stage sequence, run log format, resume logic, and escalation rules. Route to per-stage references (`references/stage-prompts.md`, `references/push-pr-ci.md`) on demand.

## Stages (high level — full details in `references/orchestration.md`)

| # | Stage | Runs as | Returns |
|---|-------|---------|---------|
| 1 | Create story (`bmad-create-story`) — **skipped if story status ≠ `backlog`** | inline skill invocation | story key + file path written to run log |
| 2 | Branch (`story/<key>` from default) | inline bash | branch name written to run log |
| 3 | Dev story (`bmad-dev-story`) | inline skill invocation | files modified, status written to run log |
| 4 | Review-fix loop (`bmad-code-review` ↔ `bmad-dev-story`, max `max_iters`) | inline per iteration | iterations, final status written to run log |
| 5 | Tech writer (`bmad-agent-tech-writer`) — conditional on user-facing changes | inline skill invocation | docs updated or skipped |
| 6 | Push + open MR/PR (auto-detect `gh`/`glab`) | inline bash | remote ref + PR url |
| 7 | CI wait + fix loop (skip if no active CI; max `max_iters` fix passes) | inline bash + inline dev-story invocation on failure | CI status |
| 8 | Final report | inline | full run summary |

## Critical principles

- **Single-turn inline execution.** The entire workflow runs in one main-context turn. Never call the `Agent` tool. Invoke nested BMAD skills inline via the `Skill` tool — their instructions inject into *this* turn, they do not spawn a sub-turn. This is what keeps the workflow to 1 premium request on metered backends.

- **The run log on disk is the only trusted state.** Context accumulates across the whole run. The harness may auto-evict old tool results or auto-compact prior messages under pressure — that is expected and acceptable. Every stage, before it starts, must **re-read** `{implementation_artifacts}/yolo-runs/<story-key>.run.md` to recover the current stage, branch, story key, iteration counters, and remote host. Do not rely on scrollback or in-conversation memory of prior stages. If you need a stage's verbose details (a diff, a review finding, a CI log), re-read the file it was written to. The run log and the files it points to are authoritative; the conversation is not.

- **File-handling discipline keeps context small.** Because every stage shares one context, each stage must be frugal with tokens:
  - `Grep` before `Read`. Never `Read` a whole file "for reference" — find the span you need, then `Read` with `offset`/`limit`.
  - `Edit` not `Write`. Diffs are cheap, full-file rewrites are not.
  - Review findings go straight to the story file (the BMAD `bmad-code-review` skill already does this). The orchestrator reads back only the `Status:` line and the unchecked follow-up tasks — never the full findings block.
  - CI failure logs pipe to a temp file, then `Grep` for the failing assertion. Never inline a whole log into context.
  - Large intermediate artifacts (diffs, logs, findings) always land on disk first and are `Grep`/`Read`-sliced back in only as needed.

- **Compaction directive — preserve anchors, drop everything else.** If the harness's auto-compaction fires mid-run (because context pressure hit the threshold), the summarization pass should retain ONLY these anchors and drop everything else, because everything else can be re-derived from disk:

  **Preserve:**
  - The active story key, branch name, default branch, remote host.
  - The path to `{implementation_artifacts}/yolo-runs/<story-key>.run.md` (the run log).
  - The current stage name and iteration counters (`review_iters_used`, `ci_iters_used`).
  - The path to the story file.
  - The PR/MR URL if stage 6 completed.
  - This skill's critical principles (so the resumed flow still follows them).

  **Drop:**
  - All tool outputs from prior stages (file contents, diffs, grep results, CI logs).
  - All narration/reasoning from prior stages.
  - The full text of earlier stage-prompt blocks — they can be re-read from `references/stage-prompts.md` if the next stage needs them.
  - Anything that can be re-obtained by re-reading a file on disk.

  After compaction, the next stage re-reads the run log to recover state and proceeds. This is not a failure mode — it is the designed behavior.

- **Commit discipline — incremental, granular, family-separated.** Three families, never mixed in one commit:
  - `code: <story-key>: <imperative summary>` — anything under repo source/tests/configs/build files
  - `bmad: <story-key>: <imperative summary>` — anything under `_bmad-output/**` (story file, sprint-status.yaml, deferred-work.md, run logs)
  - `docs: <story-key>: <imperative summary>` — anything under `{project_knowledge}/**` or root README/CHANGELOG
  - One commit per logical change, not one commit per stage. Use HEREDOC commit messages. Never `--amend`. Never `--no-verify`. Never `git add -A`/`git add .`.

- **Halt on unsolvable problems — do not guess, do not loop.** If a stage cannot proceed autonomously (ambiguous requirement, persistent test failure, missing dependency, rejected push), stop immediately, mark the run log `status: blocked` with a clear `failure_reason`, report to the user, and exit the workflow. Do NOT retry blindly or paper over the issue. Specific halt/escalation rules are in `references/stage-prompts.md` per stage.

- **YOLO overrides at BMAD skill halt points.** BMAD skills are designed for an interactive human and contain explicit `HALT` / `<ask>` instructions at decision points. When invoking a BMAD skill inline, the orchestrator must know the autonomous default for every known halt and pick it without pause. The exact overrides for each stage are in `references/stage-prompts.md` — read the relevant section before invoking the skill for that stage.

h- **Asking the user is allowed — but only via `AskUserQuestion`, and only at stage boundaries.** The default is still autonomous: pick the most autonomous option at every halt and keep moving. However, when a genuinely useful clarifying question would meaningfully change the work (ambiguous requirement, unclear scope decision, choice of approach with material trade-offs), you MAY ask the user — under these constraints:
  - **Tool restriction.** Questions are only permitted through the `AskUserQuestion` tool when running on Claude Code. On harnesses without a structured-question tool (e.g. opencode, Cursor), do NOT ask — keep the autonomous-default behavior. Never ask via plain assistant text mid-run; that breaks the single-turn contract.
  - **Batch at natural boundaries — preferred.** Collect questions and ask them together at the gates between major phases — ideally just before stage 1 (create-story) and just before stage 3 (dev-story implementation). One batched `AskUserQuestion` call with multiple questions beats several scattered ones. Asking outside these gates is allowed but should be rare and well-justified.
  - **High bar.** Ask only when the answer would change what gets built or how. Do NOT ask to confirm decisions you can make autonomously, to validate progress, or out of caution. If in doubt, don't ask — proceed with the autonomous default and capture the assumption in the run log.
  - **Hard blockers still escalate, not ask.** The "halt and mark `status: blocked`" path is unchanged for genuine blockers (rejected push, persistent test failure, missing dependency). `AskUserQuestion` is for *forward-looking* clarifications, not for handing the user a broken run.

- **Never push broken work.** If any stage produces `status: blocked` or `status: failed`, stop. Do not advance to push, PR, or CI stages.
