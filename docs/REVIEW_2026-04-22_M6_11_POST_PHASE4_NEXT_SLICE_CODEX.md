# M6.11 Post-Phase4 Next Slice — Codex (2026-04-22)

## Context

- Current `HEAD` is `8f48189`.
- `./mew work 402 --session --resume --allow-read . --json` is now correct on the active session: `phase=blocked_on_patch`, populated `active_work_todo.blocker`, populated `recovery_plan`, and `continuity=9/9`.
- `./mew work 402 --follow-status --json` is still stale because it is anchored to `.mew/follow/session-392.json`, which was written under older code (`current_git.head=5085ff0` inside the snapshot).
- That snapshot is internally contradictory:
  - `last_step.model_turn.id=1829` is the clean blocker turn.
  - `last_step.model_turn.model_metrics.tiny_write_ready_draft_outcome=blocker`.
  - `last_step.model_turn.model_metrics.patch_draft_compiler_artifact_kind=patch_blocker`.
  - but `resume.phase=drafting`, `resume.active_work_todo.status=drafting`, `resume.active_work_todo.blocker={}`, and `suggested_recovery={}`.
- Calibration still fails after the bridge:
  - `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json`
  - `total_bundles=14`
  - `dominant_bundle_type=work-loop-model-failure.request_timed_out`
  - `dominant_bundle_share=0.5714285714285714`

## Recommended Next Slice

**Slice:** make `work --follow-status` prefer a fresh current-session resume over a stale snapshot resume, even when `session_updated_at` ties.

This is a bounded Phase 4 completion slice for the operator surface, not another drafting/runtime slice.

### Exact behavior

When `mew work --follow-status` loads a snapshot and can also find the referenced session in local state:

1. Build a fresh `current_resume = build_work_session_resume(session, task=..., state=...)` using current `HEAD`.
2. Compare that against `snapshot_resume = snapshot_data["resume"]`.
3. If the current resume is structurally richer, use it as the effective resume for follow-status output even if `session_updated_at` is unchanged.

Treat the current resume as richer when any of these are true:

- `current_resume["phase"] == "blocked_on_patch"` and snapshot phase is still `drafting` or `idle`
- current `active_work_todo.blocker` is populated and snapshot blocker is empty
- current `recovery_plan.items` is non-empty and snapshot recovery plan is empty
- current continuity score is higher than snapshot continuity score
- current pending approvals differ from snapshot pending approvals

Use that effective resume for:

- `phase`
- `next_action`
- `verification_coverage_warning`
- `verification_confidence`
- `continuity`
- `pending_approval_count`
- `suggested_recovery`

Keep snapshot-owned metadata unchanged:

- `snapshot_path`
- `heartbeat_at`
- `producer_*`
- `stop_reason`
- `latest_context_checkpoint`
- `current_git`

Add a small debug field such as `resume_source: "snapshot"` or `"session_overlay"` so the user can tell which path won.

## Why This Slice Is Best

1. It finishes the Phase 4 bridge on the main operator surface. The substrate now records a clean blocker/recovery path; `follow-status` is the remaining stale surface.
2. It is narrower than another runtime or calibration change. The drafting lane, blocker persistence, and replay bundles already exist; this slice is only about selecting the right resume source at read time.
3. It fixes the exact user-visible contradiction without requiring a new live rerun. The current session already contains enough state for `blocked_on_patch`; `follow-status` is simply not preferring it.
4. It makes the next calibration decision more honest. Until `follow-status` shows the post-bridge blocker state instead of the pre-bridge snapshot resume, operators cannot cleanly distinguish “historical timeout” from “current blocker with recovery path.”

### Why not the alternatives

- Not another timeout-reduction slice yet: the calibration gate is still red, but optimizing timeout concentration before the operator surface reports the new blocker state will hide whether the bridge is actually working.
- Not a snapshot-writer-only fix: the current stale snapshot was produced on older code. A writer-only change would help future runs but would not solve the present post-commit mismatch that `follow-status` must handle.
- Not blocker-taxonomy expansion: mapping `insufficient_cached_context` more precisely is useful later, but it does not solve the stale follow-status surface.

## Files To Change

- `src/mew/commands.py`
  - `_work_follow_status_from_snapshot(...)`
  - `work_follow_status_suggested_recovery(...)`
  - add one small pure helper to choose `effective_resume` and `resume_source`
- `tests/test_work_session.py`
  - add follow-status regressions for tied timestamps and current-session overlay

No `src/mew/work_session.py` change is required for this slice. The resume builder is already producing the correct `blocked_on_patch` state.

## Focused Tests

- Add `test_work_follow_status_prefers_current_resume_over_snapshot_when_timestamps_tie`
  - snapshot resume says `drafting`
  - current session resume derives `blocked_on_patch`
  - assert JSON output uses `phase=blocked_on_patch` and `resume_source=session_overlay`

- Add `test_work_follow_status_overlay_enables_recovery_for_clean_blocker`
  - snapshot has empty recovery data
  - current resume has blocker-backed `recovery_plan`
  - assert `suggested_recovery.kind == "needs_human_review"` and command points at `work 402 --session --resume --allow-read . --auto-recover-safe`

- Add `test_work_follow_status_overlay_uses_current_continuity_when_stronger`
  - snapshot continuity `8/9`
  - current resume continuity `9/9`
  - assert follow-status returns `9/9`

- Adjust the existing follow-status “session state newer” coverage only if needed
  - keep the old timestamp-based path
  - add the new equal-timestamp richer-resume path as a separate assertion, not a replacement

## Risks

- Overlay can hide historical snapshot defects if the source is not explicit. Mitigation: emit `resume_source` and keep snapshot metadata unchanged.
- If the overlay rules are too aggressive, follow-status could mask a genuinely useful snapshot-only state. Mitigation: only overlay when the current resume is strictly richer on blocker/recovery/continuity signals.
- Pending-approval counts must come from the same effective resume source or the JSON becomes internally inconsistent.

## Non-goals

- Do not change replay calibration thresholds or bundle bucketing in this slice.
- Do not change tiny-lane prompting, compiler behavior, or blocker taxonomy.
- Do not reinterpret `latest_model_failure` semantics in this slice. It can remain historical; the blocker/recovery resume becomes the authoritative current state.
- Do not add new persistent task/session fields. This is a read-path selection fix.

## Success Criteria

After this slice lands, with the current `#402` evidence still on disk:

1. `./mew work 402 --follow-status --json` reports `phase=blocked_on_patch`.
2. `suggested_recovery` is populated from the current blocker-backed recovery plan.
3. `continuity.score` matches the current resume (`9/9`).
4. The payload makes clear that the richer state came from the current session, not the older snapshot.

If those four conditions hold, the Phase 4 bridge is visible on both resume surfaces, and the next slice can return to calibration/timeout concentration with cleaner operator evidence.
