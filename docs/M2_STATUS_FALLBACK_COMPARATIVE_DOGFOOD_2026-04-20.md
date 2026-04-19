# M2 Status Fallback Comparative Dogfood 2026-04-20

Purpose: run a true interruption-shaped comparison on both sides after the
paired-batch and accept-edits improvements, using a small source/test task that
also fixed the M2 comparative protocol.

## Task

Derive `comparison_result.status` from a merged report's
`resident_preference.choice` when no explicit comparison status, top-level
status, or top-level `preference_signal` is present.

Required surfaces:

- `src/mew/dogfood.py`
- `tests/test_dogfood.py`

## Mew Leg

Task: `#261`

Work session: `#252`

Shape:

- started with `mew work --live --approval-mode accept-edits`
- intentionally interrupted with Ctrl-C during step 1
- resumed with `mew work 261 --session --resume --allow-read .`
- continued without rebriefing the task from scratch
- emitted a guarded paired write batch for `tests/test_dogfood.py` and
  `src/mew/dogfood.py`
- auto-approved both previews under `accept-edits`
- ran focused and broader verification

Verification:

- `uv run pytest --no-testmon -q tests/test_dogfood.py -k m2_comparative`
- `uv run python -m unittest tests.test_dogfood`
- later supervisor validation: `uv run pytest --no-testmon -q tests/test_dogfood.py`

Evidence:

- `/tmp/mew-m2-status-fallback-combined/.mew/dogfood/m2-comparative-protocol.json`
- `interruption_resume_gate.mew.status: proved`
- `mew_run_evidence.paired_write_batch.status: proved`
- continuity: `9/9 strong`
- approvals: `2 applied`, `0 rejected`, `0 failed`

## Fresh CLI Leg

Runner: `codex-ultra` through `acm run`

Worktree: `/tmp/mew-fresh-status-fallback`

Shape:

- phase 1 intentionally inspected only and wrote
  `/tmp/mew-fresh-status-fallback-interrupt-note.md`
- phase 2 resumed the same codex session and completed implementation from the
  handoff note and prior context
- wrote `/tmp/mew-fresh-status-fallback-report.json`

Verification:

- `uv run pytest -q tests/test_dogfood.py -k m2_comparative`
- `git diff --check`

Evidence:

- `interruption_resume_gate.fresh_cli.status: proved`
- `manual_rebrief_needed: false`

## Combined Result

Combined protocol:

- JSON:
  `/tmp/mew-m2-status-fallback-combined/.mew/dogfood/m2-comparative-protocol.json`
- Markdown:
  `/tmp/mew-m2-status-fallback-combined/.mew/dogfood/m2-comparative-protocol.md`

Result:

- `comparison_result.status: fresh_cli_preferred`
- `resident_preference.choice: fresh_cli`
- mew interruption gate: `proved`
- fresh interruption gate: `proved`

## Interpretation

This is stronger evidence than the earlier interruption comparisons because
both sides exercised an interruption/resume path. mew did preserve the resident
state and complete the task without rebriefing; that part of M2 is real.

It still does not close M2. For this compact edit/test task, the fresh CLI
resume flow remained preferable. The next M2 work should reduce the remaining
cockpit/approval ceremony or improve the live coding loop enough that an
interrupted resident would choose to stay in mew rather than restart or resume
in a fresh coding CLI.
