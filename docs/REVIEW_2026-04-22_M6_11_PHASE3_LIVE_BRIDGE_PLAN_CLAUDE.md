# M6.11 Phase 3 — Next Slice Planning Note: Shadow Live-Bridge (Claude)

Planning only. Identifies the smallest safe live slice given that the `compile_patch_draft_previews` translator just landed and `compile_patch_draft`, the compiler replay writer, and the Phase 2/3 calibration checkpoint are all already wired offline.

## Recommendation

**Land a shadow-mode live-bridge slice next: invoke `compile_patch_draft` (and, on validated output, `compile_patch_draft_previews`) alongside the existing write-ready fast path, capture a replay bundle every time, and attach the compiler's observation to the turn record — but do not change dispatch, recovery, approval, or the prompt.** Pure instrumentation: one new helper in `src/mew/work_loop.py`, one call-site addition in `plan_work_model_turn()`, new keys on `model_metrics`, no changes in `src/mew/commands.py` or `write_tools.py`. This is the first slice that consumes `PatchDraft` / `PatchBlocker` from a live turn while meeting the user's "stop at recorded" constraint.

## Why shadow mode before authoritative dispatch

The Phase 3 design (`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:817-834`) has three sub-tasks after the translator:

1. Route live write-ready output through `compile_patch_draft`.
2. Swap the write-ready prompt to the tiny patch contract.
3. Flip the write-ready fast path to *use* the compiler's preview specs for dispatch.

Shadow-mode invocation is the narrowest possible version of (1) and deliberately excludes (2) and (3):

- **(2) cannot land first.** The prompt swap changes what the model is asked to emit. If the compiler is not yet the authoritative consumer, a swapped prompt strands live output in a schema the existing dispatch doesn't speak. And if dispatch flips simultaneously (swap + flip), a single commit reviews two new failure modes at once.
- **(3) cannot land before there is real-world evidence the compiler's rejects match the existing path's rejects.** The calibration checkpoint (`mew proof-summary --m6_11-phase2-calibration`) requires a non-trivial population of live-captured replay bundles before it can evaluate the proposal's `≤5% off-schema / ≤3% refusal` gates (`docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md:145-156`). Today those bundles only exist from fixtures and offline replays.

Shadow mode satisfies both prerequisites with zero dispatch blast radius: the compiler sees real live inputs, the calibration surface gets real data, and the existing write-ready path continues to decide what actually runs. The next slice after this one gets to review a single question ("flip shadow to authoritative?") against a concrete incidence record, not against speculation.

## Scope boundary

**In scope:**

- New helper in `src/mew/work_loop.py` (candidate name: `_shadow_compile_patch_draft_for_write_ready_turn(...)`) that:
  1. adapts the current write-ready `action_plan` (tool-call shape) into a `patch_proposal` dict the compiler can consume — i.e., collect the `edit_file` / `edit_file_hunks` tool calls into `{"kind": "patch_proposal", "summary": …, "files": [{"path", "edits": [{"old", "new"}]}]}`;
  2. invokes `compile_patch_draft(todo=…, proposal=…, cached_windows=…, live_files=…, allowed_write_roots=…)` with the session's already-assembled `_work_write_ready_fast_path_details` state;
  3. if the result is a validated `PatchDraft`, invokes `compile_patch_draft_previews(patch_draft, allowed_write_roots=…)`;
  4. invokes `write_patch_draft_compiler_replay(...)` in every terminal branch (validated, blocker, or exception) so the calibration surface gets a bundle per write-ready turn;
  5. returns a small observation dict the caller copies onto `model_metrics`.
- One call site in `plan_work_model_turn()` at `src/mew/work_loop.py:~2088` (immediately after `normalize_work_model_action` returns and only when `write_ready_fast_path.active` is true).
- Three new `model_metrics` keys: `patch_draft_compiler_ran` (bool), `patch_draft_compiler_artifact_kind` ("patch_draft" | "patch_blocker" | "none"), `patch_draft_compiler_replay_path` (str; absolute path or empty). Optional fourth: `patch_draft_compiler_error` (str; only populated if the helper raised).
- No changes in `src/mew/commands.py`. The existing `update_work_model_turn_plan(..., model_metrics=planned.get("model_metrics"))` at `src/mew/commands.py:~4165` already carries the new keys through to turn state.

**Out of scope (explicit non-goals for this slice):**

- Do not touch `build_work_write_ready_think_prompt()` at `src/mew/work_loop.py:1428` — prompt stays exactly as-is.
- Do not touch `normalize_work_model_action()` at `src/mew/work_loop.py:1457` — parse step unchanged.
- Do not dispatch the `compile_patch_draft_previews` output. The `previews` are recorded on the turn record; existing action dispatch continues unchanged.
- Do not touch `build_work_recovery_plan()` or `resume_draft_from_cached_windows`. A shadow PatchBlocker does not change recovery.
- Do not touch `build_work_session_resume()` / `work --follow-status`.
- Do not touch `write_tools.py` (frozen per design doc line 881).
- Do not touch any approval/apply call site.
- Do not add a feature flag. The helper is always-on when `write_ready_fast_path.active`; off otherwise. Flagging is unnecessary because the shadow observation cannot change behavior and `patch_draft_compiler_ran=False` is the correct metric when the fast path is inactive.

## Files to touch

| File | Change |
| --- | --- |
| `src/mew/work_loop.py` | Add `_shadow_compile_patch_draft_for_write_ready_turn(...)` helper near `_work_write_ready_fast_path_details()` (`src/mew/work_loop.py:1205`). Call it from `plan_work_model_turn()` right after `normalize_work_model_action()` (around `src/mew/work_loop.py:2088`), guarded by `if write_ready_fast_path.get("active")`. Add the three (optionally four) keys to the `model_metrics` dict built around `src/mew/work_loop.py:2003`. |
| `src/mew/work_replay.py` | No code change. The existing `write_patch_draft_compiler_replay(...)` at `src/mew/work_replay.py:199` already accepts exactly the six inputs the helper will pass. |
| `src/mew/commands.py` | No changes. |
| `src/mew/patch_draft.py` | No changes. |
| `src/mew/proof_summary.py` | No changes. The calibration checkpoint will start seeing real bundles automatically once the helper writes them. |

## Tests

Place next to existing write-ready tests in `tests/test_work_session.py` (alongside `test_write_ready_fast_path_falls_back_to_recent_target_path_windows` at line ~6165 and `test_write_ready_draft_runtime_mode_contract` at ~6806). Five net new tests:

1. **Shadow validated path.** Write-ready turn returns an `edit_file` / `edit_file_hunks` action_plan whose paths + old/new align with `_work_write_ready_fast_path_details` cached windows and on-disk content → compiler produces a validated PatchDraft → translator produces previews → turn's `model_metrics` has `patch_draft_compiler_ran=True`, `patch_draft_compiler_artifact_kind="patch_draft"`, `patch_draft_compiler_replay_path` is non-empty and points at an existing `replay_metadata.json`. Dispatch behavior (final action on the turn) is unchanged from the existing test's expectation.
2. **Shadow blocker path.** Cached windows deliberately mismatched from live file text → compiler produces a `stale_cached_window_text` PatchBlocker → metrics record `artifact_kind="patch_blocker"` with non-empty replay path; turn's final action is still the original `edit_file` action (shadow mode does not intercept).
3. **Fast path inactive.** Non-write-ready turn → helper not called → metrics expose `patch_draft_compiler_ran=False`, `artifact_kind="none"`, `replay_path=""`. No replay bundle written.
4. **Non-edit action plan.** Write-ready fast path active, but `normalize_work_model_action` returns a non-`edit_file` action (e.g., the model emitted a `read_file` tool call) → the adapter declines to synthesize a proposal and the helper records `patch_draft_compiler_artifact_kind="none"` without writing a replay bundle (or writes a blocker bundle with an explicit "not an edit action" code — implementer's call, but the test pins whichever is chosen).
5. **Helper exception isolation.** Monkey-patch `write_patch_draft_compiler_replay` to raise `RuntimeError` → turn still persists with the original action, `patch_draft_compiler_error` is populated, `patch_draft_compiler_replay_path=""`, and no other turn-state field is corrupted. Mirrors the Phase 2 model-failure bundle's `except Exception: pass` discipline (`src/mew/commands.py:4112-4121`).

Tests 1 and 2 can reuse the existing `tests/fixtures/work_loop/patch_draft/paired_src_test_happy/scenario.json` and `stale_cached_window_text/scenario.json` fixtures for their cached-window + live-file setup, driven by the same `tempfile.TemporaryDirectory` + `os.chdir` pattern used in `tests/test_work_replay.py`.

No changes needed in `tests/test_patch_draft.py` or `tests/test_work_replay.py`.

## Acceptance criteria

1. `plan_work_model_turn()` invokes the compiler on every write-ready turn where `_work_write_ready_fast_path_details` reports `active=True`.
2. Every such invocation writes a replay bundle under `.mew/replays/work-loop/<date>/session-<id>/todo-<id>/attempt-<n>/replay_metadata.json`, regardless of whether the compiler produced a validated draft or a blocker.
3. `model_metrics.patch_draft_compiler_ran`, `patch_draft_compiler_artifact_kind`, `patch_draft_compiler_replay_path` are set on the turn record in all three states (validated / blocker / fast-path-inactive) and are persisted by the existing `update_work_model_turn_plan(..., model_metrics=...)` path at `src/mew/commands.py:~4165`.
4. `mew proof-summary --m6_11-phase2-calibration .mew/replays/work-loop` run after a live write-ready turn returns the real bundles, not an empty sample. (The existing calibration gate thresholds are not modified in this slice.)
5. Every existing write-ready test in `tests/test_work_session.py` still passes *unchanged* — demonstrating that turn-dispatch behavior did not regress.
6. The helper catches all exceptions from `compile_patch_draft`, `compile_patch_draft_previews`, and `write_patch_draft_compiler_replay`, logs them into `model_metrics.patch_draft_compiler_error`, and never blocks the outer turn from persisting. Matches the error-isolation discipline already used for the live-loop model-failure replay at `src/mew/commands.py:4112-4121`.
7. `build_work_write_ready_think_prompt`, `normalize_work_model_action`, `build_work_recovery_plan`, `build_work_session_resume`, `write_tools.py`, and every approval/apply code path are byte-identical to the pre-slice state.

## Follow-on work (explicitly NOT in this slice)

- **Prompt swap.** Replace `build_work_write_ready_think_prompt()` with the tiny patch contract so the model directly emits `patch_proposal` JSON. Removes the action_plan → proposal adapter. Calibration gate evaluation should gate this slice.
- **Authoritative dispatch.** Flip from shadow to authoritative: when `patch_draft_compiler_artifact_kind="patch_draft"`, dispatch the translator's preview specs instead of the original action. This is the slice that finally retires `build_work_write_ready_think_prompt` and the adapter.
- **Draft-time recovery.** On a compiler PatchBlocker, run `resume_draft_from_cached_windows` or equivalent instead of the generic replan. Phase 4 scope.
- **Follow-status surface.** Expose `patch_draft_compiler_artifact_kind` and `patch_draft_compiler_error` in `work --follow-status`.

## Residual risks for this slice

- **Adapter correctness.** The `action_plan → patch_proposal` adapter is a new implicit contract that lives until the prompt swap removes it. If the current write-ready prompt ever emits a shape the adapter doesn't recognize, the helper records `artifact_kind="none"` rather than erroring — which is the right safety posture but means "adapter can't interpret" becomes operationally indistinguishable from "fast path inactive" unless the metric distinguishes them. Recommend a distinct `patch_draft_compiler_artifact_kind="unadapted"` value or equivalent.
- **Replay-bundle volume.** Shadow mode will write one bundle per write-ready turn; a long session could populate `.mew/replays/work-loop/` with many attempts per todo. The calibration scanner handles this, but operators may want a retention knob before Phase 3 closes. Out of scope here.
- **Compiler-vs-dispatch divergence is now observable.** Turns where the compiler produces a blocker but dispatch succeeds (or vice versa) will show up in the replay data. That is the feature, not the bug — the calibration gate is how we read the divergence. But it means reviewers may see "shadow says blocker, loop still succeeded" in transcripts and need to know that's expected for this slice.
