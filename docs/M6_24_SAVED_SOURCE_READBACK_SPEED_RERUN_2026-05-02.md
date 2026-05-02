# M6.24 Saved Source Readback Speed Rerun - 2026-05-02

## Run

Job:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-saved-source-readback-compile-compcert-1attempt-20260502-1302`

Command shape:

- task: `terminal-bench/compile-compcert`
- trials: `1`
- model: `gpt-5.5`
- auth: `/Users/mk/.codex/auth.json`
- mew command: `mew work --oneshot ... --defer-verify`

## External Result

- Harbor mean: `1.000`
- trials: `1`
- exceptions: `0`
- reward: `1.0`
- runtime: `30m 21s`

The external verifier passed. This confirms mew can still solve the
`compile-compcert` task after the saved source readback hardening.

## Internal Closeout

The internal mew closeout gate still did not close:

- `mew-report.work_exit_code`: `1`
- `source_authority`: `unknown`
- `current_failure`: `artifact_missing_or_unproven`
- `strategy_blockers`: `[]`

Local replay after the follow-up artifact-proof repair changes the internal
state to:

- `target_built`: `satisfied`
- `default_smoke`: `satisfied`
- `current_failure`: `null`
- `strategy_blockers`: `[]`
- `source_authority`: still `unknown`

## Root Cause

There were two separate issues.

First, the final proof command built and smoked `/tmp/CompCert/ccomp`
successfully, then used `set +e` only after the strict compile segment to
capture the smoke program exit code. The reducer treated any later `set +e` as
disabling `errexit` for the earlier proof segment, so it failed to recognize
the artifact/default-smoke proof. This was too conservative.

Second, the source readback was top-level and unguarded, but it appeared before
a noisy `make ccomp` continuation. Retained command output clipped away the
archive hash/root lines, so `source_authority` remained `unknown`. The model
must place or repeat saved source readbacks near the final proof after noisy
build/install output.

## Repair

- Make the default-smoke artifact proof mask check segment-local for `errexit`.
  A later `set +e` no longer invalidates an earlier strict proof segment.
- Update the work-loop guidance: when proving saved source authority, place or
  repeat archive metadata/hash/root readback after noisy build/install output
  and close to final artifact proof.

## Validation

- Targeted tests: `23 passed, 1069 deselected`
- Combined long-build/work-session/acceptance: `1224 passed, 1 warning, 67 subtests passed`
- Scoped ruff: passed
- `git diff --check`: passed
- `codex-ultra` review session `019de6a8-c827-75f3-974b-67a08d05b5b2`: `STATUS: APPROVE`

## Next Action

Run one same-shape `compile-compcert` speed_1 again. The close gate remains:

- Harbor reward `1.0`
- runner errors `0`
- command transcript exit `0`
- `mew-report.work_exit_code=0`
- `source_authority=satisfied`
- `current_failure=null`
- `strategy_blockers=[]`
