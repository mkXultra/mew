# Refusal Separation Review

## Findings

No blocking findings in the current uncommitted slice.

## Notes

- The refusal handling in [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1622) now cleanly returns a tiny-draft `blocker` result for refusal exceptions, with the expected `model_returned_refusal` code and `model_exception_refusal` exit stage.
- The dogfood proof shape is now materially better. In [src/mew/dogfood.py](/Users/mk/dev/personal-pj/mew/src/mew/dogfood.py:999) the scenario explicitly removes any fixture-provided `active_work_todo` before writing state, so resume/follow have to reconstruct `blocked_on_patch`, `model_returned_refusal`, and `inspect_refusal` from the persisted refusal turn in [tests/fixtures/work_loop/recovery/402_tiny_draft_refusal/scenario.json](/Users/mk/dev/personal-pj/mew/tests/fixtures/work_loop/recovery/402_tiny_draft_refusal/scenario.json:57). That addresses the earlier proof gap.
- The remaining fixture copy still includes a pre-seeded `active_work_todo` at [tests/fixtures/work_loop/recovery/402_tiny_draft_refusal/scenario.json](/Users/mk/dev/personal-pj/mew/tests/fixtures/work_loop/recovery/402_tiny_draft_refusal/scenario.json:116), but the scenario strips it before observation, so this is a readability nit rather than a behavioral risk.
- Focused verification passed:
  - `uv run pytest -q tests/test_work_session.py -k 'tiny_write_ready_draft_lane_refusal_exception_becomes_blocker'`
  - `uv run pytest -q tests/test_dogfood.py -k 'm6_11_refusal_separation'`

approve
