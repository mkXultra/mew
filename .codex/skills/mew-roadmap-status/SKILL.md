---
name: mew-roadmap-status
description: Update mew roadmap milestone status. Use when asked to assess progress against ROADMAP.md, refresh milestone statuses, decide the next roadmap target, or preserve roadmap progress across context compression.
---

# Mew Roadmap Status

Use this skill to keep mew's roadmap operational, not just aspirational.

Workflow:

1. Read `ROADMAP.md`.
2. Read `ROADMAP_STATUS.md` if it exists.
3. Inspect only the evidence needed:
   - `git status --short`
   - recent commits, usually `git log --oneline -n 10`
   - relevant files/tests for the milestone being assessed
   - latest test or dogfood results if already available
   - if side-project dogfood is active: `SIDE_PROJECT_ROADMAP_STATUS.md`,
     `mew side-dogfood report --json`, and open GitHub issues with the
     `[side-pj]` title prefix
4. Update `ROADMAP_STATUS.md` with:
   - status for each milestone
   - concrete evidence
   - missing proof, or a current blocker when progress is blocked by an external dependency or decision
   - next action
   - latest validation
5. Keep the status candid. Do not mark a milestone complete unless the "Done when" criteria in `ROADMAP.md` are actually met.

Formatting rules:

- Preserve the existing `ROADMAP_STATUS.md` structure unless there is a clear reason to change it:
  - summary table
  - one section per roadmap milestone
  - `Evidence`
  - `Missing proof`
  - `Next action`
  - `Latest Validation`
  - `Current Roadmap Focus`
- Update `Last updated` to the current local date when editing `ROADMAP_STATUS.md`.
- Prefer `Missing proof` over vague blockers. Use `blocked` only for a real external decision, missing dependency, or unavailable prerequisite.

Evidence rules:

- Do not treat dirty worktree changes as completed work unless their behavior is verified.
- Use recent commits as evidence only when they directly support the milestone assessment.
- Inspect only files directly related to the milestone being assessed.
- Do not mark validation as current unless it was run in the same update session.
- If validation was not rerun, keep it as `last observed` or state that it was not rerun.
- If a milestone status changes, include the concrete proof that justified the change.
- If an open `[side-pj]` problem issue exists, record it only when it affects
  the current main milestone, M6.14 repair work, or M6.16 implementation-lane
  evidence. Normal side-project progress should stay in
  `SIDE_PROJECT_ROADMAP_STATUS.md` and the side-project dogfood ledger, not the
  main roadmap.

Focus rule:

- `Current Roadmap Focus` should normally be the earliest milestone whose "Done when" criteria are not satisfied and whose next action unlocks later milestones.
- Do not move focus to later polish work while an earlier enabling milestone is still missing its core user value.
- Do not let a side-project issue preempt the active roadmap focus unless it is
  a true exception: a core mew blocker, a reproducible M6.14 repair candidate,
  or a required M6.16 evidence collection issue.

Side-project issue queue command:

```bash
gh issue list --state open --search "[side-pj] in:title" --json number,title,url,updatedAt
```

If `gh` is unavailable or offline, continue with local roadmap evidence and
write that the issue queue was not checked.

Status vocabulary:

- `not_started`: no meaningful implementation yet
- `foundation`: supporting pieces exist, but the milestone's core user value is not usable
- `in_progress`: core implementation exists and is being exercised
- `blocked`: cannot progress without a decision or missing dependency
- `done`: all roadmap "Done when" criteria are satisfied and dogfooded

Product bar:

- The goal is not "feature exists".
- The goal is that frontier models would prefer to inhabit mew over Claude Code or Codex CLI for task/coding work.
- When uncertain, bias toward a lower status and write the missing proof.
