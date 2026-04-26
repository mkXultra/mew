---
name: side-pj-mew-impl
description: Run isolated mew side-project implementation as mew-first dogfood, update SIDE_PROJECT_ROADMAP_STATUS.md, and record structured M6.13.2 telemetry for M6.16 implementation-lane polish.
---

# Side Project Mew Implementation

Use this skill when starting, reviewing, or updating side-project work that is
meant to dogfood mew's implementation lane.

Goal: make mew implement a real isolated side project while preserving clean
evidence about whether mew can actually do the work. The side-project Codex CLI
is an independent operator, not a subordinate agent that waits for main Codex
instructions after every step.

## Required Reads

1. `SIDE_PROJECT_ROADMAP.md`
2. `SIDE_PROJECT_ROADMAP_STATUS.md`
3. `ROADMAP_STATUS.md` only when core milestone interaction matters
4. `mew side-dogfood report --json` to see current telemetry

## Operating Rule

- mew is the default implementer.
- Side-project Codex CLI is normally `operator`: it runs mew from the
  side-project directory, makes local decisions, and supervises the attempt.
- Codex/Codex CLI may also be `reviewer`, `comparator`, or `verifier` when it
  checks mew's work.
- If Codex/Codex CLI writes the product patch, record that role as `fallback`
  or `implementer`; do not count it as mew-first autonomy credit.
- Keep the side project isolated in a separate worktree or directory.
- Do not edit core mew from the side-project lane unless the failure is a
  classified M6.14 repair blocker or a later M6.16 measured hardening slice.
- Do not make GitHub issues for normal progress. GitHub issues are the
  exception queue: one real problem per issue, using only open/closed state.

## Workflow

1. Pick one bounded side-project task from `SIDE_PROJECT_ROADMAP_STATUS.md`.
2. Before implementation, define:
   - side project name
   - branch or worktree
   - expected files
   - focused verifier
   - expected Codex/Codex CLI role, normally `operator`
3. In the side-project directory, let Codex CLI operate mew instead of editing
   the product code directly.
4. Let mew attempt the implementation first.
5. Review with Codex/Codex CLI as reviewer/comparator/verifier when needed.
6. Run the focused verifier.
7. Write a local structured result report in the side-project report outbox.
8. Only create a GitHub issue when there is a real problem that main Codex
   should process.
9. Stop instead of implementing directly when mew cannot complete the task.

## Two-Directory Model

There are two active shells/agents:

- main mew repo Codex: stays in `/Users/mk/dev/personal-pj/mew`, maintains
  milestones, status, skills, and the canonical dogfood ledger
- side-project Codex CLI: works in the side-project directory and operates mew
  to make mew implement the side project

The side-project Codex CLI should run mew from the side-project directory, for
example:

```bash
cd <side-project-dir>
/Users/mk/dev/personal-pj/mew/mew code <task-id> --allow-read . --allow-write .
```

Append/report telemetry from the main mew repo, not from the side-project
branch:

```bash
cd /Users/mk/dev/personal-pj/mew
./mew side-dogfood append --input <record.json>
./mew side-dogfood report --json
```

This keeps the canonical ledger on the main branch while the side-project code
can live on its own branch or worktree.

## Normal Report Line

Normal progress stays local. The side-project Codex CLI should write one JSON
record per completed attempt under the side-project directory, for example:

```text
.mew-dogfood/reports/<task-id>-<short-summary>.json
```

Use the main repo template as the schema source:

```bash
/Users/mk/dev/personal-pj/mew/mew side-dogfood template
```

Main Codex will poll the side-project report outbox and append accepted records
to the canonical main-branch ledger:

```bash
cd /Users/mk/dev/personal-pj/mew
./mew side-dogfood append --input <side-project-report.json>
```

The side-project Codex CLI should not need to update the main ledger directly.

## Problem Report Line

Use GitHub issues only for problems. Do not use labels for the first version;
GitHub's open/closed state is enough. Use the title prefix `[side-pj]` so main
Codex can poll issues without labels.

Create one issue per problem when:

- mew repeats the same failure after bounded steering
- mew cannot produce a product patch without operator-written code
- verifier failure requires operator product-code edits to fix
- scope drift or wrong-target behavior repeats
- the task spec is ambiguous enough that the ledger row cannot be written
  honestly
- the failure appears to be a core mew loop/substrate problem

The issue should include:

- title prefix `[side-pj]`
- side project and task summary
- command(s) used to operate mew
- what mew attempted
- verifier output or failure evidence
- why the operator stopped
- whether this looks like side-project task repair, M6.14 repair, or M6.16
  implementation-lane hardening input

Main Codex processes open problem issues while continuing main milestone work.
When resolved, close the issue. No `adding/getting/fixing` labels are needed.

## Operator Effort Boundary

The side-project Codex CLI should try hard to operate mew, but should not become
the implementer.

Allowed operator work:

- split or clarify the task
- give mew focused steering
- run inspections, diffs, and verifiers
- reject bad mew patches
- ask mew for a retry
- create local report JSON
- create a problem issue when blocked
- perform non-product setup needed to let mew run, such as opening the worktree
  or preparing task metadata

Disallowed operator work unless explicitly recorded as `fallback` or
`implementer`:

- writing the product diff directly
- fixing verifier failures by hand
- reshaping mew's failed patch into a successful patch
- hiding a failed mew attempt behind a Codex-authored commit
- claiming clean/practical mew-first credit for operator-authored code

Stop and report instead of coding when any of these are true:

- two focused steering attempts lead to the same failure class
- 30 minutes pass without material implementation progress
- the verifier failure cannot be fixed without operator product-code edits
- mew does not understand the task scope after clarification
- the next useful action would be for Codex CLI to write the product patch
- the result cannot be recorded honestly as mew-authored work

## Ledger Commands

Create a record template:

```bash
./mew side-dogfood template
```

Append a completed attempt:

```bash
./mew side-dogfood append --input <record.json>
```

Summarize current evidence:

```bash
./mew side-dogfood report --json
```

Default ledger:

```text
proof-artifacts/side_project_dogfood_ledger.jsonl
```

## Required Ledger Fields

Every attempt should record:

- `task_id`
- `session_id`
- `side_project`
- `branch_or_worktree`
- `task_summary`
- `task_kind`
- `codex_cli_used_as`
- `first_edit_latency`
- `read_turns_before_edit`
- `files_changed`
- `tests_run`
- `reviewer_rejections`
- `verifier_failures`
- `rescue_edits`
- `outcome`
- `failure_class`
- `repair_required`
- `proof_artifacts`
- `commit`

Use `codex_cli_used_as` values exactly as the CLI accepts:

```text
operator | reviewer | comparator | verifier | fallback | implementer | none
```

Use `outcome` values exactly as the CLI accepts:

```text
clean | practical | partial | failed
```

## First Project Preference

Prefer `mew-companion-log` first.

Reason: it is medium-sized, local-first, fixture-testable, and product-relevant
without GUI, OS-permission, TTS, screen-capture, or network noise.

## Stop Rules

Stop and create a problem issue when:

- the side-project task wants to modify core mew
- the proof command is missing
- Codex/Codex CLI had to implement the product patch
- the same failure class repeats and looks like a loop substrate problem
- the ledger row cannot be completed honestly
- mew cannot implement the task without operator product-code edits

## Status Update Rule

Main Codex updates `SIDE_PROJECT_ROADMAP_STATUS.md` after polling side-project
reports or processing a problem issue. Side-project Codex does not need to edit
main status for normal progress.

When status is updated, include:

- task summary
- outcome
- verifier result
- ledger row path or row number
- whether mew-first credit is clean, practical, partial, or none
- next action
- any open problem issue that needs main-side action

Do not mark a side-project milestone done unless its Done-when criteria in
`SIDE_PROJECT_ROADMAP.md` are satisfied.
