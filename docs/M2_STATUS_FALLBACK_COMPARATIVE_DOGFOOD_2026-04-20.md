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
- comparator caveat: this proves a fresh CLI **same-session resume**, not a
  true fresh CLI restart from no prior agent context

Verification:

- `uv run pytest -q tests/test_dogfood.py -k m2_comparative`
- `git diff --check`

Evidence:

- `interruption_resume_gate.fresh_cli.status: proved`
- `manual_rebrief_needed: false`
- `context_mode: same_session_resume`
- `restart_comparator_status: not_proved`

## Combined Result

Combined protocol:

- JSON:
  `/tmp/mew-m2-status-fallback-combined-gate/.mew/dogfood/m2-comparative-protocol.json`
- Markdown:
  `/tmp/mew-m2-status-fallback-combined-gate/.mew/dogfood/m2-comparative-protocol.md`

Result:

- `comparison_result.status: fresh_cli_preferred`
- `resident_preference.choice: fresh_cli`
- top-level interruption gate: `proved`
- mew interruption gate: `proved`
- fresh interruption gate: `proved`

Follow-up protocol fix:

- `interruption_resume_gate.status` is now derived from child gate statuses
  when both sides are known.
- If either side is still `unknown`, the top-level gate remains `unknown`.
- Explicit non-unknown top-level gate status is preserved.

## Interpretation

This is stronger evidence than the earlier interruption comparisons because
both sides exercised an interruption/resume path. mew did preserve the resident
state and complete the task without rebriefing; that part of M2 is real.

It still does not close M2. For this compact edit/test task, the fresh CLI
same-session resume flow remained preferable, but that is not the same as the
M2 Done-when comparator: "restart in a fresh coding CLI." Future M2 comparison
reports now need to record `context_mode`, `session_resumed`,
`handoff_note_used`, and `restart_comparator_status` so mew does not mistake a
resumed external agent session for true fresh restart evidence. The next M2
work should either run that true restart leg or reduce the remaining
cockpit/approval ceremony enough that an interrupted resident would choose to
stay in mew.
