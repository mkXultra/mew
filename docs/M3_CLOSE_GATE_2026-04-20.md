# M3 Close Gate 2026-04-20

Status: close-gate proof passed.

This document closes Milestone 3, Persistent Advantage. The claim is not that
mew has solved every long-horizon autonomy problem. The claim is narrower and
evidence-based: returning to mew after interruption, context compression,
terminal close, or long-running resident cadence is now faster and safer than
starting from a fresh coding CLI on comparable task shapes.

## Behavior Proved

M3 was closed by combining three classes of evidence:

- fresh-restart comparisons where mew was preferred because it preserved the
  exact next action, failed verification context, pending approvals, and
  working memory;
- source/test reentry dogfood beyond README-only tasks;
- resident-loop cadence proofs across half-hour, one-hour, four-hour real
  time, plus week/ten-day synthetic or virtual-time reentry checks.

The final blocking proof was the 4h isolated Docker resident-loop run.

## Final 4h Real-Time Proof

Collection:

```bash
scripts/collect_proof_docker.sh mew-proof-real-4h-20260420-1312
./mew proof-summary proof-artifacts/mew-proof-real-4h-20260420-1312 --json --strict
```

Result: `pass`

Container:

- name: `mew-proof-real-4h-20260420-1312`
- image: `mew-proof:real-4h`
- status: `exited`
- exit code: `0`
- started: `2026-04-20T04:11:50.599898182Z`
- finished: `2026-04-20T08:11:54.418370245Z`

Artifacts:

- stdout: `proof-artifacts/mew-proof-real-4h-20260420-1312/stdout.log`
- stderr: `proof-artifacts/mew-proof-real-4h-20260420-1312/stderr.log`
- inspect: `proof-artifacts/mew-proof-real-4h-20260420-1312/inspect.json`

Resident-loop summary:

- requested duration: `14400.0` seconds
- requested interval: `60.0` seconds
- time dilation: `1.0`
- processed events: `240`
- passive events: `239`
- open questions: `1`
- deferred questions: `0`
- passive span: `14305.0` seconds
- passive gaps: `238`
- passive gap min/max: `60.0` / `61.0` seconds
- passive gaps outside expected interval by more than 2s: `0`

Checks:

- `resident_loop_starts_and_stops`: pass
- `resident_loop_processes_multiple_events`: pass
- `resident_loop_records_passive_effect`: pass
- `resident_loop_compacts_repeated_wait_thoughts`: pass
- `resident_loop_echoes_passive_output`: pass
- `resident_loop_reentry_focus_surfaces_next_action`: pass
- `resident_loop_reentry_brief_surfaces_current_state`: pass
- `resident_loop_reentry_context_saves_checkpoint`: pass

## Supporting Evidence

- `docs/M3_REENTRY_BURDEN_COMPARISON_2026-04-20.md` records a strict fresh
  comparator with `comparison_choice=mew_preferred`,
  `manual_rebrief_needed=false`, and `repository_only_compliance=true`.
- `docs/M3_SOURCE_REENTRY_DOGFOOD_2026-04-20.md` records a source/test reentry
  comparison with `comparison_result.choice=mew_preferred`.
- `docs/M3_RESIDENT_LOOP_30MIN_2026-04-20.md` and
  `docs/M3_RESIDENT_LOOP_1H_REAL_2026-04-20.md` proved shorter real-time
  resident cadence before the 4h close proof.
- `docs/M3_VIRTUAL_TIME_ISOLATED_10DAY_2026-04-20.md` proved long-horizon
  passive behavior and post-runtime reentry surfaces under virtual time.
- `docs/M3_AGED_REENTRY_7DAY_2026-04-20.md` proved week-scale aged reentry
  contracts in isolated dogfood.

## Interpretation

M3 is done because mew now has durable, inspectable resident continuity across
the failure modes that matter for inhabitation:

- after interruption or context compression, the model can recover the task,
  risk, next action, and verifier state from mew rather than chat memory;
- fresh CLI restarts can solve the tasks, but they spend extra steps
  reconstructing state that mew already preserved;
- passive resident loops continue for several hours in an isolated process and
  leave reentry surfaces that can be loaded after the runtime stops.

Multi-day real-time cadence would strengthen confidence further, but it is no
longer required to close M3. The combination of strict fresh-comparator wins,
source/test reentry proof, 10-day virtual-time proof, and 4h real-time cadence
is enough to move the active roadmap gate forward.
