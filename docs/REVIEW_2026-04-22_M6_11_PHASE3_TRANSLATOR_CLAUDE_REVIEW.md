# M6.11 Phase 3 — PatchDraft → Dry-Run Preview Translator (Claude Review, Revision 2)

Scope: `src/mew/patch_draft.py` (new `compile_patch_draft_previews`), `tests/test_patch_draft.py` (new `PatchDraftTranslatorFixtureTests`, seven tests). Revision 2 re-checks the four findings from revision 1.

## Verdict

**No active blocker-level findings. Safe to land as offline plumbing.**

The shape-vs-planning-note divergence is now documented in the function's own docstring rather than implicit. Write-policy coverage gained two dedicated tests. Rejection coverage expanded from one to four branches and includes a new duplicate-path tightening the implementation itself added in this revision. Offline-only is still confirmed: `grep -r compile_patch_draft_previews src/` returns only the definition at `src/mew/patch_draft.py:101`. No callers in `work_loop.py`, `work_session.py`, or `commands.py`.

## Findings

### Prior Finding 1 — Output shape divergence from planning note — **resolved via docstring**

The function now opens with an explicit contract declaration (`src/mew/patch_draft.py:101-106`):

> Convert a validated PatchDraft into dry-run write action specs for the existing write-action execution path (edit_file/edit_file_hunks payload shape), not write_tool result objects.

That is a durable in-code statement of option (1) from revision 1's recommendation: the translator produces a *call spec*, not a `write_tools.py` result object. The planning note's "shaped exactly like dry-run output" commitment is explicitly retracted in favor of a payload shape the caller will use to *invoke* `edit_file` / `edit_file_hunks` in dry-run mode. Because the declaration lives on the function itself, the next slice's reviewer cannot miss it. The function name still reads "previews" rather than "specs," which is minor cosmetic drift; I've kept that in residual risks.

### Prior Finding 2 — Write-policy rejection path untested — **resolved**

Two new tests pin the two live policy-rejection branches:

- `tests/test_patch_draft.py:175-193` (`test_compile_patch_draft_previews_requires_allowed_write_roots`) passes `allowed_write_roots=[]` with an otherwise-valid draft; asserts `kind == "patch_blocker"`, `code == "write_policy_violation"`, and that the detail message matches the "allowed_write_roots is required" branch at `src/mew/patch_draft.py:138`.
- `tests/test_patch_draft.py:195-214` (`test_compile_patch_draft_previews_rejects_path_outside_allowed_roots`) passes `allowed_write_roots=["/tmp/forbidden-root"]`; asserts the out-of-roots branch at `src/mew/patch_draft.py:164-169` emits a `write_policy_violation` with the offending path attached.

Both code paths now have explicit coverage, and the detail-string assertion on the first test will catch an accidental branch merge on future edits.

### Prior Finding 3 — Rejection coverage is one-of-many — **materially improved**

Rejection-path coverage went from one test to four, including a new branch the implementation itself added in this revision:

- Non-list edits (`test_compile_patch_draft_previews_rejects_invalid_draft`, `tests/test_patch_draft.py:162-175`) — carried over from revision 1.
- Empty `allowed_write_roots` (Finding 2 above).
- Path outside roots (Finding 2 above).
- **Duplicate same-path files** (`test_compile_patch_draft_previews_rejects_duplicate_same_path_entries`, `tests/test_patch_draft.py:216-243`) — new test pinning a new tightening. The implementation now tracks a `seen_paths` set (`src/mew/patch_draft.py:124`) and rejects a second `files[]` entry for the same path as `model_returned_non_schema` with `"duplicate path"` in the detail. This mirrors the compiler's own duplicate-path check at `src/mew/patch_draft.py:158-163` — defense in depth without silent success.

Still untested (but not blocker-level, because the compiler produces validated PatchDrafts upstream and these are malformed-input guards): invalid `kind`, missing `path`, non-string / empty `old`, non-string `new`, `edit_file` with 0 or 2+ edits, unvalidated `status`, non-dict input, non-dict `file_item`. I've left these as a residual-risk item rather than elevating them — the load-bearing policy paths (write-policy and duplicate-path) are covered, and a compiler-produced artifact will never hit the malformed-input branches.

### Prior Finding 4 — SHA / provenance metadata dropped — **deferred, acceptable**

`src/mew/patch_draft.py:144-148` still emits only `type`, `path`, `apply`, `dry_run`, and the edit payload. The compiler's `window_sha256s`, `pre_file_sha256`, `post_file_sha256` fields (`src/mew/patch_draft.py:365-367`) are still not carried into the preview.

This is the "decide explicitly" question from revision 1, and the explicit decision in this slice is "don't forward." That is defensible: the `PatchDraft` itself still carries the SHAs, so the next slice's caller can reach back into the `PatchDraft` directly if it needs to verify "live file is still at `pre_file_sha256` before dispatching the dry-run." The translator's job stops at structural/policy validation + call-spec emission. Worth restating as a residual risk, not a blocker.

### Prior Findings 5–7 — passthrough, ordering, offline-only — **still correct**

- Blocker passthrough (`src/mew/patch_draft.py:113-114`, tested at `tests/test_patch_draft.py:147-160`) — unchanged, correct.
- Ordering preservation (file order + within-file edit order, tested at `tests/test_patch_draft.py:260-298`) — unchanged, correct by construction.
- Offline-only — re-verified; no new production callers.

## Residual risks

- **Function name vs docstring mismatch.** The function is `compile_patch_draft_previews`, but the docstring correctly calls its output "dry-run write action specs … not write_tool result objects." The name still suggests the result-object reading. Rename to `compile_patch_draft_dispatches` (or similar) when the next slice lands and the caller's shape is stable; too early to rename until the caller exists.
- **SHA provenance not forwarded.** `window_sha256s` / `pre_file_sha256` / `post_file_sha256` are on the `PatchDraft` itself but absent from the preview (Finding 4). The next slice will need to reach back into the `PatchDraft` for those values if it wants to verify on-disk state before executing dry-run. Not a bug; a deferred design decision.
- **`kind` / `type` terminology drift.** Compiler's per-file output uses `kind` (`src/mew/patch_draft.py:363`); translator emits `type` (`src/mew/patch_draft.py:227`). Two vocabularies for the same tool identifier inside the same module. Cosmetic; fix when the caller lands.
- **Secondary rejection branches still untested.** Bad `kind`, missing `path`, non-string `old`/`new`, empty `old`, `edit_file` edit-count mismatch, unvalidated `status`, non-dict inputs. Compiler-produced artifacts should never hit these; hand-built inputs (as used in some tests) can, but the risk is contained to non-production entry points.
- **Dead code until the next slice lands.** Acceptable for a bounded plumbing slice; planning note (`docs/REVIEW_2026-04-22_M6_11_PHASE3_FIRST_SLICE_CLAUDE.md:60`) already flagged this.
- **`patch_draft.get("todo_id") or patch_draft.get("id")` fallback** (`src/mew/patch_draft.py:112`) — `id` is the artifact-level identifier from the compiler (`src/mew/patch_draft.py:91`) while `todo_id` is the work-item identifier (`src/mew/patch_draft.py:92`). Using `id` as a fallback will attribute a rejection to the artifact id rather than the todo id in a malformed-input case — unlikely in practice but worth a one-line comment if rejections ever feed into session state.

## Recommended next step

Land the slice. When the next Phase 3 slice wires a live caller:

1. Decide the SHA-forwarding question (forward through the preview vs. re-read from the `PatchDraft`).
2. Rename `compile_patch_draft_previews` if the caller's consumption confirms "specs" rather than "previews" is the right noun.
3. Consider adding one or two of the untested secondary rejection branches (invalid `kind`, unvalidated `status`) if the live caller is ever exposed to hand-built or partially-malformed `PatchDraft` inputs.
