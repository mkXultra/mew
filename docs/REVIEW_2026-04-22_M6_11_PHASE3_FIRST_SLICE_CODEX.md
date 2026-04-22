# Recommendation

Land a single Phase 3 "write-ready compiler bridge" slice first:

- for the existing write-ready fast path only, replace the generic write-batch THINK contract with the tiny `patch_proposal | patch_blocker` contract
- route that live write-ready result through `PatchDraftCompiler`
- on validated `PatchDraft`, translate the artifact into the existing dry-run `edit_file` / `edit_file_hunks` preview flow without changing approval/apply/verify or `write_tools.py`

# Why this should land first

This is the smallest safe live integration point left after Phase 2. The repo already has:

- `WorkTodo` and write-ready cached-window state in `src/mew/work_session.py`
- offline `PatchDraftCompiler` validation in `src/mew/patch_draft.py`
- compiler replay capture in `src/mew/work_replay.py`
- calibration/checkpoint coverage in `src/mew/proof_summary.py`

What is still missing is the first runtime consumer of that compiler. The design’s own Phase 3 scope is exactly this seam: replace the write-ready prompt, route output through the compiler, and reuse the existing dry-run preview path. [`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`](/Users/mk/dev/personal-pj/mew/docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:817) [`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`](/Users/mk/dev/personal-pj/mew/docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:823)

This slice should come before any Phase 4 recovery/follow-status work for three reasons:

- it proves the live patch lane end-to-end on the narrowest possible surface
- it reuses the current dry-run preview and approval flow, so it does not widen write semantics
- later work depends on real live `PatchDraft` / `PatchBlocker` outputs existing first; otherwise recovery, follow-status, and review are still wiring against offline-only artifacts

Prompt-only replacement should not land first by itself. Today the executor still expects normal work actions/tool batches, so swapping the prompt without the compiler bridge would strand live write-ready output in an unusable schema.

# Exact files to touch

- `src/mew/work_loop.py`
  - replace `build_work_write_ready_think_prompt()` with the tiny patch contract
  - add the narrow write-ready response normalization needed to distinguish `patch_proposal` / `patch_blocker` from the generic action schema
  - keep prompt metrics and write-ready detection intact
- `src/mew/commands.py`
  - add the first live callsite to `compile_patch_draft()`
  - on validated `PatchDraft`, translate `files[]` into the existing dry-run write preview path so pending approvals still work unchanged
  - on compiler result, write the existing compiler replay bundle via `write_patch_draft_compiler_replay()`
  - for this first slice, stop at "validated draft preview or exact blocker recorded"; do not pull in Phase 4 recovery-plan changes yet

# Exact tests to touch

- `tests/test_work_session.py`
  - replace the current write-ready prompt assertions around `build_work_write_ready_think_prompt()` with patch-contract assertions instead of generic `edit_file` / `edit_file_hunks` wording
  - add one end-to-end work-loop happy-path test where a write-ready model turn returns a valid `patch_proposal`, the compiler validates it, and the session ends with the same pending dry-run approvals the current flow already uses
  - add one end-to-end work-loop blocker test where a write-ready model turn returns a `patch_blocker` or compiler-rejected proposal and the session records the blocker/replay bundle without emitting any write tool batch
- `tests/test_work_replay.py`
  - add one integration-oriented assertion only if the live callsite needs new metadata in the compiler replay bundle; otherwise this file should stay untouched

# Boundaries

Keep this first slice out of:

- `build_work_recovery_plan()` and `resume_draft_from_cached_windows`
- `build_work_session_resume()` / `work --follow-status`
- Phase 5 review-lane insertion
- `write_tools.py` semantics

That keeps the first Phase 3 slice bounded to "live patch contract in, existing dry-run preview out," which is the smallest safe bridge from Phase 2 scaffolding to live drafting.
