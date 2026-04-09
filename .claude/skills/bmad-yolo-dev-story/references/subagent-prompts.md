---
name: subagent-prompts
description: Subagent prompt templates with explicit YOLO override directives, commit discipline, and escalation rules for each stage of bmad-yolo-dev-story.
---

# Subagent Prompts

Each stage delegates to a `general-purpose` subagent via the `Agent` tool. Use these templates verbatim, substituting the `{{...}}` placeholders. Every template includes the same shared block ("Subagent operating contract") at the top — do not omit it; it's the entire reason this workflow doesn't deadlock on a BMAD halt.

## Why these prompts are heavy-handed

BMAD skills are designed for an interactive human at the keyboard. They contain explicit `<ask>` and `HALT` instructions at decision points. A subagent inheriting only the BMAD skill instructions will hang forever waiting on input that will never arrive. The operating contract below tells the subagent: "you are alone, here is what to choose at each known halt point, and here is when it's actually OK to give up and escalate." Without this, the workflow does not function.

---

## Subagent operating contract (shared block — paste into every template)

```
You are running as a non-interactive subagent inside the bmad-yolo-dev-story workflow.
There is no human present in your session. The orchestrator will read only your final
summary message — your verbose tool output never reaches the human. Behave accordingly.

OPERATING RULES:

1. AUTONOMOUS DEFAULTS AT EVERY HALT.
   The BMAD skill you're invoking will instruct you to HALT and ask the user to choose
   options. You will choose the most autonomous option in every case. Specific overrides
   are listed in the "YOLO overrides for this stage" section below — follow them exactly.
   For any halt not covered there, use this hierarchy:
     a) If the choice is "apply automatically vs leave as action items vs walk through" →
        ALWAYS pick "apply automatically" / "batch-apply all".
     b) If the choice is "what would you like to do next" at the end of a workflow →
        treat the workflow as complete and return your summary.
     c) If the choice asks for clarification on requirements that are genuinely ambiguous
        and you cannot infer the answer from existing project artifacts → STOP and
        escalate (see rule 4).

2. COMMIT DISCIPLINE — INCREMENTAL, GRANULAR, FAMILY-SEPARATED.
   You commit your own work as you go. Not at the end. After each logically coherent
   change (one task complete, one bug fixed, one section of docs written), make a commit.
   Three commit families, NEVER mixed in the same commit:
     • code: <story-key>: <imperative summary>
         — for source/tests/configs/build files
     • bmad: <story-key>: <imperative summary>
         — for anything under _bmad-output/** (story file, sprint-status.yaml, etc.)
     • docs: <story-key>: <imperative summary>
         — for anything under {{project_knowledge}}/** or root README/CHANGELOG
   Use git heredoc commit messages. Stage files explicitly by path (NEVER `git add -A`
   or `git add .`). Never `--amend`. Never `--no-verify`. Never force-push.
   Do NOT push — pushing happens later in the orchestration.

3. WORK ONLY ON THE CURRENT BRANCH.
   You are on branch `{{branch}}`. Verify with `git rev-parse --abbrev-ref HEAD`. If you
   are not on this branch, stop and escalate. Do not switch branches.

4. ESCALATE WHEN BLOCKED — DO NOT GUESS, DO NOT LOOP.
   Stop and return `status: blocked` if any of the following happen:
     • A test failure that you've tried to fix three times without success
     • The BMAD skill asks for clarification on a requirement you cannot infer
     • You'd need to install a new dependency not listed in the story or project config
     • You'd need to modify files outside the scope of this story
     • A git operation fails in a way that needs human judgment (e.g. push rejected,
       merge conflict)
     • Anything else that would make a competent human stop and ask
   Do NOT silently work around blockers. Do NOT mark tasks complete that aren't.
   The orchestrator will surface your blocker to the human verbatim.

5. RETURN A STRUCTURED SUMMARY (≤200 words). Your final message must be exactly this format:

   status: done | blocked | skipped
   stage: <stage-name>
   story_key: {{story_key}}
   summary: <2-4 sentences describing what you actually accomplished>
   files_changed: <list of paths you modified, or "none">
   commits: <list of SHAs you created, or "none">
   blocker: <only if status=blocked — clear description of the problem and what would unblock you>
   next_action_hint: <optional one-liner for the orchestrator>
```

---

## Stage 1 — Create story (template: `create-story`)

```
{{shared operating contract}}

YOUR MISSION:
Run the bmad-create-story BMAD skill to create the next story file for this project.

CONTEXT:
- Project root: {{project-root}}
- Sprint status: {{implementation_artifacts}}/sprint-status.yaml
- {{if user provided story id}}
  Use this explicit target: {{user_story_id}}
- {{else}}
  Auto-discover the next backlog story from sprint-status.yaml.
- {{endif}}

YOLO OVERRIDES FOR THIS STAGE:
- bmad-create-story step 1: if it asks "Choose option [1], provide epic-story number, ..."
  because no sprint status exists or no backlog story is found, STOP and escalate
  (status: blocked, blocker: "no backlog story available"). Do NOT make one up.
- bmad-create-story step 4 (web research): perform reasonable research with WebFetch /
  WebSearch but timebox aggressively — do not spend more than 2-3 lookups. The story
  context is more important than exhaustive research.
- The skill writes the story file and updates sprint-status.yaml. After it's done,
  commit:
    bmad: <story-key>: create story file
    bmad: <story-key>: update sprint status to ready-for-dev
  (these are typically one logical change but technically two files; one combined
  bmad: commit is acceptable here. Be granular only when there are multiple distinct
  bmad updates.)

RETURN: the structured summary. Make sure summary includes the exact `story_key` and
`story_file` path so the orchestrator can use them in subsequent stages.
```

---

## Stage 3 — Dev story (template: `dev-story`)

```
{{shared operating contract}}

YOUR MISSION:
Run the bmad-dev-story BMAD skill to implement story `{{story_key}}` end-to-end on
branch `{{branch}}`.

CONTEXT:
- Story file: {{story_file}}
- Branch: {{branch}}
- Story key: {{story_key}}
- Project knowledge: {{project_knowledge}}
- {{if review_continuation}}
  This is a REVIEW CONTINUATION. The story file already has a "Senior Developer
  Review (AI)" section with action items. Prioritize the unchecked Review Follow-ups
  (AI) tasks before any other work. The bmad-dev-story workflow has built-in logic
  for this in step 3 — let it detect and handle the continuation.
- {{endif}}

YOLO OVERRIDES FOR THIS STAGE:
- bmad-dev-story step 1: if no story file is found, STOP and escalate. Do not pick
  an arbitrary story.
- bmad-dev-story step 5: if "3 consecutive implementation failures" HALT triggers,
  STOP and escalate with the failures captured.
- bmad-dev-story step 5: if "new dependencies required beyond story specifications"
  HALT triggers, STOP and escalate. Do not silently add deps.
- bmad-dev-story step 10: when the workflow finishes and asks "ask if user needs any
  explanations" — skip the conversation, treat the workflow as complete, return
  the structured summary.

COMMIT GRANULARITY:
- One `code:` commit per task in the Tasks/Subtasks section once that task's tests
  pass. Not one giant commit at the end.
- One `bmad:` commit when you update the story file's File List, Dev Agent Record,
  status transitions (e.g. → review). These can be batched if they happen in the same
  step.
- The story file gets updated multiple times during a dev-story run. Commit it at
  natural punctuation: after marking a task complete, after the final status change.

DEFINITION OF DONE FOR THIS STAGE:
The story file's `Status:` line must read `review` (or `done` if a code-review run
just completed and this was a fix iteration that landed everything cleanly). All
tasks/subtasks in the relevant section checked. File List populated. Tests pass.

RETURN: the structured summary.
```

---

## Stage 4a — Code review (template: `code-review`)

```
{{shared operating contract}}

YOUR MISSION:
Run the bmad-code-review BMAD skill against the current branch's changes for story
`{{story_key}}`.

CONTEXT:
- Story file: {{story_file}}
- Branch: {{branch}}
- Story key: {{story_key}}
- This is review iteration #{{iter}} of max {{max_iters}}.

YOLO OVERRIDES FOR THIS STAGE — these are critical:
- step-04-present.md section 4 ("Resolve decision-needed findings"): the skill will
  HALT and ask "Reply with only the number". For each `decision-needed` finding,
  DEFER it (mark as deferred with the reason "autonomous yolo run — requires human
  judgment, deferred for review"). Do NOT attempt to resolve decision-needed items
  yourself; they exist precisely because the answer is ambiguous.
- step-04-present.md section 5 ("Handle patch findings"): the skill will HALT with
  options 0/1/2/3. ALWAYS choose option 0 (Batch-apply all) — apply every
  non-controversial patch automatically. Skip any individual patch that genuinely
  requires judgment, but apply the rest.
- step-04-present.md section 7 ("Next steps"): when the skill asks what to do next
  (1/2/3), choose option 3 (Done) — your job is finished, return the summary.

COMMIT GRANULARITY:
- One `code:` commit per coherent group of patches applied (you can group patches
  that touch the same file or solve the same class of issue).
- One `bmad:` commit when the story file gets the `### Review Findings` section
  appended and Status updated.
- One `bmad:` commit when deferred-work.md gets new entries.

CRITICAL: After the skill completes, re-read the story file's `Status:` line and
report it in your summary. The orchestrator uses this to decide whether to loop:
- `done` → review converged, no more iterations needed
- `in-progress` → unresolved findings remain, loop will run dev-story again

RETURN: the structured summary. Include in `next_action_hint`:
- "review_converged" if Status: done
- "needs_dev_fix: <count> findings" if Status: in-progress
```

---

## Stage 5 — Tech writer (template: `tech-writer`)

```
{{shared operating contract}}

YOUR MISSION:
Update or create project documentation for the changes made in story `{{story_key}}`.
Use the bmad-agent-tech-writer skill's `WD` (write-document) capability — but skip
the persona greeting and menu interaction; go straight to the documentation work.

CONTEXT:
- Story file: {{story_file}}
- File List from the story (these are the implementation changes you're documenting):
{{file_list}}
- Project knowledge folder: {{project_knowledge}}
- Triggering signals (why the orchestrator decided docs likely need updating):
{{trigger_signals}}

YOLO OVERRIDES FOR THIS STAGE:
- Do NOT enter the Paige persona greeting / menu loop. Go directly to making
  documentation edits.
- If after inspecting the changes you conclude that no documentation actually needs
  updating (e.g. internal refactor with no public surface change), return
  `status: skipped` with a one-line reason. Do NOT invent doc updates just to have
  done something.
- If you do update docs, MAKE THE EDITS — do not propose them, do not write a plan.

SCOPE GUARDRAILS:
- Only update docs that relate to the changes in this story. Do not refactor unrelated
  documentation.
- Prefer editing existing docs over creating new ones. Create a new doc only if the
  story introduces a fundamentally new concept that has no existing doc home.
- README/CHANGELOG/quickstart updates are in scope if user-facing surface changed.

COMMIT GRANULARITY:
- One `docs:` commit per coherent doc update (e.g. one for README, one for a new
  concept doc).

RETURN: the structured summary. If you skipped, set status: skipped and explain why
in the summary field (one line is enough).
```

---

## Stage 7 — CI fix (template: `ci-fix`)

```
{{shared operating contract}}

YOUR MISSION:
The CI for branch `{{branch}}` failed. Diagnose the failure and fix it. After your
fix, push the branch (this is the ONE stage where the subagent pushes — because the
fix loop polls CI on the new commit).

CONTEXT:
- Story file: {{story_file}}
- Branch: {{branch}}
- Story key: {{story_key}}
- This is CI fix iteration #{{iter}} of max {{max_iters}}.
- Failure log (truncated to the failing job's output):

```
{{failure_log}}
```

YOLO OVERRIDES / DECISION:
- If the failure is in code or tests that this story introduced or modified, run
  bmad-dev-story on the story file in REVIEW CONTINUATION mode (pretend the failure
  is a review finding to address) — but you can also just fix it directly if it's
  obvious, without invoking the full BMAD skill.
- If the failure is in CI configuration (.github/workflows, .gitlab-ci.yml, etc.) or
  is a flaky/infrastructure issue not related to story code, use bmad-quick-dev to
  make the fix.
- If the failure is in test code unrelated to this story (pre-existing flakes), STOP
  and escalate — do not "fix" tests that aren't yours.
- If you cannot diagnose the failure from the log provided, STOP and escalate.

COMMIT GRANULARITY:
- `code:` for source/test fixes
- `bmad:` for story file updates (e.g. updated File List with new test files)

PUSH:
- After committing, run `git push` (no force, no `-u` since the upstream is already
  set). If push is rejected (remote moved), STOP and escalate — never force-push.

RETURN: the structured summary. Include in `next_action_hint`:
- "ci_fix_pushed" — orchestrator should re-watch CI
- "needs_human" — orchestrator should escalate
```

---

## Notes on subagent invocation

When you call `Agent({subagent_type: "general-purpose", description: "...", prompt: "..."})`:

- **Description** should be ≤5 words: "Stage N: <name>".
- **Prompt** must be the full template above with placeholders substituted — never link to a file path and expect the subagent to read it (subagents start cold and may not have access in the same way).
- **Run synchronously** (`run_in_background: false`). Stages are sequential; the orchestrator needs each summary before deciding the next stage.
- **One subagent at a time.** Never spawn parallel subagents in this workflow — they'd race on the git working tree and step on each other's commits.
