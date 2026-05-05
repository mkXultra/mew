# M6.24 Acceptance Closeout Evidence Repair - 2026-05-02

## Trigger

The post-stale-blocker clean-closeout rerun for `terminal-bench/compile-compcert`
externally passed with reward `1.0`, but `mew work` still exited `1`.

Evidence:

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-stale-blocker-clearing-compile-compcert-1attempt-20260502-0140/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-stale-blocker-clearing-compile-compcert-1attempt-20260502-0140/compile-compcert__UpEUdBT/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-stale-blocker-clearing-compile-compcert-1attempt-20260502-0140/compile-compcert__UpEUdBT/verifier/test-stdout.txt`

## Diagnosis

The task itself succeeded. The external verifier passed all checks, and the
final command evidence proved:

- upstream v3.13.1 source URL and archive identity
- executable `/tmp/CompCert/ccomp`
- default runtime/header installation
- default compile/link/run smoke

The internal closeout failed because the deterministic long-dependency
acceptance guard rejected valid final proof:

1. A harmless section header such as
   `printf '== required artifact /tmp/CompCert/ccomp =='` was treated as
   spoofed artifact output.
2. An unrelated linker warning containing `missing .note.GNU-stack` was treated
   as proof that the target artifact was missing.

## Repair

`src/mew/acceptance_evidence.py` now separates harmless labels and unrelated
warnings from spoofed proof:

- echo/printf output is rejected only when it emits proof-shaped artifact facts
  such as permissions, `exists=true`, file-type markers, or smoke markers.
- `missing` / `not found` / `no such file` only invalidates artifact proof when
  the same output line also references the target artifact.
- proof segments are tracked using unquoted shell segment spans so quoted copies
  of commands do not count as real probes.
- proof segments whose failure can be masked by `||`, later `;` / newline
  commands, `set +e`, or skipped `&&` chains are rejected.

## Validation

- `uv run pytest --no-testmon -q tests/test_acceptance.py -k 'long_dependency or masked_probe or late_errexit or disabled or quoted_probe or and_skipped or and_chain or and_lhs'`
- `uv run pytest --no-testmon -q tests/test_acceptance.py tests/test_long_build_substrate.py tests/test_work_session.py -k 'long_dependency or source_provenance or runtime_link or wall_budget or recovery or acceptance'`
- `uv run ruff check src/mew/acceptance_evidence.py tests/test_acceptance.py`
- real failing report replay now allows the final `finish`
- codex-ultra review session `019de48d-a6aa-7a32-9a70-d5cf4d943c2f` returned `PASS`

## Next

Run one same-shape `compile-compcert` speed proof again. The close gate is:

- Harbor reward `1.0`
- runner errors `0`
- `command-transcript.json` exit code `0`
- `mew-report.json` shows clean internal closeout

Do not run proof_5 or resume broad measurement until that clean-closeout speed
proof is recorded.
