# M6.24 `compile-compcert` Parallel Proof-5 Result

Task: `compile-compcert`

Result:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-wall-target-compile-compcert-5attempts-20260430-0644/2026-04-30__06-44-04/result.json`

## Summary

- trials: `5`
- errors: `0`
- reward: `0/5`
- runtime: `31m 03s`
- all trials ended with `mew work` `stop_reason=wall_timeout`
- verifier failure shape: `/tmp/CompCert/ccomp` missing in every trial

This is useful evidence, but it is not a clean close-gate failure for the
selected repair.

## Interpretation

The immediately preceding speed proof passed `1/1` in `25m 38s` on the same
head and command shape. This five-trial run started five full Coq/CompCert
source builds in parallel on the same host. All trials reached long dependency
build states and then hit wall timeout.

The difference between `speed_1=pass` and `parallel proof_5=0/5` points to
resource contention in the proof harness, not a new generic mew implementation
loop blocker.

## Decision

For CPU-heavy long dependency/toolchain builds, M6.24 proof escalation must be
resource-normalized:

- run the same per-trial command shape;
- use sequential or low-concurrency Harbor scheduling;
- record the scheduling choice explicitly in the decision ledger;
- do not start a mew-core repair solely from high-parallelism timeout evidence.

Next action:

Run a resource-normalized five-trial proof for `compile-compcert`, starting
with sequential `-k 5 -n 1`, unless a user decision changes the proof budget.

## Invalid Sequential Probe

An attempted rerun used `-k 1 -n 5` at:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-wall-target-compile-compcert-5attempts-seq-20260430-0719/2026-04-30__07-19-17/result.json`

That run is not score evidence:

- Harbor created `n_total_trials: 1`, so `-k 1 -n 5` is not a five-trial
  sequential proof shape.
- The single trial failed before any work because `/Users/mk/.codex/auth.json`
  returned `HTTP 429 usage_limit_reached`.

Correct next proof shape: `-k 5 -n 1`, with a non-quota-limited auth file.
