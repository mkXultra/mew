# Recommendation

Land one bounded "write-ready live bridge" slice next:

- in `src/mew/work_loop.py`, make the write-ready fast path ask for the tiny `patch_proposal | patch_blocker` contract instead of the generic tool-action schema
- in `src/mew/commands.py`, consume that write-ready patch result by calling `compile_patch_draft()` and then `compile_patch_draft_previews()`
- on validated `PatchDraft`, reuse the existing dry-run preview execution path so the resulting tool calls and pending approvals still look like normal `edit_file` / `edit_file_hunks` previews
- on `PatchBlocker` or compiler rejection, stop the step cleanly and record the artifact/replay outcome, but do not add Phase 4 recovery-plan behavior yet

# Why this is the next smallest safe slice

The offline pieces now exist:

- `compile_patch_draft()` validates proposal/blocker artifacts
- `compile_patch_draft_previews()` deterministically translates validated drafts into dry-run preview specs
- replay capture and calibration already cover compiler input/output artifacts

The smallest remaining live gap is therefore not recovery; it is the first runtime seam that produces and consumes `PatchDraft` / `PatchBlocker` at all. The design’s Phase 3 scope is exactly that seam: replace the write-ready fast-path prompt, route output through `PatchDraftCompiler`, and translate validated drafts into the existing dry-run preview flow. [`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`](/Users/mk/dev/personal-pj/mew/docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:821) [`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`](/Users/mk/dev/personal-pj/mew/docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:823) [`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`](/Users/mk/dev/personal-pj/mew/docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:940) [`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`](/Users/mk/dev/personal-pj/mew/docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:941)

This should come before any draft-time recovery work because:

- it proves the live patch lane on the narrowest write-ready surface
- it reuses the current dry-run approval/apply machinery rather than widening semantics
- Phase 4 recovery and follow-status should consume real live `PatchBlocker` / `PatchDraft` outcomes, not offline-only artifacts

# Exact files to touch

- `src/mew/work_loop.py`
  - replace `build_work_write_ready_think_prompt()` with the tiny patch contract for write-ready mode
  - add the narrow result normalization needed so write-ready model turns can return a patch artifact instead of a generic action batch
  - keep non-write-ready planning unchanged
- `src/mew/commands.py`
  - detect the new write-ready patch artifact result from `plan_work_model_turn()`
  - call `compile_patch_draft()` and then `compile_patch_draft_previews()`
  - on validated preview specs, feed them through the existing dry-run write execution path so approvals/tool calls remain the same shape as today
  - on `PatchBlocker` or compiler rejection, record the blocker/replay result and stop the step without emitting write tool calls

# Exact tests to touch

- `tests/test_work_session.py`
  - update the existing write-ready fast-path prompt assertions so they pin the patch contract instead of generic `edit_file` / `edit_file_hunks` instructions
  - add one end-to-end write-ready happy-path test where a model patch proposal compiles, translates, and produces the same pending dry-run approvals/tool calls the current preview flow uses
  - add one end-to-end blocker test where a model patch blocker stops the step without any write tool calls
  - add one end-to-end compiler-rejection test where an invalid patch proposal produces a compiler replay artifact and no write previews

`tests/test_patch_draft.py` should not need more changes for this bridge slice; the offline compiler and translator contracts are already pinned there.

# Acceptance criteria

1. When write-ready fast path is active, the write-ready prompt uses the tiny patch contract rather than asking for a generic tool batch.
2. A valid write-ready `patch_proposal` reaches `compile_patch_draft()` and `compile_patch_draft_previews()`, then results in the same dry-run `edit_file` / `edit_file_hunks` tool-call and pending-approval surfaces that the existing preview flow already exposes.
3. A write-ready `patch_blocker` or compiler-rejected proposal emits no write tool calls and no pending approvals.
4. Compiler input/output replay capture is written for the live bridge path.
5. No Phase 4 behavior is added in this slice:
   - no `build_work_recovery_plan()` changes
   - no `resume_draft_from_cached_windows`
   - no follow-status/resume UX expansion
   - no `write_tools.py` semantic changes

# Out of scope for this slice

- draft-time recovery routing
- `blocked_on_patch` follow-status/resume rendering work
- review-lane insertion
- approval/apply/verify semantics beyond reusing the current dry-run preview path
