# M6.11 Phase 3 — First-Slice Planning Note (Claude)

Planning only. Identifies the smallest safe Phase 3 slice given the current repo state (Phase 2 replay capture + Phase 2/3 calibration checkpoint both landed) and the Phase 3 scope at `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:817-823`.

## Recommendation

**Land the `PatchDraft → dry-run preview` translator first, with no live-loop wiring and no prompt change.** Pure offline plumbing: one new function in `src/mew/patch_draft.py`, fixture-driven tests in `tests/test_patch_draft.py`. Entry gate is already satisfied (calibration checkpoint landed in the prior slice per design doc §Phase 3 entry gate, lines 830-834).

## Why this slice before the others

Phase 3 scope has three sub-tasks (design doc §Phase 3 lines 817-823):

1. Replace `build_work_write_ready_think_prompt()` with the tiny patch schema contract.
2. Route write-ready model output through `PatchDraftCompiler`.
3. Translate `PatchDraft` into existing dry-run `edit_file` / `edit_file_hunks`.

The translator (3) comes first because it is the load-bearing plumbing that both of the other two depend on, and because it is the only sub-task that can land with **zero live blast radius**:

- **(1) prompt swap alone breaks the loop.** Changing the prompt to emit `patch_proposal` JSON without a translator leaves `normalize_work_model_action` at `src/mew/work_loop.py:1457` with no route for the new shape — the very next model turn fails to parse. The design doc's freeze list also explicitly freezes "further prompt-only tuning of the current write-ready fast path" (design doc line 880), so any prompt work carries the most risk.
- **(2) compiler wiring alone has nothing to deliver.** `compile_patch_draft` produces a `PatchDraft` dict with `files[].kind = "edit_file" | "edit_file_hunks"` and `files[].edits = [{old, new}]` (`src/mew/patch_draft.py:361-369`). Until something converts that shape into the existing `edit_file(path, old, new, dry_run=True)` / `edit_file_hunks(path, edits, dry_run=True)` calls that `src/mew/work_session.py:1598-1617` already dispatches, wiring the compiler produces a dict the rest of the loop cannot consume.
- **(3) the translator is locally verifiable.** Its contract — `PatchDraft → list of dry-run preview dicts` — has no model dependency, no session dependency, no telemetry implications. It can be tested end-to-end against the Phase 2 fixtures (`tests/fixtures/work_loop/patch_draft/paired_src_test_happy/scenario.json`), which already carry the expected `PatchDraft` shape. The Phase 2 round-trip test (`tests/test_work_replay.py:239-279`) already proved those fixtures re-feed into the compiler cleanly; this slice proves they also re-feed into the existing write primitives.

Landing (3) first lets the next slice (either compiler wiring with the current prompt shimmed into `patch_proposal` shape, or the prompt swap itself) terminate in a tested translator rather than asking a reviewer to judge both ends of a new pipeline in the same commit.

## Scope boundary

**In scope:**
- One new function in `src/mew/patch_draft.py` (candidate name: `compile_patch_draft_previews(patch_draft, *, allowed_write_roots)`), taking a validated `PatchDraft` dict and returning a list of preview dicts shaped exactly like `edit_file`/`edit_file_hunks` dry-run output (per `src/mew/write_tools.py:413-429, 458-475`).
- Per-file dispatch: if `file["kind"] == "edit_file"` → unpack `edits[0]` to `old`/`new` and call `edit_file(path, old, new, allowed_roots, dry_run=True)`; if `"edit_file_hunks"` → pass the full `edits` list through to `edit_file_hunks`. Early return of a structured error dict if `patch_draft["kind"] == "patch_blocker"`.
- Fixture-driven tests asserting the translator's output for each fixture scenario matches what `edit_file`/`edit_file_hunks` emit directly with the same on-disk state.

**Out of scope (explicit non-goals for this slice):**
- Do not touch `src/mew/work_loop.py` (`build_work_write_ready_think_prompt`, `plan_work_model_turn`, `normalize_work_model_action`).
- Do not touch `src/mew/work_session.py` (`_work_write_ready_fast_path_details`, tool dispatch).
- Do not touch `src/mew/write_tools.py` — treat it as stable per design doc freeze list line 881.
- No new feature flag, no env var, no kwarg on any existing function. The translator is imported only by tests in this slice.
- No changes to `commands.py`, no CLI surface, no session-field additions.
- No changes to the replay writer or the calibration checkpoint.

## Files to touch

| File | Change |
| --- | --- |
| `src/mew/patch_draft.py` | Add `compile_patch_draft_previews(patch_draft, *, allowed_write_roots)` near the existing `compile_patch_draft` (`src/mew/patch_draft.py:53`). Thin dispatcher over `edit_file` / `edit_file_hunks` from `src/mew/write_tools.py`. |
| `tests/test_patch_draft.py` | Add 3–4 tests: (a) happy path against `paired_src_test_happy` fixture → emits two preview dicts with `dry_run=True`, non-empty `diff`; (b) translator on a `patch_blocker` input returns an error shape (or raises `ValueError`) without touching disk; (c) `edit_file` single-hunk case unpacks `edits[0]` correctly; (d) `edit_file_hunks` multi-hunk case preserves edit ordering. |

No other production code paths change.

## Test fixtures and staging

Translator tests need the target files to exist on disk matching `live_files.text` from the fixture (the existing dry-run primitives in `write_tools.py` read from disk). Use the same `tempfile.TemporaryDirectory` + `os.chdir` pattern already established in `tests/test_work_replay.py:35-63`. The `paired_src_test_happy/scenario.json` fixture at `tests/fixtures/work_loop/patch_draft/paired_src_test_happy/scenario.json:36-` already contains the literal `text` for each target path.

## What this unblocks

- **Next slice (Phase 3 step 2):** route live write-ready model output through `compile_patch_draft` and terminate in `compile_patch_draft_previews`. That slice adds a guarded call site in `src/mew/work_loop.py` after `normalize_work_model_action` (around line 2046 per the current layout) and records preview dicts back into the turn result. Because this slice already lands a tested terminal step, the next slice's review reduces to "is the guard right, is the call site right."
- **Slice after that (Phase 3 step 1):** the prompt swap. Once the compiler + translator are wired and producing replay bundles under real traffic, the calibration checkpoint (already landed) can quantify off-schema/refusal incidence for the current prompt before it is replaced.

## Residual risks

- **Dead code until the next slice lands.** `compile_patch_draft_previews` has no production caller in this slice. Acceptable for a deliberately bounded "plumbing first" approach; mitigated by the module-local tests and by the short path to the next slice.
- **Disk-staging in tests couples translator tests to filesystem state.** Unavoidable without touching `write_tools.py` (which the design doc freezes). The tempdir pattern already in use in `tests/test_work_replay.py` is sufficient.
- **`edit_file` kind with `len(edits) == 1`** is a contract inflection point between the compiler's output and the write primitives' input — the compiler sets `kind = "edit_file"` when `len(proposal_file["edits"]) == 1` (`src/mew/patch_draft.py:363`). The translator is the only place this unpacking lives; a test should explicitly assert it.
- **No entry-gate work needed.** The Phase 2/3 calibration checkpoint at `src/mew/proof_summary.py:205` is already wired per the prior landed slice, satisfying the design doc §Phase 3 entry gate.
