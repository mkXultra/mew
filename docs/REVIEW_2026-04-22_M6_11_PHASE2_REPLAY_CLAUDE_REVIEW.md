# M6.11 Phase 2 — Replay-Bundle Persistence (Claude Review)

Scope: `src/mew/work_replay.py` (new), `src/mew/commands.py` (failure-path hook), `tests/test_work_session.py` (seven tests).

## Verdict

**Acceptable for this slice.** All four prior blockers — side-effect mutation, path non-determinism, capture errors suppressing the failure save, and `todo-none` collisions — have been addressed, and the missing tests (refusal, negative path, attempt increment, read-only invariance, and write-failure isolation) have all landed. Remaining notes are minor and belong in residual risks, not as gating findings.

## Findings

1. **Prior Finding 1 (side-effect) — resolved.** `write_work_model_failure_replay` now deepcopies the session before handing it to `_build_resume_context`, which is the only path that calls the mutating `build_work_session_resume` → `_observe_active_work_todo` chain (`src/mew/work_replay.py:146-147`). `test_replay_capture_is_read_only_for_session_frontier_state` takes `deepcopy(session)` before capture and asserts equality after, so regressions on `active_work_todo` / `last_work_todo_ordinal` would fail the test.

2. **Prior Finding 2 (path non-determinism) — resolved.** `date_bucket` is now derived from `model_turn["finished_at"]` (falling back to `started_at`, then wall clock) via `_date_bucket_from_model_turn` (`work_replay.py:32-39`), and the path now includes `turn-{turn_id}` (`work_replay.py:141`). `_next_attempt` still scans the filesystem, but that is now scoped under the stable `turn-<id>/` directory, so retries of the same turn cluster together as `attempt-1`, `attempt-2`, …. `test_replay_bundle_path_is_stable_and_attempt_increments` pins the shape across two writes.

3. **Prior Finding 3 (capture errors suppress save) — resolved.** The call in `src/mew/commands.py:4112-4121` is now wrapped in `try/except Exception: pass`, so `save_state(state)` always runs. `test_replay_bundle_write_failure_does_not_block_turn_persistence` forces a `RuntimeError` from the capture and asserts the turn still persists with `status="failed"` and no `replay_bundle_path`.

4. **Prior Finding 4 (`todo-none` collision) — resolved.** `_todo_dir_name` now returns `f"no-todo-{session_id}"` when there is no active todo (`work_replay.py:95-102`), and because the path also keys on `turn-{turn_id}`, two independent non-todo failures on the same session no longer share an attempt counter.

5. **Prior Finding 5 (duplicate `model_metrics` / `draft_metrics`) — resolved.** The two fields are now semantically distinct: `model_metrics` is the full turn metrics (`dict(model_turn["model_metrics"])`, `work_replay.py:170`), while `draft_metrics` is a named subset assembled from the read-only resume context (`work_replay.py:171-181`).

6. **Prior Finding 6 (missing tests) — resolved.** Six new tests cover refusal classification (`ModelRefusalError` and `CodexRefusalError` both asserted), the no-bundle negative path (also asserts `.mew/replays/work-loop` directory is not created), attempt-N increment, read-only invariance on the live session, and write-failure isolation. Together with the timeout and generic cases from the first slice, the behavioral surface is well pinned.

No new blocker-level findings.

## Residual risks

- **Silent capture-failure.** The `except Exception: pass` in `commands.py:4120-4121` swallows all capture errors without logging. That was the right tradeoff for this slice (observability must never block the main loop), but it means a disk-full, permissions, or schema regression will produce invisible gaps in replay coverage. Before a downstream consumer of bundles lands, some form of gap signal (log, metric, or a turn-level `replay_bundle_error` note) will be needed.
- **`_failure_profile` timeout branch is redundant.** The `isinstance(exc, ModelBackendError)` guard at `work_replay.py:75` is subsumed by the generic `"timed out" in message.lower()` branch immediately below it (`:81`); both return the same profile. Purely cosmetic, no behavior change, fine to leave.
- **`REPLAYS_ROOT` is hardcoded to `Path(".mew/replays/work-loop")`** rather than derived from `config.STATE_DIR` (`work_replay.py:10`). Functionally equivalent today because `STATE_DIR = Path(".mew")`, but if `STATE_DIR` is ever reconfigured, replays won't follow. Worth aligning when touching this module next.
- **Shallow copy of `model_metrics` into the bundle** (`work_replay.py:170`). Serialization happens immediately via `json.dumps`, so nested aliasing is not observable in practice; only matters if a future caller holds the bundle dict in memory alongside the live turn.
- **Failure taxonomy is narrow by design.** `WORK_TODO_PHASE_STATUSES = {"drafting", "blocked_on_patch"}` plus `write_ready_fast_path` is the right trigger for "pre-PatchDraftCompiler draft failure," but `awaiting_review`, `applying`, and `verifying` failures will fall off the replay surface. Intentional for this slice; revisit when PatchDraftCompiler lands.

## Recommended next step

Land the slice. When starting the PatchDraftCompiler replay work, address the silent-capture risk first — wire a minimal log or a `replay_bundle_error` field on the failed turn so gap detection is possible before anything starts consuming bundles offline.
