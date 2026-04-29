# DESIGN 2026-04-29 - M6.24 Runtime Artifact Freshness

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> runtime_artifact_cleanup_external_verifier_alignment -> rerun make-doom-for-mips same shape`

## Trigger

The hard-runtime same-shape rerun in
`docs/M6_24_HARD_RUNTIME_RERUN_2026-04-29.md` stayed 0/5, but the best trial
reached a stronger state than prior attempts:

- built `/app/doomgeneric_mips`
- ran exact `node vm.js`
- observed Doom startup stdout
- verified `/tmp/frame.bmp` as a valid 640x400 32bpp BMP
- external verifier reached 2/3

The remaining miss was caused by verifier freshness. The agent's self-check
left `/tmp/frame.bmp` in place. The external verifier waits until that path
exists, waits one second, then terminates the fresh VM process. Since the stale
frame existed before the verifier started, stdout was captured too early.

## Architecture Fit

Decision: `implementation_profile`.

This repair stays in the authoritative implementation/tiny lane. It strengthens
the finish policy for generated runtime artifacts and external verifier
alignment, while preserving the same coding authority: produce the task change,
run or preserve verifier evidence, and block false completion.

No new lane is introduced because artifact freshness is a verifier/finish
contract inside the implementation lane. A future verifier helper lane may
audit these proofs, but the write-capable owner remains implementation/tiny.

## v0 Repair

Implemented in:

- `src/mew/acceptance.py`
- `src/mew/work_session.py`
- `src/mew/work_loop.py`

Behavior:

- task text that combines a fresh runtime command with generated `/tmp/...`
  artifacts is recognized as a runtime artifact freshness surface
- `acceptance_finish_blocker()` blocks `task_done=true` when a completed
  self-check created a runtime `/tmp/...` artifact and no later cleanup command
  is visible
- work-session resume now surfaces
  `stale_runtime_artifact_risk` with the artifact path, source tool, and cleanup
  guidance
- the THINK prompt tells the model to preserve self-check evidence, then clean
  stale runtime artifacts before finish unless the task explicitly requires the
  artifact to pre-exist

This is generic arbitrary-workspace behavior. It applies to frames, screenshots,
runtime logs, sockets, pid files, and similar generated verifier artifacts. It
does not encode Doom or Terminal-Bench-specific logic.

## Validation

Focused validation:

```sh
uv run pytest tests/test_acceptance.py -k 'runtime_artifact or complete_verified_checks' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'stale_runtime_artifact or runtime_contract_gap or work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py src/mew/work_loop.py tests/test_acceptance.py tests/test_work_session.py
```

Observed:

- `3 passed, 48 deselected`
- `4 passed, 767 deselected`
- `ruff`: all checks passed

## Same-Shape Rerun Gate

Next proof should rerun:

`terminal-bench/make-doom-for-mips`

Accept as improved only if:

- no stale runtime artifact finish is accepted
- the best trial no longer fails because `/tmp/frame.bmp` pre-exists before the
  external verifier starts
- reward improves, or external verifier passes the previously failing stdout
  timing condition in the best trial

If the rerun remains 0/5 but fails on a different concrete verifier condition,
record that new condition in `proof-artifacts/m6_24_gap_ledger.jsonl` before
choosing another repair.
