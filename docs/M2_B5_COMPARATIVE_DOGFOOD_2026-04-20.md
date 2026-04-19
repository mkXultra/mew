# M2 B5 Comparative Dogfood - 2026-04-20

Purpose: verify the B5 paired-test discovery fix in a real coding task and compare the resulting mew run with a fresh CLI run.

Base commit: `95a540e Dogfood paired test discovery`

## Task

Add a new M2 comparative task shape named `test_discovery`.

Required surfaces:

- `src/mew/dogfood.py`
- `tests/test_dogfood.py`

This task intentionally touches the same kind of surface that previously failed: a source edit whose natural existing test owner is `tests/test_dogfood.py`, not a convention-only `tests/test_cli.py`.

## Mew Leg

Workspace: `/tmp/mew-m2-b5-mew`

Result: completed.

Evidence:

- work session: `#1`
- model turns: `7`
- tool calls: `12`
- elapsed: `wall=117s`, `active=94s`
- approvals: `1 applied`, `0 rejected`, `0 failed`
- continuity: `9/9 strong`
- verification: `uv run python -m unittest tests.test_dogfood` passed
- focused verification also passed through the approved source edit path: `uv run pytest -q tests/test_dogfood.py -k m2_task_shape`

B5-specific observation:

- The resident first attempted the source edit.
- The paired-test steer suggested the existing test path `tests/test_dogfood.py`.
- It did not steer to nonexistent `tests/test_cli.py`.
- The test edit was applied with deferred verification, then the source edit landed, then broad verification passed.

Mew-side interruption gate:

- `not_proved`
- Reason: this run did not include an actual interruption or recovery-risk point.
- Resume quality itself was strong, but the required interruption evidence was absent.

## Fresh CLI Leg

Workspace: `/tmp/mew-m2-b5-fresh`

Runner: `codex-ultra` through `acm run`

Result: completed.

Evidence:

- changed `src/mew/dogfood.py`
- changed `tests/test_dogfood.py`
- wrote `/tmp/mew-m2-b5-fresh/fresh-cli-report.json`
- verification passed:
  - `uv run pytest -q tests/test_dogfood.py -k m2_task_shape`
  - `uv run python -m unittest tests.test_dogfood`

Fresh-side report judged:

- `status`: `fresh_cli_preferred`
- Reason: the task was narrow, non-interrupted, and direct file inspection/edit/verification had less ceremony.
- Fresh-side interruption gate: `not_proved`, because no interruption was simulated.

## Combined Result

Generated combined protocol:

- JSON: `/tmp/mew-m2-b5-combined/.mew/dogfood/m2-comparative-protocol.json`
- Markdown: `/tmp/mew-m2-b5-combined/.mew/dogfood/m2-comparative-protocol.md`

Combined status:

- `fresh_cli_preferred`

Interpretation:

- B5 is fixed for the observed failure mode. mew now steers existing test ownership correctly for this class of task.
- For a small non-interrupted coding task, fresh CLI still feels better because it has less workflow overhead.
- This does not test mew's intended advantage: interruption-resume and durable resident continuity.

## Decision

Keep B5 as done.

Do not spend more cycles on the `tests/test_cli.py` blocker unless it reappears.

Next M2 dogfood should be a true interruption-shaped paired task:

1. Start mew on a small paired source/test change.
2. Interrupt after partial progress or pending approval.
3. Resume from `mew work <task-id> --session --resume --allow-read .`.
4. Require passing verification after resume.
5. Compare with a fresh CLI run that is also interrupted or honestly marked `not_proved`.

If mew still loses on the next interrupted run, the likely next blocker is not B5. It is either:

- paired source/test approval ceremony, or
- direct cockpit latency / Streaming Tool Executor.
