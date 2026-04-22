# M6.11 Phase 2 — PatchDraftCompiler Scaffolding (Claude Review)

Scope: the uncommitted slice introducing the pure offline compiler.

- [`src/mew/patch_draft.py`](/Users/mk/dev/personal-pj/mew/src/mew/patch_draft.py) (new)
- [`tests/test_patch_draft.py`](/Users/mk/dev/personal-pj/mew/tests/test_patch_draft.py) (new)

Third round of review after the latest follow-up fixes. Cross-checked against [`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md`](/Users/mk/dev/personal-pj/mew/docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md) and [`docs/REVIEW_2026-04-22_M6_11_PHASE2_COMPILER_CODEX_REVIEW.md`](/Users/mk/dev/personal-pj/mew/docs/REVIEW_2026-04-22_M6_11_PHASE2_COMPILER_CODEX_REVIEW.md). `uv run python -m unittest tests.test_patch_draft` is green (18/18, up from 12/12 in round 2 and 6/6 in round 1).

## Verdict

**No active blocker-level findings. Acceptable to land as the Phase 2 scaffolding slice.**

Every active concern from the prior round of review is now addressed:

- **Prior Finding #2 (caller-optional write-root enforcement) — RESOLVED.** `_validate_pairing` ([`patch_draft.py:225-230`](/Users/mk/dev/personal-pj/mew/src/mew/patch_draft.py#L225)) now fails fast with `write_policy_violation` + detail `"allowed_write_roots is required for validation"` whenever the argument is empty or omitted. The whole suite was retrofitted to pass an explicit `ALLOWED_WRITE_ROOTS = ["."]` ([`test_patch_draft.py:35`](/Users/mk/dev/personal-pj/mew/tests/test_patch_draft.py#L35)), and the missing-roots case is pinned by `test_compile_patch_draft_blocks_write_policy_violation_when_roots_missing` ([`test_patch_draft.py:353-374`](/Users/mk/dev/personal-pj/mew/tests/test_patch_draft.py#L353)). The independent Codex finding tracking the same gap is closed by the same change.

- **Prior residual risk (new strict-missing-live-file branches unpinned) — RESOLVED.** Three direct tests now cover each of the three blocker paths in `_normalize_live_file`:
  - `test_compile_patch_draft_blocks_missing_live_file_payload` ([line 433-456](/Users/mk/dev/personal-pj/mew/tests/test_patch_draft.py#L433)) — `live_files={}`.
  - `test_compile_patch_draft_blocks_missing_live_file_text` ([line 458-481](/Users/mk/dev/personal-pj/mew/tests/test_patch_draft.py#L458)) — `live_files={path: {}}`.
  - `test_compile_patch_draft_blocks_missing_live_file_sha256` ([line 483-506](/Users/mk/dev/personal-pj/mew/tests/test_patch_draft.py#L483)) — `live_files={path: {"text": ...}}`.

- **Prior residual risk (test coverage regressions from round 1) — RESOLVED.** Both removed tests are back: `test_compile_patch_draft_blocks_unpaired_source_edit` ([line 407-431](/Users/mk/dev/personal-pj/mew/tests/test_patch_draft.py#L407)) re-pins the `unpaired_source_edit_blocked` branch, and `test_compile_patch_draft_blocks_non_dict_proposal` ([line 394-405](/Users/mk/dev/personal-pj/mew/tests/test_patch_draft.py#L394)) re-pins the non-dict-proposal path into `model_returned_non_schema`.

## Findings

No active findings. One follow-up that was open at the end of round 2 is carried forward into residual risks below because it is a pre-Phase-3 concern, not a Phase 2 gate.

## Residual risks

- **Recovery-action vocabulary drift (prior Finding #1).** The seven non-design strings in `PATCH_BLOCKER_RECOVERY_ACTIONS` ([`patch_draft.py:11-24`](/Users/mk/dev/personal-pj/mew/src/mew/patch_draft.py#L11)) — `narrow_old_text`, `merge_or_split_hunks`, `revise_patch`, `add_paired_test_edit`, `revise_patch_scope`, `retry_with_schema`, `inspect_refusal` — remain unreferenced by [`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:565-572`](/Users/mk/dev/personal-pj/mew/docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md#L565), which still lists only six actions. This does not affect the Phase 2 offline-compiler contract — no caller outside the compiler reads the field yet — so it is correctly deferred. It does become a contract gap the moment Phase 3 starts emitting these strings into replay bundles and follow-status. Resolution remains either widening the design enum or collapsing the mapping onto the existing six.

- **`cached_window_text_truncated` localizes to `windows[0]`** ([`patch_draft.py:274-283`](/Users/mk/dev/personal-pj/mew/src/mew/patch_draft.py#L274)), not the actually-truncated window — consistent with the Codex review. Only matters once Phase 3 feeds multi-window inputs.

- **Carry-forward (unchanged behavior, unchanged risk):**
  - Multi-window bundle text uses `\n` join ([`patch_draft.py:413`](/Users/mk/dev/personal-pj/mew/src/mew/patch_draft.py#L413)); straddling-edit soft-check could misfire with multi-window inputs.
  - `_stable_artifact_id` hashes `{todo_id, summary, files}` only; `summary` wording drift rotates the id without semantic change, and per-file content hashes are not factored in.
  - `PatchDraft` / `PatchBlocker` still omit `created_at` despite appearing in the design's example schemas (also flagged by Codex).
  - Compiled `files[].edits` is returned in proposal order while the diff is generated post-sort; ordering contract remains implicit.
  - `int(line_start)` coercion failure in `_normalize_cached_window_bundle` resets both `line_start` and `line_end`.
  - `tests/fixtures/work_loop/patch_draft/` still does not exist — explicit Phase 2 follow-up per design lines 593–600 and "Concrete First Tasks" #5 (line 913).

## Recommended next step

Land the slice. Before the first Phase 3 caller wiring, pick up the recovery-action vocabulary reconciliation as the last open Phase 2 contract item — either widen `LOOP_STABILIZATION_DESIGN_2026-04-22.md:565-572` or collapse the compiler's seven extra strings onto the existing six — because migration cost goes up sharply once these codes start appearing in persisted replay bundles, follow-status output, and resume JSON.
