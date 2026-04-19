# M2 Accept-Edits Dogfood 2026-04-20

## Purpose

Reduce M2 observer/supervision overhead for small focused edits without
changing the default approval boundary.

This slice adds an explicit `--approval-mode accept-edits` mode. When requested,
mew applies changed dry-run `write_file` / `edit_file` previews automatically,
while preserving configured write roots, paired-test source-edit guards, and
approval-time verification.

## Implementation

- `mew do`, `mew work`, and `mew code` accept `--approval-mode accept-edits`.
- Work-session defaults remember the mode, so `/continue`, `/follow`, and
  resume controls keep the same permission posture.
- Auto approval uses the internal approval path directly, so `--json` work-loop
  output remains parseable instead of being polluted by nested approval output.
- The final work-loop report records the auto approval status and applied tool
  id.
- M2 comparative dogfood now records the mew-side session's `approval_mode` and
  default permission posture, so future comparison artifacts can tell whether a
  run used the low-friction mode.

## Validation

```bash
uv run ruff check src/mew/commands.py src/mew/dogfood.py tests/test_work_session.py tests/test_dogfood.py
git diff --check
uv run pytest --no-testmon -q \
  tests/test_work_session.py::WorkSessionTests::test_work_live_accept_edits_mode_auto_applies_dry_run_write \
  tests/test_work_session.py::WorkSessionTests::test_work_json_accept_edits_mode_keeps_stdout_parseable \
  tests/test_dogfood.py::DogfoodTests::test_run_dogfood_work_session_scenario
./mew dogfood --scenario work-session --workspace /tmp/mew-accept-edits-work-session-dogfood --json
./mew dogfood --scenario m2-comparative \
  --workspace /tmp/mew-m2-approval-mode-evidence \
  --mew-session-id 250 \
  --json
```

Observed:

- focused pytest: `3 passed`
- dogfood: `pass`
- dogfood check added: `work_ai_accept_edits_auto_applies_preview`
- focused comparative evidence check confirms `approval_mode: accept-edits` is
  serialized into JSON and the markdown runbook.
- comparative artifact:
  `/tmp/mew-m2-approval-mode-evidence/.mew/dogfood/m2-comparative-protocol.json`
  records `approval_mode: accept-edits`, the default permission posture, and
  the passing verifier from mew work session `#250`.

## Interpretation

This does not close M2 by itself. It gives the resident a Claude Code-like
`acceptEdits` mode for low-friction small edits and creates executable dogfood
evidence that the mode works without breaking JSON observation.

The real dogfood task also exposed a remaining M2 gap: test-first edits can
still run verification before the source-side companion edit lands unless the
resident explicitly defers verification or the system can apply the paired edit
as a batch. That points back to batch or multi-action approval as the next
stronger M2 lever.

Next M2 evidence should compare a real small write-heavy task using
`accept-edits` against a fresh CLI run and record whether the result moves from
`fresh_cli_preferred` toward `equivalent`.
