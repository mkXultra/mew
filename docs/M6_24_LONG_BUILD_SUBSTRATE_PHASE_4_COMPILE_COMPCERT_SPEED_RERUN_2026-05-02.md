# M6.24 Phase 4 Speed Rerun: compile-compcert

Date: 2026-05-02 JST

## Shape

- Task: `terminal-bench/compile-compcert`
- Requested shape: `-k 1 -n 1`
- Job: `mew-m6-24-long-build-substrate-phase4-compile-compcert-1attempt-20260502-0050`
- Auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- Command wall: Harbor `timeout_seconds=1800`, mew `--max-wall-seconds 1740`

## Result

- Harbor mean: `1.000`
- Reward: `1/1`
- Runner errors: `0`
- Total runtime: `30m 34s`
- Trial: `compile-compcert__3reNT9X`

External verifier passed:

- `test_compcert_exists_and_executable`
- `test_compcert_valid_and_functional`
- `test_compcert_rejects_unsupported_feature`

Evidence:

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-build-substrate-phase4-compile-compcert-1attempt-20260502-0050/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-build-substrate-phase4-compile-compcert-1attempt-20260502-0050/compile-compcert__3reNT9X/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-build-substrate-phase4-compile-compcert-1attempt-20260502-0050/compile-compcert__3reNT9X/verifier/test-stdout.txt`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-build-substrate-phase4-compile-compcert-1attempt-20260502-0050/compile-compcert__3reNT9X/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-build-substrate-phase4-compile-compcert-1attempt-20260502-0050/compile-compcert__3reNT9X/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`

## Readout

The external task shape is viable after Phase 4. mew built and verified
`/tmp/CompCert/ccomp`; the external Terminal-Bench verifier passed all checks.

However, the run exposed an internal closeout defect before proof escalation:
`mew work` kept historical long-build strategy blockers active after later
source-authority, final-artifact, and default-smoke command evidence succeeded.
The command transcript therefore exited nonzero even though the external
verifier scored `1.0`.

This is not a benchmark-specific solver issue. It is a generic reducer issue:
historical strategy blockers should remain available as cleared history, but
must not remain `current_failure` once the long-build contract is satisfied.

## Follow-Up Repair

Implemented in the same checkpoint:

- direct source-authority detection now accepts authority-bearing acquisition
  output such as `upstream_ref_url=...`, `upstream_ref=...`,
  `authority_archive_url=...`, or `matched_authority_url=...` even when the
  command contains harmless section headers;
- local identity output such as `local_sha256=...` or `archive_top=...` does
  not count as standalone source authority;
- assertion-only echo/header cases remain rejected;
- `reduce_long_build_state()` computes active strategy blockers separately from
  cleared historical blockers;
- once source authority, required artifact proof, and required runtime/default
  smoke are satisfied, stale strategy blockers no longer keep the state blocked.

Validation:

- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py`
  - 60 passed
- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py -k 'long_build or source_provenance or runtime_link or wall_budget or recovery'`
  - 121 passed, 802 deselected
- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py`
  - 1044 passed, 1 warning, 67 subtests passed
- `uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`

codex-ultra review:

- `docs/REVIEW_2026-05-02_M6_24_STALE_STRATEGY_BLOCKER_CLEARING_CODEX.md`
- session `019de45d-0f50-7623-b441-b13158656286`
- first round required tighter source-authority markers;
- final round returned `PASS`.

## Next

Run one more same-shape `compile-compcert` speed_1 after the stale-blocker
repair. The expected improvement is not just external reward `1.0`; `mew work`
should also close cleanly instead of exhausting steps on stale blocker repair.

Do not run proof_5 or broad measurement until this rerun is recorded.
