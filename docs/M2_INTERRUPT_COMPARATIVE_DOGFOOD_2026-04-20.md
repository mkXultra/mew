# M2 Interruption Comparative Dogfood - 2026-04-20

Purpose: test the M2 interruption-resume gate after the B5 paired-test discovery fix, using a real mew work session with preserved recovery risk and a matching fresh CLI run.

Base commit: `0173a82 Record B5 comparative dogfood`

## Task

Add a new M2 comparative task shape named `approval_pairing`.

Required surfaces:

- `src/mew/dogfood.py`
- `tests/test_dogfood.py`

This task intentionally exercises the paired source/test approval flow again, but with an explicit failed observation preserved before the resident starts.

## Mew Leg

Workspace: `/tmp/mew-m2-interrupt-mew`

Result: completed.

Setup:

- created work session `#1`
- injected a failed read of `tests/missing_m2_resume_hint.py` before the resident run
- kept the failure in session history as the recovery-risk point

Evidence:

- work session: `#1`
- model turns: `8`
- tool calls: `15`
- elapsed: `wall=135s`, `active=99s`
- approvals: `1 applied`, `0 rejected`, `0 failed`
- continuity: `9/9 strong`
- verification:
  - `uv run pytest -q tests/test_dogfood.py -k m2_task_shape` passed
  - `uv run python -m unittest tests.test_dogfood` passed

Mew-side behavior:

- The first resident step explicitly recovered from the failed stale file read by inspecting `tests/`.
- The paired-test steer suggested the existing test path `tests/test_dogfood.py`.
- The test edit was applied with deferred verification.
- The matching source edit then landed and verification passed.
- The closed resume bundle preserved the failure, runnable next action, world state, verification confidence, and final working memory.

Mew-side interruption gate:

- `proved`
- `changed_or_pending_work`: true
- `risk_or_interruption_preserved`: true
- `runnable_next_action`: true
- `continuity_usable`: true
- `verification_after_resume_candidate`: true

Limit:

- This was a controlled failed-tool recovery, not an OS/process-level kill or Ctrl-C interruption.

## Fresh CLI Leg

Workspace: `/tmp/mew-m2-interrupt-fresh`

Runner: `codex-ultra` through `acm run`

Result: completed.

Evidence:

- changed `src/mew/dogfood.py`
- changed `tests/test_dogfood.py`
- wrote `/tmp/mew-m2-interrupt-fresh/fresh-cli-report.json`
- verification passed:
  - `uv run pytest -q tests/test_dogfood.py -k m2_task_shape`
  - `uv run pytest -q tests/test_dogfood.py -k m2_comparative`

Fresh-side report judged:

- `status`: `completed`
- `preference_signal`: `inconclusive`
- `interruption_resume_gate`: `unknown`
- Reason: the fresh run completed the narrow task, but did not exercise an interruption-resume trial.

## Combined Result

Generated combined protocol:

- JSON: `/tmp/mew-m2-interrupt-combined-v2/.mew/dogfood/m2-comparative-protocol.json`
- Markdown: `/tmp/mew-m2-interrupt-combined-v2/.mew/dogfood/m2-comparative-protocol.md`

Combined status:

- `inconclusive`

Important protocol facts:

- mew interruption gate: `proved`
- fresh CLI interruption gate: `unknown`
- resident preference: `inconclusive`

## Implementation Follow-Up

The fresh CLI report initially used a natural flat shape:

- `task_summary`
- `verification`
- `friction_summary`
- `preference_signal`
- top-level `interruption_resume_gate`

The original merge path only understood the nested `fresh_cli` shape, so the combined protocol failed to fill the fresh summary. `mew dogfood --scenario m2-comparative` now accepts the flat report shape too.

## Decision

Record this as the first M2 comparative run where the mew-side interruption-resume gate is proved.

Do not close M2 from this alone. The comparison remains inconclusive because the fresh side did not undergo a matching interruption and because mew still carries more approval/workflow ceremony than a mature coding CLI.

Next useful M2 work should be one of:

1. Run a stricter interruption comparison with an actual process stop or Ctrl-C boundary.
2. Reduce measured cockpit latency / perceived idle ratio.
3. Reduce paired approval ceremony without weakening source/test safety.
