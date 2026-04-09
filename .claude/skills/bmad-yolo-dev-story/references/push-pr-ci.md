---
name: push-pr-ci
description: Remote detection, push, MR/PR creation (gh or glab), CI wait with skip-when-no-active-CI, and the CI fix loop for bmad-yolo-dev-story.
---

# Push, PR/MR, CI

These stages run **inline** (the orchestrator executes them directly), with one exception: when CI fails, the fix is delegated to a subagent via the `ci-fix` template in `subagent-prompts.md`.

## Remote detection

```bash
git remote get-url origin
```

Parse the host:

| Host pattern                 | Tool   | Notes                                              |
| ---------------------------- | ------ | -------------------------------------------------- |
| `github.com`                 | `gh`   | Both HTTPS and SSH URLs                            |
| Contains `gitlab` (any host) | `glab` | Self-hosted GitLab too — match the substring       |
| Anything else                | —      | Halt with `unsupported remote host: <host>`        |

Verify the chosen tool is installed and authenticated:
- `gh auth status` (must succeed)
- `glab auth status` (must succeed)

If the tool is missing or unauthenticated, halt with a clear message — do not try to install or authenticate from inside the workflow.

Cache the detected `remote_host` in the run log front matter so resume works without re-detecting.

## Push (stage 6, part 1)

```bash
git push -u origin story/<story-key>
```

Rules:
- Never `--force` or `--force-with-lease`. Never `--no-verify`.
- If the push is rejected because the remote moved, halt and escalate. This happens on resume scenarios where someone else (or a previous yolo run) already pushed — the human should decide whether to rebase, merge, or abandon.
- If the push succeeds with no errors, advance to the PR/MR step.

## Open PR/MR (stage 6, part 2)

**Title:** Use the story title from the story file's `## Story` section, prefixed with the story key. Format: `<story-key>: <title>`. Keep under 70 chars; truncate the title portion if needed.

**Body:** Markdown, including:
- A one-line summary
- Link to the story file (relative path)
- The acceptance criteria summary (bullet list — copied from the story)
- A "Yolo run" footer with the run log path and commit count
- Footer attribution: `🤖 Generated with bmad-yolo-dev-story`

**Idempotency:** On resume, a PR/MR may already exist for this branch. Always check first:
- GitHub: `gh pr view --json url,number 2>/dev/null` (run from inside the branch checkout — `gh` infers the branch)
- GitLab: `glab mr view --output json 2>/dev/null`

If one exists, capture the URL and skip creation. If not, create it.

### GitHub create command

```bash
gh pr create \
  --title "<title>" \
  --base "<default-branch>" \
  --body "$(cat <<'EOF'
## Summary
<one-liner>

## Story
- File: <relative path>
- Key: <story-key>

## Acceptance Criteria
- <bullets from story>

## Yolo run
- Run log: <relative path>
- Commits: <count>

🤖 Generated with bmad-yolo-dev-story
EOF
)"
```

### GitLab create command

```bash
glab mr create \
  --title "<title>" \
  --target-branch "<default-branch>" \
  --source-branch "story/<story-key>" \
  --description "$(cat <<'EOF'
## Summary
<one-liner>

## Story
- File: <relative path>
- Key: <story-key>

## Acceptance Criteria
- <bullets from story>

## Yolo run
- Run log: <relative path>
- Commits: <count>

🤖 Generated with bmad-yolo-dev-story
EOF
)"
```

Capture the URL into `mr_pr_url` in the run log front matter.

## Stage 7 — CI wait + fix loop

### Detect active CI (skip-when-none)

The user's directive: **wait only if there's an active CI; otherwise skip the wait stage entirely.**

GitHub:
```bash
gh run list \
  --branch "story/<story-key>" \
  --limit 1 \
  --json status,databaseId,workflowName,event \
  --jq '.[0]'
```

GitLab:
```bash
glab ci status --branch "story/<story-key>"
```

Decision tree:
- If output is empty / no run found → no CI is configured for this branch (or CI hasn't kicked off yet — give it ~10 seconds and retry once before concluding "no active CI"). Skip the entire CI wait stage. Log "no active CI detected; skipped wait" in the run log. Advance to stage 8.
- If a run is found and is `queued`, `in_progress`, or `pending` → watch it.
- If a run is found and is already `completed` with conclusion `success` → CI passed, advance to stage 8.
- If a run is found and is already `completed` with conclusion `failure`/`cancelled`/`timed_out` → enter the fix loop.

### Watch the run

GitHub:
```bash
gh run watch <run-id> --exit-status
```
- `--exit-status` makes it exit non-zero on failure, which the orchestrator can detect.

GitLab:
```bash
glab ci view --branch "story/<story-key>"
```
- `glab ci view` shows status; for blocking, poll `glab ci status` every ~30 seconds until the pipeline reaches a terminal state.

### On success

Advance to stage 8.

### On failure — CI fix loop

1. **Capture the failure log** (truncated, only the failing job's output — pass at most ~3000 lines to the subagent; aggressively trim ANSI escapes and noise):

   GitHub:
   ```bash
   gh run view <run-id> --log-failed
   ```

   GitLab: `glab ci trace <job-id>` for each failed job.

2. **Spawn the `ci-fix` subagent** using the template in `references/subagent-prompts.md`. Pass:
   - `story_file`, `story_key`, `branch`
   - `iter` (current ci_iters_used + 1)
   - `max_iters`
   - `failure_log` (the truncated text)

3. **The subagent commits and pushes** its fix. (This is the only stage where a subagent pushes — because the loop polls CI on the new commit.)

4. **On subagent return:**
   - `status: blocked` → halt the workflow, surface the blocker. Do not loop further.
   - `status: done` → re-enter the CI watch (a new CI run will have started from the push).

5. **Increment `ci_iters_used`.** If it would exceed `max_iters` (default 3), halt with `status: failed`, including the latest failure log in the report. Do not loop forever.

6. Loop back to "Watch the run" with the new run id.

### After the fix loop

- If CI ultimately passes within `max_iters` → advance to stage 8.
- If `max_iters` is exhausted → halt as failed.

## Idempotency notes for resume

If the workflow is resumed mid-stage 6 or 7:
- Stage 6 push: re-running `git push` is safe (no-op if branch is up to date). Re-running PR/MR creation will fail noisily; check for an existing PR/MR first.
- Stage 7 CI watch: re-fetch the latest run on the branch and resume watching from there. Don't re-trigger CI just to "be sure" — let the existing run finish.
