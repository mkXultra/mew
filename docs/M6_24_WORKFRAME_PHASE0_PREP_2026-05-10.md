# M6.24 WorkFrame Phase 0 Prep

Purpose: keep the Phase 0 implementation decision durable across context
compression and prevent drift back to incremental HOT_PATH polish.

## Active Decision

Start `docs/DESIGN_2026-05-10_M6_24_IMPLEMENT_V2_WORKFRAME_REDESIGN.md`
from Phase 0.

This supersedes the older immediate next action to run another
`make-mips-interpreter` same-shape `step-check-10min`. The repeated
frontier/todo/evidence/contract repairs are now treated as enough signal to
prepare the WorkFrame reducer boundary.

## Phase 0 Target

Implement only the baseline/schema substrate:

- define `WorkFrame`, `WorkFrameInputs`, `WorkFrameTrace`, and
  `WorkFrameInvariantReport`;
- implement a fixture-only deterministic reducer over saved sidecar facts;
- add prompt inventory checks proving legacy model-visible projections are
  still present before cutover;
- document the debug bundle shape;
- record baseline metrics for prompt bytes, tool-result bytes, sidecar bytes,
  first edit, first verifier, model turns, tool calls, same-family repeats, and
  WorkFrame size.

## Non-Goals

- no live Harbor benchmark;
- no `speed_1`, `proof_5`, or new same-shape step-check spending;
- no Phase 1 prompt cutover;
- no provider-native tool-calling redesign;
- no task-specific MIPS, VM, DOOM, or Terminal-Bench solver rule;
- no backward-compatibility adapters for old unreleased `implement_v2`
  projections.

## Close Gate

Phase 0 is closeable only when:

- the schema exists and is reviewed;
- reducer fixture recomputation is deterministic on current head;
- canonical fixture hash recomputation passes on current head;
- prompt inventory checks prove old projection surfaces are still detectable
  before cutover;
- debug bundle format is documented;
- all calibration metrics have green/yellow/red bands or explicitly block
  progression;
- focused unit tests and the Phase 0 fastcheck pass;
- `git diff --check` passes;
- no live benchmark was spent for Phase 0.

## Reentry Rule

After context compression or interruption, read this file, the WorkFrame design,
`ROADMAP_STATUS.md`, and `docs/M6_24_DECISION_LEDGER.md` before selecting work.
If those files conflict with older HOT_PATH rows, this Phase 0 prep decision is
newer and wins.

The next implementation action is: create the Phase 0 schema, reducer fixture,
prompt inventory checks, and baseline metric recording. Do not resume
same-shape `step-check-10min` until Phase 0 closes and the next phase explicitly
authorizes it.
