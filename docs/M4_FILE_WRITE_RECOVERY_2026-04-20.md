# M4 File-Write Recovery Proof 2026-04-20

Status: passed.

This proof is the first M4 slice after the M3 persistent-advantage gate moved
to background real-time monitoring. It exercises deterministic recovery for an
interrupted apply-write work-session tool.

## Implementation

- `start_work_tool_call` now records a `write_intent` before an applied
  `write_file` or `edit_file` runs.
- The intent stores the target path, pre-write hash, intended post-write hash,
  expected size, verifier command, and verifier cwd.
- Interrupted applied writes are classified from live world state:
  - `not_started`: target still matches the pre-write hash and no atomic temp
    file remains.
  - `completed_externally`: target already matches the intended post-write hash.
  - `partial`: an atomic temp file remains near the target.
  - `target_diverged`: target matches neither pre-write nor intended hashes.
- `mew work --recover-session` can now:
  - resume a `not_started` applied write with explicit `--allow-write`,
    `--allow-verify`, and matching `--verify-command`;
  - skip a `completed_externally` write and rerun the recorded verifier.

## Proof

Command:

```bash
./mew dogfood --scenario m4-file-write-recovery --workspace proof-workspace/mew-proof-m4-file-write-recovery-local-20260420-1130 --json
```

Result:

- status: `pass`
- checks:
  - `m4_file_write_recovery_retries_not_started_apply_write`
  - `m4_file_write_recovery_skips_completed_write_and_verifies`
  - `m4_file_write_recovery_reports_target_diverged_review`
  - `m4_file_write_recovery_reports_partial_review`

## Interpretation

M3 proved that mew can preserve enough state to explain interrupted work.
This M4 slice proves the next step: for a narrow side-effect class, mew can
revalidate the world and safely choose a concrete recovery action instead of
only narrating the interruption.

This does not close M4. It covers applied file writes with hash-based recovery
and explicit review reporting for diverged or partial targets. Runtime effects,
shell commands, rollback-required writes, and broader passive auto-recovery
remain future work.
