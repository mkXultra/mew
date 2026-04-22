# M6.11 Phase 3 — Shadow-Mode Live Bridge (Claude Review)

Scope: `src/mew/work_loop.py` (new `_shadow_compile_patch_draft_for_write_ready_turn` helper + call-site in `plan_work_model_turn` + four new `model_metrics` keys), `tests/test_work_session.py` (four new shadow-bridge tests, one new test helper `_seed_write_ready_shadow_session`).

## Verdict

**Safe to land. Shadow-only invariants hold; outer action semantics are unchanged.** The slice implements the Claude planning note's shadow-mode recommendation (not Codex's authoritative-dispatch recommendation), which is the safer first live-bridge choice. Two findings worth addressing before Phase 3 prompt swap; neither is a land blocker.

## Shadow-only invariants

- **Helper is pure with respect to outer dispatch.** `src/mew/work_loop.py:2270-2274` computes `action = normalize_work_model_action(action_plan, …)` *before* the helper runs at `src/mew/work_loop.py:2275-2285`. The helper never reassigns `action`; the return dict at `src/mew/work_loop.py:2292-2299` returns the pre-shadow `action`. Tests 1, 2, and 3 each assert `planned["action"]["type"]` against the model's mocked output, pinning this invariant.
- **No in-memory session/turn state mutated.** Helper only reads `session`, `context`, `action_plan`, `action`, `write_ready_fast_path` via `.get()` (`src/mew/work_loop.py:1253-1260`). Writes go to (a) the returned observation dict, and (b) the replay bundle directory. No keys added to `session`, no turn-state fields touched.
- **Shadow call gated by `write_ready_fast_path.active`.** Guard at `src/mew/work_loop.py:2275`. Test 4 (`test_patch_draft_compiler_shadow_bridge_is_skipped_when_write_ready_fast_path_is_inactive`) patches the helper with an `AssertionError` side effect and verifies a non-write-ready turn proceeds unaffected, with no compiler keys on `model_metrics` and no `.mew/replays/work-loop` directory created. Strong pin.
- **Exceptions are bounded.** `src/mew/work_loop.py:1383-1387` wraps the entire compiler/translator/replay-write sequence in `try/except Exception` and writes `artifact_kind="exception"`, `replay_path=""`, `error=<clipped>`. On the failure path the helper still returns a full observation dict, so the caller's `.update()` always sets the four keys and the outer turn proceeds.

## Findings

### Finding 1 — `_normalized_work_path` vs `normalize_work_path` divergence — latent, non-blocker

The helper uses `_normalized_work_path` from `src/mew/work_loop.py:1883-1884`:

```python
return str(path or "").replace("\\", "/").lstrip("./")
```

The compiler internals (`src/mew/patch_draft.py:151, 514`) use `normalize_work_path` from `src/mew/test_discovery.py:37-38`:

```python
return str(path or "").strip().replace("\\", "/").lstrip("./")
```

Difference: the compiler's variant does `.strip()`, the helper's variant does not. For well-formed model output this is invisible (paths have no surrounding whitespace), but if the model ever emits `" src/mew/patch_draft.py"` with a leading space:

- Helper builds `cached_windows` keyed on `" src/mew/patch_draft.py"` (`src/mew/work_loop.py:1359`) and `live_files` keyed on the same (`src/mew/work_loop.py:1350`).
- Helper builds `proposal["files"][i]["path"] = " src/mew/patch_draft.py"` (`src/mew/work_loop.py:1312`).
- Compiler's `_normalize_proposal` re-normalizes the proposal path via strip-variant → `"src/mew/patch_draft.py"`.
- Compiler's `_normalize_cached_window_bundle` then calls `cached_windows.get("src/mew/patch_draft.py")` — misses, because the dict key was kept in no-strip form.
- Result: phantom `missing_exact_cached_window_texts` blocker in the bundle even though the windows were present.

Bounded impact: shadow-only, so no dispatch regression; affects only calibration-bundle fidelity in the whitespace-edge case. Fix is one character: either import `normalize_work_path` from `test_discovery` and use it in the helper, or `.strip()` paths when building `cached_windows` / `live_files` / proposal file entries.

### Finding 2 — Exception-isolation path is not test-pinned

The planning note (`docs/REVIEW_2026-04-22_M6_11_PHASE3_LIVE_BRIDGE_PLAN_CLAUDE.md:67`) called for test #5: "Monkey-patch `write_patch_draft_compiler_replay` to raise `RuntimeError` → turn still persists with the original action, `patch_draft_compiler_error` is populated, `patch_draft_compiler_replay_path=""`, and no other turn-state field is corrupted." That test is not present in the landed slice — the four new tests cover validated, blocker, unadapted, and fast-path-inactive, but not helper-internal exception.

The isolation code itself is correct at `src/mew/work_loop.py:1383-1387`. But without a test pinning "compiler/translator/replay raises → outer turn still completes with original action + `patch_draft_compiler_error` populated," a future refactor can remove the `except Exception:` without any test failing. Given the slice's whole rationale is "instrumentation that never affects dispatch," this is the one invariant that should be locked by a test.

Suggested test (one new test, mirroring test 3's shape but with `patch("mew.work_loop.write_patch_draft_compiler_replay", side_effect=RuntimeError("disk full"))`): assert `planned["action"]` equals the original action, `planned["model_metrics"]["patch_draft_compiler_error"]` is non-empty, `planned["model_metrics"]["patch_draft_compiler_replay_path"] == ""`.

### Finding 3 — Pre-run metric snapshot reports `patch_draft_compiler_ran=False` even when it will run

`src/mew/work_loop.py:2202-2208` initializes the four compiler keys before the think / act calls, then `src/mew/work_loop.py:2209-2210` passes a snapshot to `pre_model_metrics_sink`. Any consumer of the pre-sink sees `ran=False`, `artifact_kind=""`, `replay_path=""`, `error=""` — which is strictly the pre-run state, but the key `patch_draft_compiler_ran=False` is indistinguishable in shape from "the helper ran and decided the call was unadapted." Consumers reading pre-sink metrics alongside the final turn record could confuse "pre-run snapshot" with "helper executed and rejected the action."

Low severity because the final turn record (what the calibration gate reads) always has the post-helper values. But if anyone starts logging pre-sink snapshots for debugging, this ambiguity will bite. Either (a) omit the compiler keys from the pre-sink snapshot (they get added by the helper anyway since `.update()` adds new keys), or (b) use a tri-state `artifact_kind` such that `""` means "pre-run" and `"unadapted"` / `"none"` means "helper decided not to call compiler."

### No-action observations

- **Replay always captured on terminal branches.** `src/mew/work_loop.py:1375-1382` is reached only when `compile_patch_draft` returns (validated or blocker). On exception, `replay_path` stays `""` by design — the replay surface only records *compiler inputs/outputs*, which don't exist if the compiler itself threw. Consistent with the Phase 2 replay contract.
- **Translator return value intentionally discarded.** `src/mew/work_loop.py:1372-1374` calls `compile_patch_draft_previews` but does not record its result. Defensible for shadow mode: the compiler-replay bundle already captures inputs + `validator_result`, and the translator's own contract is pinned by `tests/test_patch_draft.py`. Re-invoking it here is a "does translation succeed?" smoke test, not a dispatch-path check.
- **`model_metrics` key hygiene.** Pre-init at `src/mew/work_loop.py:2202-2208` + post-helper `.update()` at `src/mew/work_loop.py:2275-2285` ensures the four keys are always present on write-ready turns. On non-write-ready turns, the keys are absent (test 4 asserts `assertNotIn("patch_draft_compiler_ran", planned["model_metrics"])`). Clean.
- **Total model seconds unaffected by shadow.** `src/mew/work_loop.py:2286-2289` computes `total_model_seconds = think + act`, measured separately. The shadow helper's latency (file reads + compile + translator + replay write) is not counted, which is the right choice — shadow work shouldn't inflate the user-facing latency metric.
- **Replay path is resolved to absolute.** `src/mew/work_loop.py:1381` does `str(Path(replay_path).resolve())`, which avoids cwd-dependent relative paths in the recorded metric. Good for cross-session correlation.
- **Target-path extraction has correct fallback order.** `src/mew/work_loop.py:1261-1271` tries `active_work_todo.source.target_paths` → `resume.working_memory.target_paths` → paths from `recent_windows`. Test 1 exercises the working-memory fallback path (the seeder places target_paths there, not on `active_work_todo`).

## Residual risks

- **Helper assumes `cwd == workspace root` for live-file reads.** `src/mew/work_loop.py:1344-1352` calls `Path(path).read_text()` on relative paths. In a normal mew invocation this resolves inside the workspace, but if the loop is ever driven from a sub-directory the live_files dict will be empty → compiler will blocker on `stale_cached_window_text`. Shadow-only impact.
- **Replay bundle proliferation.** One bundle per write-ready turn, no retention knob. Acceptable per planning-note residual risk §2; operators should be aware when long sessions accumulate attempts.
- **Adapter is a new implicit contract.** The `action_plan → patch_proposal` adapter at `src/mew/work_loop.py:1287-1322` lives until the prompt swap retires `build_work_write_ready_think_prompt`. Any future write-ready prompt tweak must keep producing shapes the adapter recognizes (batch of `edit_file` / `edit_file_hunks`), or the bundles silently flip to `unadapted`. The `artifact_kind="unadapted"` value is distinct from `"none"` / `""`, so a calibration operator can tell them apart — that's Codex-planning-note protection that landed correctly.
- **`compile_patch_draft_previews` exceptions are absorbed as "exception" rather than their own category.** If the compiler succeeds with a validated draft but the translator raises (e.g., a contract regression between the two), the bundle records the validator_result correctly but the metric reads `artifact_kind="exception"` — losing the information that the compiler actually succeeded. Acceptable because the replay bundle itself records `validator_result.kind == "patch_draft"`, so calibration analysis can still see what happened by reading the bundle. But metric-only consumers see a less informative signal.
- **`prompt_swap` is now the only remaining load-bearing change to Phase 3.** When it lands, Finding 1 becomes moot (paths will flow directly from the model's `patch_proposal` JSON rather than through `_normalized_work_path`); until then, Finding 1 is a latent bundle-fidelity bug.

## Recommended next step

Land the slice. Before the Phase 3 prompt swap lands:

1. Add the missing exception-isolation test (Finding 2) — cheap to write, pins the one invariant the slice's value proposition rests on.
2. Switch the helper to `test_discovery.normalize_work_path` (Finding 1) so calibration bundles faithfully reflect compiler intent even on whitespace-edge-case paths. One-line change.
3. Consider whether the pre-sink snapshot should omit the four compiler keys (Finding 3) or whether the ambiguity is tolerable given the pre-sink's debug-only role.

None of the three block landing this slice. All three are cheap; if the prompt-swap slice is the next to land, (1) is the only one that matters — (2) and (3) can wait until that slice retires the adapter entirely.
