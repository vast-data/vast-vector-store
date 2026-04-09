---
name: push-pr-ci
description: Remote detection, push, MR/PR creation (gh or glab), CI wait with skip-when-no-active-CI, and the CI fix loop for bmad-yolo-dev-story.
---

# Push, PR/MR, CI

These stages run **inline** (the orchestrator executes them directly), with one exception: when CI fails, the fix is delegated to a subagent via the `ci-fix` template in `subagent-prompts.md`.

## Remote detection

**Detection runs in pre-conditions (stage 0) — not at stage 6.** The result is cached in the run log so later stages and resume don't re-detect.

If the user passed `--remote-host github` or `--remote-host gitlab`, use it verbatim and skip detection entirely.

Otherwise apply these signals **in order** and stop at the first match:

1. **Repo CI config files (highest priority — most reliable for self-hosted).**
   - `.gitlab-ci.yml` exists at the repo root → `gitlab`
   - `.github/workflows/` directory exists with at least one `*.yml`/`*.yaml` file → `github`
   - If both exist → ambiguous; halt and ask the user to pass `--remote-host`.

2. **Remote URL host string.** Run `git remote get-url origin` and parse the host:
   - Host == `github.com` (with or without `www.`) → `github`
   - Host contains the substring `gitlab` (e.g. `gitlab.com`, `gitlab.example.org`) → `gitlab`

3. **Last-resort tool probe.** Run both in parallel:
   - `glab repo view 2>/dev/null` (succeeds if the remote is a glab-known host)
   - `gh repo view 2>/dev/null` (succeeds if the remote is github)
   - Exactly one succeeds → that's the host. Both fail → unknown host. Both succeed → ambiguous (rare).

4. **Unknown.** Halt with a clear message: `Could not auto-detect remote host for <url>. Re-run with --remote-host github|gitlab to specify explicitly.` Do NOT default to either tool — guessing wrong wastes a stage and corrupts the run log.

**Verify only the matching CLI tool**, then cache:

| Detected | Verification command | Cache as |
| -------- | -------------------- | -------- |
| `github` | `gh auth status`     | `remote_host: github` |
| `gitlab` | `glab auth status`   | `remote_host: gitlab` |

If the matching tool is missing or unauthenticated, halt with a clear message — do not try to install or authenticate from inside the workflow, and do not fall back to the other tool. **Never run `gh auth status` if detection said gitlab, or vice versa.**

### Self-hosted GitLab

This is the common case that breaks naive host-string matching (e.g. `git.vastdata.com`, `gitlab.internal.example`, etc.). Rule 1 (`.gitlab-ci.yml` presence) handles it. If a project has neither a `.gitlab-ci.yml` nor a `.github/workflows/` directory and the remote host string doesn't match either pattern, the user must pass `--remote-host` — there's no reliable signal left.

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
