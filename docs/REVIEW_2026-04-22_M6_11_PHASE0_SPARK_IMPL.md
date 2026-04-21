# REVIEW: M6.11 Phase 0 (Spark) – Draft-state observability slice

## What changed
- Added write-ready draft contract observability metrics in `src/mew/work_loop.py` under `plan_work_model_turn()` when write-ready fast-path is active:
  - `draft_phase`
  - `draft_attempts`
  - `cached_window_ref_count`
  - `cached_window_hashes`
  - `draft_runtime_mode`
  - `draft_prompt_contract_version`
  - `draft_prompt_static_chars`
  - `draft_prompt_dynamic_chars`
  - `draft_retry_same_prefix`
- Added session-level draft placeholders in `build_work_session_resume()` (`src/mew/work_session.py`) derived from latest write-ready model turn metrics or edit-ready plan observation fallback.
- Extended follow-status failure extraction/formatting in `src/mew/commands.py` to include draft metrics in `latest_model_failure` and `latest_model_failure_metrics`.
- Added focused regression coverage in `tests/test_work_session.py`:
  - write-ready planning model metrics include draft placeholders
  - session resume surfaces draft placeholders
  - follow-status JSON and text include draft failure metrics in #399/#401-style failure paths
- Addressed review findings with follow-up corrections:
  - corrected `draft_runtime_mode` semantics to reflect actual streaming/guarded/fallback behavior
  - suppress `draft_retry_same_prefix` output when no draft state exists on the failed model turn
  - aligned `cached_window_hashes` contract by including `path|line_start|line_end|text` in both model-turn and resume fallback signatures

## Validation run
- `uv run python3 -m py_compile src/mew/work_loop.py src/mew/work_session.py src/mew/commands.py tests/test_work_session.py`
- `uv run ruff check src/mew/work_loop.py src/mew/work_session.py src/mew/commands.py tests/test_work_session.py`
- `uv run python -m pytest -q tests/test_work_session.py -k "write_ready_fast_path or build_work_session_resume_surfaces_draft_placeholders or work_follow_status"`
- `git diff -- src/mew/work_loop.py src/mew/work_session.py src/mew/commands.py tests/test_work_session.py docs/REVIEW_2026-04-22_M6_11_PHASE0_SPARK_IMPL.md`

## Limitations
- `Plan 0` intentionally avoids introducing durable WorkTodo state and no compiler artifacts; observability is placeholder-only and inferred from latest write-ready model turn data.
- `draft_retry_same_prefix` remains a placeholder (`False` when present) because full prefix-retry detection is not part of Phase 0.
