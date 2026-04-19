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
- `batch` remains read-only by default, but now has one guarded write path:
  exactly one `tests/**` write/edit plus one `src/mew/**` write/edit. Both are
  forced to dry-run previews, ordered test-before-source, and remain behind the
  existing approval boundary.
- In `--approval-mode accept-edits`, that paired write batch is approved as one
  group through the approve-all path: the test half defers verification and the
  source half runs the final verifier, with existing rollback behavior on
  failure.
- M2 comparative dogfood now records the mew-side session's `approval_mode` and
  default permission posture, so future comparison artifacts can tell whether a
  run used the low-friction mode.
- M2 comparative evidence now records `paired_write_batch` from real work
  session model turns, so a session that used a guarded paired write batch can
  carry that fact into the fresh-CLI comparison artifact.

## Validation

```bash
uv run ruff check src/mew/commands.py src/mew/dogfood.py tests/test_work_session.py tests/test_dogfood.py
git diff --check
uv run pytest --no-testmon -q \
  tests/test_work_session.py::WorkSessionTests::test_work_live_accept_edits_mode_auto_applies_dry_run_write \
  tests/test_work_session.py::WorkSessionTests::test_work_json_accept_edits_mode_keeps_stdout_parseable \
  tests/test_work_session.py::WorkSessionTests::test_work_ai_batch_previews_paired_source_and_test_writes \
  tests/test_work_session.py::WorkSessionTests::test_accept_edits_auto_approves_paired_write_batch_with_group_verification \
  tests/test_dogfood.py::DogfoodTests::test_run_dogfood_work_session_scenario
./mew dogfood --scenario work-session --workspace /tmp/mew-accept-edits-work-session-dogfood --json
./mew dogfood --scenario work-session --workspace /tmp/mew-paired-write-batch-dogfood --json
./mew dogfood --scenario m2-comparative \
  --workspace /tmp/mew-m2-approval-mode-evidence \
  --mew-session-id 250 \
  --json
./mew dogfood --scenario m2-comparative \
  --workspace /tmp/mew-m2-paired-batch-evidence \
  --mew-session-id 251 \
  --json
./mew dogfood --scenario m2-comparative \
  --workspace /tmp/mew-m2-paired-batch-combined \
  --mew-session-id 251 \
  --m2-comparison-report /tmp/mew-fresh-paired-batch-report.json \
  --json
```

Observed:

- focused pytest: `3 passed`
- dogfood: `pass`
- dogfood check added: `work_ai_accept_edits_auto_applies_preview`
- dogfood check added after real test-first failure:
  `work_ai_accept_edits_defers_paired_test_first_verification`
- dogfood check added for the paired write batch:
  `work_ai_accept_edits_auto_approves_paired_write_batch`
- `/tmp/mew-paired-write-batch-dogfood` passed and confirms a source/test batch
  is previewed test-first, auto-approved as one guarded group under
  `accept-edits`, defers the test verification, and runs the final source-side
  verifier successfully.
- Real mew dogfood task `#260` used the new paired write batch in work session
  `#251`: step `#3` emitted one batch containing the `tests/test_dogfood.py`
  and `src/mew/dogfood.py` edits, `accept-edits` auto-approved both previews,
  full pytest passed, and the focused M2 comparative test passed.
- `/tmp/mew-m2-paired-batch-evidence/.mew/dogfood/m2-comparative-protocol.json`
  records `paired_write_batch.status: proved`, `tool_call_ids: [1530, 1531]`,
  `applied_count: 2`, and `forced_preview: true` for session `#251`.
- `/tmp/mew-m2-paired-batch-combined/.mew/dogfood/m2-comparative-protocol.md`
  merges a fresh `codex-ultra` implementation report for the same paired-batch
  evidence feature. The mew leg proves `paired_write_batch`, but the fresh leg
  still records `resident_preference.choice: fresh_cli` for this narrow
  write-heavy edit/test loop.
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

The real dogfood task exposed a remaining M2 gap: test-first edits could run
verification before the source-side companion edit landed when the model emitted
a normal dry-run preview under a paired-test steer. The follow-up fix marks
paired-test-steer previews with `defer_verify_on_approval`, so
`accept-edits` can auto-apply the test half without running the verifier until
the source edit lands.

The next slice adds the stronger M2 lever without opening arbitrary writable
batching. When the resident already knows both exact edits, it can emit one
paired write batch and avoid the test-steer round trip. Safety stays narrow:
mixed read/write batches and unpaired writes are rejected, both writes are
preview-only, and application still flows through approval / approve-all.
The M2 comparative artifact now preserves whether this path was used, which
makes the next fresh-CLI comparison less hand-wavy.

The paired-batch comparison did not move this narrow task to mew-preferred. It
does reduce mew's approval ceremony, but direct fresh CLI remains lower overhead
for compact local edit/test work that does not need resident memory.

Next M2 evidence should use an interruption-shaped paired source/test task:
pause or stop the mew resident mid-change, resume without user rebrief, finish
verification, and compare that against an interrupted fresh CLI leg. That is the
task shape where mew's persistent body should have a real chance to win.
