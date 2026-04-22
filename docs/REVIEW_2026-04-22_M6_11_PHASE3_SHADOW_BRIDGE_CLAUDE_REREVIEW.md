# M6.11 Phase 3 — Shadow-Mode Live Bridge (Claude Re-Review)

Scope: only the follow-up to `docs/REVIEW_2026-04-22_M6_11_PHASE3_SHADOW_BRIDGE_CLAUDE_REVIEW.md` Findings 1 and 2. Files: `src/mew/work_loop.py`, `tests/test_work_session.py`. Code not modified per instructions.

## Verdict

**No active findings. Safe to land.** Both fixes match what the prior review asked for, and the exception-isolation test is slightly stronger than the suggested shape (drives `main()` end-to-end rather than `plan_work_model_turn` directly).

## Prior findings — resolution

### Prior Finding 1 (path normalizer divergence) — **resolved**

The helper now imports the strip-variant from `test_discovery` at `src/mew/work_loop.py:15`:

```python
from .test_discovery import normalize_work_path
```

A local alias `canonical_path` is defined at the top of the helper (`src/mew/work_loop.py:1258-1259`) and used consistently at every normalization site the prior review flagged:

- Target-path extraction from `active_work_todo.source` (`work_loop.py:1276`), `resume.working_memory.target_paths` (`work_loop.py:1282`), and `recent_windows` fallback (`work_loop.py:1289`).
- Proposal tool path (`work_loop.py:1316`).
- `cached_windows` / `live_files` dict keys via the window-iteration loop (`work_loop.py:1363, 1377, 1380, 1388`).

Every path that flows into the compiler's `proposal`, `cached_windows`, or `live_files` now passes through the same `.strip()`-aware normalizer that `compile_patch_draft._normalize_proposal` / `_normalize_cached_window_bundle` use internally. The whitespace-edge-case phantom-blocker risk the prior review flagged is closed. The local `_normalized_work_path` at `work_loop.py:1887` is still used by other write-ready fast-path helpers and is left intact — this is correct scope; the alignment fix targets only the shadow-bridge surface where the compiler's normalizer matters.

### Prior Finding 2 (missing exception-isolation test) — **resolved, stronger than recommended**

New test at `tests/test_work_session.py:7039-7121`: `test_patch_draft_compiler_shadow_bridge_replay_writer_exception_does_not_escape`. It patches `mew.work_loop.write_patch_draft_compiler_replay` with `side_effect=RuntimeError("disk full")` and drives the whole CLI through `main()` rather than just `plan_work_model_turn`, which pins one stricter invariant than the prior review asked for: "an exception inside the shadow helper does not regress the exit code of `mew work`." Specifically it asserts:

- `main([...]) == 0` (`tests/test_work_session.py:7084-7105`) — whole invocation still succeeds.
- `turn["status"] == "completed"` (`tests/test_work_session.py:7110`) — turn state persists cleanly.
- `turn["action"]["type"] == "batch"` and the tool paths list is exactly the model's mocked batch, in the original order (`tests/test_work_session.py:7111-7115`) — outer action preserved byte-for-byte.
- `metrics["patch_draft_compiler_artifact_kind"] == "exception"` (`tests/test_work_session.py:7117`) — exception branch was actually hit.
- `"disk full" in metrics["patch_draft_compiler_error"]` (`tests/test_work_session.py:7118`) — the error message survived the `clip_output` call and is recorded.
- `metrics["patch_draft_compiler_replay_path"] == ""` (`tests/test_work_session.py:7119`) — no stale path written on the failed branch.

The shadow-bridge test count goes from four to five, locking every branch of the helper (validated / blocker / unadapted / exception / fast-path-inactive).

### Prior Finding 3 (pre-sink snapshot ambiguity) — **unchanged, still non-blocker**

The prior review classified this as low-severity ("Low severity because the final turn record always has the post-helper values"). This revision does not address it, which matches its non-blocker status. Noted below as residual.

## Residual non-blocking risks (carried over, unchanged)

- **Pre-sink snapshot ambiguity.** `work_loop.py:2202-2208` still initializes the four compiler keys to `False`/`""` before the helper runs and `2209-2210` snapshots them to `pre_model_metrics_sink`. Pre-sink consumers see `ran=False` indistinguishable in shape from the post-run "unadapted" state. Low severity; cosmetic fix would be to exclude the keys from the pre-sink snapshot, but final turn records remain correct in all cases.
- **Helper assumes `cwd == workspace root`** for `Path(path).read_text()` at `work_loop.py:1385`. Shadow-only impact; in a sub-directory invocation the bundle records a phantom `stale_cached_window_text` blocker.
- **Replay bundle proliferation** — one bundle per write-ready turn, no retention policy. Operational concern once the prompt swap lands and write-ready turns become common.
- **Adapter is a new implicit contract** — the `action_plan → patch_proposal` adapter at `work_loop.py:1310-1352` must keep matching whatever shape the write-ready prompt produces until the prompt swap retires both. The `artifact_kind="unadapted"` signal makes breakage diagnosable.

Nothing here warrants blocking the prompt-swap slice.
