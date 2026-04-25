# M6.11 Residual Close-Gate Audit (2026-04-25)

Recommendation: CLOSE_READY.

Auditor task: residual close-gate audit and roadmap-status input only. This
document does not modify source, tests, proof artifacts, or the canonical
M6.11 calibration ledger.

Current HEAD: `72dd8ba` (`Complete executor lifecycle overlays`).

## Scope

The original M6.11 core close gate is already recorded in
`docs/M6_11_CLOSE_GATE_AUDIT_2026-04-25.md`. This residual audit covers the
later hardening slices that were intentionally pulled forward before broad
M6.9 work resumed:

- Phase 5 isolated review lane.
- Phase 6 active `WorkTodo` executor lifecycle overlays.
- Read-only `MemoryExploreProvider` v0.
- Prompt/cache boundary observability.

## Residual Checklist

1. Phase 5 isolated review lane is landed and reviewed.

   Status: PASS.

   Evidence: commit `f69b94b` adds `review_patch_draft_previews()` before
   approval/apply. Accepted reviews preserve previews; rejected reviews return
   `review_rejected` with `revise_patch_from_review_findings`,
   `patch_draft_id`, review metadata, and findings. Task `#577` is recorded as
   product progress via supervisor rescue rather than mew-first autonomy
   credit.

2. Phase 6 executor lifecycle overlays are landed without replacing
   `WorkTodo.status`.

   Status: PASS.

   Evidence: commits `2e27c9f` and `72dd8ba` add
   `active_work_todo.executor_lifecycle` as an overlay. The recorder accepts
   `queued`, `executing`, `completed`, `cancelled`, and `yielded`. Producer
   paths record executing/completed/yielded/cancelled across non-batch tools,
   batch tools, model/tool failure replay, explicit stops, user interrupts,
   and `mew repair` stale-running-work recovery. `WorkTodo.status` and blocker
   fields remain the draft-domain source of truth.

3. Read-only memory exploration exists without adding a second planner.

   Status: PASS.

   Evidence: commit `d5513e8` adds the read-only
   `MemoryExploreProvider` v0. It feeds the existing explore handoff keys
   (`target_paths`, `cached_window_refs`, `candidate_edit_paths`,
   `exact_blockers`, and `memory_refs`) while rejecting traversal, tilde,
   drive-letter absolute, NUL, and private-memory paths from path-bearing
   fields. No autonomous memory planner, new CLI surface, write path, or prompt
   rewrite was added.

4. Prompt/cache boundary observability is exposed in resume.

   Status: PASS.

   Evidence: commit `df397ae` exposes `prompt_cache_boundary` from existing
   draft prompt contract/runtime/static/dynamic/retry metrics while preserving
   the flat resume fields and returning `{}` when no draft metrics exist.

5. Current validation remains green after the residual slices.

   Status: PASS.

   Evidence:

   - `./mew dogfood --all --json`: `status=pass`, generated at
     `2026-04-25T03:52:24Z`.
   - `uv run pytest -q tests/test_dogfood.py -k 'm6_11' --no-testmon`:
     `6 passed`.
   - `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --strict --json`:
     `ok=true`, `total_bundles=94`, `off_schema_rate=0.0`,
     `refusal_rate=0.0`, `malformed_relevant_bundle_count=0`.
   - For the final Phase 6 expansion: `uv run pytest -q
     tests/test_work_session.py --no-testmon` passed with `613` tests and `24`
     subtests; `uv run pytest -q tests/test_work_replay.py --no-testmon`
     passed with `24` tests and `4` subtests; ruff and `git diff --check`
     passed for touched files.

6. Reviewer approvals are recorded.

   Status: PASS.

   Evidence:

   - Phase 5 isolated review lane: codex-ultra approved the landed supervisor
     rescue slice in the residual evidence recorded in `ROADMAP_STATUS.md`.
   - `MemoryExploreProvider` v0: codex-ultra approved final static review
     session `019dc287-8591-7610-a0c7-135d5a52cc98`.
   - Prompt/cache boundary: codex-ultra approved session
     `019dc29c-2015-7432-b44e-06eca6f517a5`.
   - Phase 6 lifecycle expansion: codex-ultra approved session
     `019dc2b2-22d9-7cb0-b915-4d9f2b89df2b`.

7. Autonomy accounting is honest.

   Status: PASS_WITH_NOTE.

   Evidence: The residual phase contains mixed autonomy outcomes.
   `MemoryExploreProvider` counts as `success_after_substrate_fix` because mew
   owned the final implementation patch after the missing-target substrate
   repair. Phase 5, prompt/cache, and the final lifecycle expansion are product
   progress via supervisor rescue, not clean mew-first autonomy credit. This is
   acceptable because the residual gate is loop-substrate hardening and the
   purpose is to make later mew-first work more diagnosable.

## Closure Decision

M6.11 residual hardening is close-ready. The remaining action is bookkeeping:
mark M6.11 closed as a whole and return active focus to M6.9 Durable Coding
Intelligence from the clean proof-slice boundary.

Next M6.9 work should use the now-closed residual surfaces:

- use isolated patch review before apply/approval,
- inspect `active_work_todo.executor_lifecycle` before classifying loop
  failures,
- use read-only memory explore as a provider rather than a second planner,
- preserve prompt/cache boundary metrics in resume when diagnosing drift or
  repeated deliberation.
