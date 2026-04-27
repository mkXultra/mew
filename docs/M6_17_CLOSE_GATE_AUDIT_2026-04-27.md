# M6.17 Close Gate Audit - Resident Meta Loop / Lane Chooser

Date: 2026-04-27 JST

## Verdict

M6.17 is closed.

The milestone goal was not autonomous dispatch. The v0 gate was a reviewer-gated
resident meta-loop proposal surface: it should read roadmap/task/memory and
calibration evidence, name a lane plan, preserve repair routing, and never
mutate dispatch/roadmap/memory state without approval.

## Done-When Check

| Criterion | Status | Evidence |
|---|---|---|
| Produce a reviewer-visible next-task and lane-dispatch proposal with evidence from roadmap status, memory, and calibration metrics | Met | Task `#679` added lane-dispatch fields to selector proposals. Recorded selector proposal `#26` selected task `#682` with `lane_dispatch`, calibration refs, failure cluster, and preference refs after M7 became active. Task `#681` also made the no-candidate fallback reviewer-visible when no safe candidate remains. |
| Proposal names authoritative lane, helper lanes, fallback, verifier, budget, and expected-value rationale | Met | `lane_dispatch` includes `authoritative_lane`, `helper_lanes`, `fallback_lane`, `verifier`, `budget`, `expected_value_rationale`, `repair_route`, and `reviewer_gate`. |
| Reviewer approval is required before dispatch in v0 | Met | Proposals keep `approval_required: true`; selector execution remains separate from proposal creation and no auto-dispatch was added. |
| After a completed work item, the meta loop can propose the next action or repair path without losing the active milestone gate | Met | Task `#680` fixed `mew next --kind coding` so stale older M6 paused work does not override the active roadmap focus. Task `#681` added `next_action` to no-candidate selector proposals. After moving active work to M7, `./mew next --kind coding` returns the M7 self-improve command, and `./mew task propose-next 681 --record --json` recorded blocked proposal `#25` with M7 `next_action`. |
| No task status, roadmap status, or durable memory write is mutated without the appropriate lane/reviewer/policy gate | Met | Selector proposal creation is read-only unless `--record` is explicitly used; `--record` records only a reviewer-visible proposal. No dispatch, roadmap status, or durable memory mutation is performed by the selector itself. |

## Key Evidence

- Commit `305ca09` added lane-dispatch details to selector proposals.
- Commit `22b3e61` kept coding next-move selection on the active M6 roadmap gate.
- Commit `b9a922d` exposed `next_action` for no-candidate selector fallback.
- Recorded selector proposal `#25` after M7 became active:
  - previous task: `#681`
  - candidate: none
  - status: blocked
  - lane dispatch: present
  - next action: `./mew self-improve --start-session --focus 'Advance M7 Senses: Inbound Signals'`
- Recorded selector proposal `#26` after M7 became active:
  - previous task: `#681`
  - candidate: `#682` (`M7: audit inbound signal surfaces and choose proof source`)
  - status: proposed
  - lane dispatch: present
  - calibration refs, failure cluster, and preference refs: present

## Validation

- `uv run python -m unittest tests.test_tasks tests.test_commands`
- `uv run python -m unittest tests.test_brief`
- `uv run python -m unittest tests.test_commands`
- `uv run ruff check src/mew/tasks.py src/mew/commands.py tests/test_tasks.py tests/test_commands.py`
- `uv run ruff check src/mew/brief.py tests/test_brief.py`
- `uv run ruff check src/mew/commands.py tests/test_commands.py`
- `git diff --check`

Codex-ultra review sessions:

- `019dcbc5-974b-7fc3-955b-b2bc869c74c3`: pass for task `#679`.
- `019dcbd8-e9bb-7880-9009-7efb152bc3eb`: pass for task `#680`.
- `019dcbe9-aae6-75d1-a17d-fb613f1ef4c3`: pass for task `#681`.
- `019dcbf0-ad2d-7233-a395-6a0ac7f37bc8`: pass for this close audit
  after recorded proposal `#26` was added to the proof.

## Autonomy Accounting

- `#679`: mixed. Mew produced the initial lane-dispatch patch; supervisor
  applied narrow review fixes. Product progress, not clean autonomy credit.
- `#680`: supervisor rescue. Mew produced three failing or too-broad drafts.
  No mew autonomy credit.
- `#681`: mixed. Mew produced the source/test patch and passed verification;
  supervisor applied small formatter polish. Partial autonomy credit.

## Residuals

- The resident meta loop is still reviewer-gated. Autonomous dispatch remains a
  later milestone.
- Selector status currently surfaces recorded proposal history but does not
  make the M6.17 close proof prominent. This is acceptable because close proof
  is captured here and in `ROADMAP_STATUS.md`.
- M6.17 does not implement inbound senses. That begins in M7.
