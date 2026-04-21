# REVIEW: M6.11 Phase 0 (Spark) – Draft-state observability slice

## Findings

No findings remain in the reviewed scope (`src/mew/work_loop.py`, `src/mew/work_session.py`, `src/mew/commands.py`, `tests/test_work_session.py`, `docs/REVIEW_2026-04-22_M6_11_PHASE0_SPARK_IMPL.md`).

## Prior Findings Status

1. Resolved: `draft_runtime_mode` now matches the real execution path.
   - `_write_ready_draft_runtime_mode()` reports `"streaming"` for streaming turns and `"guarded"` or `"fallback_unguarded"` for non-streaming turns based on timeout-guard availability in [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:666).
   - `plan_work_model_turn()` records that value into write-ready draft metrics in [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:2006).
   - Regression coverage now asserts the corrected helper contract in [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:6804).

2. Resolved: follow-status no longer fabricates draft placeholders for non-draft failures.
   - `_latest_failed_model_turn()` now only copies draft-specific metrics when `write_ready_fast_path` is true in [src/mew/commands.py](/Users/mk/dev/personal-pj/mew/src/mew/commands.py:6569).
   - The formatter still renders draft fields when present, but the non-draft path no longer injects `draft_retry_same_prefix=False` or related placeholders in [src/mew/commands.py](/Users/mk/dev/personal-pj/mew/src/mew/commands.py:6809).
   - Regression coverage now exercises a non-draft failed turn and asserts the draft placeholders stay absent in [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:21689).

3. Resolved: `cached_window_hashes` now uses the same contract on both surfaces.
   - Model-turn metrics hash `path|line_start|line_end|text` in `_write_ready_draft_window_signature()` at [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:648).
   - Resume fallback hashes the same fields in `_cached_window_signature()` at [src/mew/work_session.py](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:4309).
   - Regression coverage now checks helper-level equality across both implementations in [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:6813).

## Residual Risks / Test Gaps

- No end-to-end test currently drives a real streaming write-ready planning turn and then verifies that `draft_runtime_mode=streaming` survives through persisted model-turn or follow-status surfaces; current coverage validates the helper contract directly.
- No test currently drives `build_work_session_resume()` through the `plan_item_observations[0].edit_ready` fallback path and asserts the emitted fallback `cached_window_hashes`; current resume coverage is based on draft metrics already present on model turns.

## Validation

- `uv run python3 -m py_compile src/mew/work_loop.py src/mew/work_session.py src/mew/commands.py tests/test_work_session.py`
- `uv run ruff check src/mew/work_loop.py src/mew/work_session.py src/mew/commands.py tests/test_work_session.py`
- `uv run python -m pytest -q tests/test_work_session.py -k "write_ready_fast_path or draft_runtime_mode_contract or draft_window_hash_contract_is_stable_between_model_turns_and_resume_fallback or build_work_session_resume_surfaces_draft_placeholders or work_follow_status"` -> `23 passed, 419 deselected in 2.29s`
