# Recommendation

Choose one bounded slice: **shrink the tiny write-ready draft prompt contract (`v2`)**.

Do this before lane-observability-only work or any blocker/recovery follow-up.

# Why This Slice

- `e474b6a` fixed stale tiny-surface contamination, but the latest live rerun still shows timeout dominance.
- The newest fact is decisive: turn `1823` timed out in the tiny lane itself (`tiny_write_ready_draft_* = timeout`, `patch_draft_compiler_ran = false`).
- That makes another measurement-only slice lower value. We already know the tiny call is still too heavy at roughly `18040` chars.
- Blocker-stop handling is not the limiting issue. It already fired once; timeouts are still the dominant failure mode.

# Exact Bounded Change

Touch only `src/mew/work_loop.py` and `tests/test_work_session.py`.

Implement **tiny prompt contract `v2`** with these rules:

- In `build_write_ready_tiny_draft_model_context()`, keep only:
  - `active_work_todo.source.plan_item`
  - `active_work_todo.source.target_paths`
  - `write_ready_fast_path.cached_window_texts[].path`
  - `write_ready_fast_path.cached_window_texts[].text`
  - `allowed_roots.write`
- Remove from the tiny context:
  - `active_work_todo.id`
  - `active_work_todo.status`
  - `active_work_todo.attempts`
  - `active_work_todo.blocker`
  - `source.verify_command`
  - `focused_verify_command`
  - cached-window `line_start`
  - cached-window `line_end`
  - cached-window `tool_call_id`
  - cached-window `window_sha256`
  - cached-window `file_sha256`
- In `build_work_write_ready_tiny_draft_prompt()`, serialize the tiny context compactly instead of pretty-printing it.
- Bump `WORK_WRITE_READY_TINY_DRAFT_PROMPT_CONTRACT_VERSION` to `v2`.
- Keep compiler/replay behavior unchanged. This slice is only about making the tiny draft request smaller.

# Why Not The Other Options

- `lane-specific timeout/elapsed observability`: useful, but not next. The latest live turn already attributes at least one dominant failure directly to the tiny lane.
- `blocker-stop handling`: already landed enough to prove the path; it is not the dominant live failure.
- `broader recovery or follow-status work`: outside the tightest Phase 0-4 follow-up and unnecessary until the tiny call stops timing out so often.

# Acceptance Criteria

1. `tiny_write_ready_draft_prompt_contract_version` reports `v2`.
2. Tiny prompt tests prove the removed fields no longer appear in the prompt/context.
3. On the same `#402`-shape live rerun, `tiny_write_ready_draft_prompt_chars` drops materially from the current ~`18040` baseline.
4. No command-path, blocker semantics, replay format, or non-write-ready behavior changes in this slice.

# Immediate Follow-Through

After landing, rerun the same `#402` collection and check only two things:

- whether tiny-lane timeout incidence falls from the current dominant share
- whether `patch_draft_compiler_ran=true` appears more often than the current `1/6`

If both stay flat after this shrink, the next slice should be timeout/elapsed attribution, not more prompt trimming.
