# M6.11 Phase 2 — Compiler Replay-Capture (Claude Review, Revision 2)

Scope: `src/mew/work_replay.py` (`write_patch_draft_compiler_replay` + `_sanitize_replay_path_component`), `tests/test_work_replay.py` (six tests, incl. fixture round-trip).

Revision 2 of this review; supersedes the prior revision and re-checks the three contract-level findings it raised. Independent of [`REVIEW_2026-04-22_M6_11_PHASE2_COMPILER_REPLAY_CODEX_REVIEW.md`](REVIEW_2026-04-22_M6_11_PHASE2_COMPILER_REPLAY_CODEX_REVIEW.md); both of Codex's findings are also re-checked.

## Verdict

**No active findings. Safe to land; safe for Phase 3 to wire.**

All three prior contract concerns (round-trip shape, silent empty-dict coercion, unsanitized path components) are resolved with precision: the helper's keyword signature now mirrors `compile_patch_draft()`'s inputs 1:1, every required payload is isinstance-guarded with a no-op fallthrough, and `_sanitize_replay_path_component` normalizes path separators before interpolation. A fixture-driven round-trip test proves a captured bundle re-feeds back into the compiler without shape loss.

## Findings

### Prior Finding 1 (round-trip contract is unspecified) — **resolved**

The helper signature at `src/mew/work_replay.py:199-209` now takes exactly the six slots that matter for offline replay:

```
session_id, todo_id, todo, proposal, cached_windows, live_files, allowed_write_roots, validator_result
```

which mirrors `compile_patch_draft(*, todo, proposal, cached_windows, live_files, allowed_write_roots)` at `src/mew/patch_draft.py:53` with `validator_result` appended for the expected output. Bundle files on disk (`work_replay.py:244-251`) match the same names (`todo.json`, `proposal.json`, `cached_windows.json`, `live_files.json`, `allowed_write_roots.json`, `validator_result.json`), and `replay_metadata.json` enumerates them (`work_replay.py:264-271`). No more semantic drift between "what the compiler needs" and "what the bundle carries."

The new round-trip test at `tests/test_work_replay.py:239-279` closes this definitively: it loads `tests/fixtures/work_loop/patch_draft/paired_src_test_happy/scenario.json`, writes the bundle, re-reads the six payloads from disk, re-invokes `compile_patch_draft(**payload)`, and asserts the artifact's `kind`/`status` match the fixture's `expected`. This is the exact contract the prior review asked for.

### Prior Finding 2 (silent coercion of non-dict payloads, Codex F1) — **resolved**

`work_replay.py:210-221` now rejects bad payloads up front:

- `todo`, `proposal`, `cached_windows`, `live_files`, `validator_result` must each pass `isinstance(..., dict)` — else return `None`.
- `allowed_write_roots` must pass `isinstance(..., (list, tuple))` — else return `None`.

No more empty-dict coercion. `test_patch_draft_compiler_replay_invalid_required_payload_is_noop` at `tests/test_work_replay.py:181-205` pins this for `proposal=[]` and additionally asserts `.mew/replays/work-loop` is not created. A single case covers the `isinstance` gate; the six slots all go through the same code shape, so one test is sufficient to lock the contract.

### Prior Finding 3 (unsanitized path components, Codex F2) — **resolved**

`_sanitize_replay_path_component` at `work_replay.py:49-52` replaces `/` and `\` with `-` after stripping. Applied to both `session_id` and `todo_id` at `work_replay.py:223-224`. `test_patch_draft_compiler_replay_sanitizes_path_components` at `tests/test_work_replay.py:207-237` pins:

- `session_id="session/1"` → path segment `session-session-1`
- `todo_id="todo/9/1"` → path segment `todo-todo-9-1`
- Raw `todo/9/1` absent from the final metadata path

Directory-traversal via `".."` is not a concern here because the string never contains a path separator after normalization — `"../foo"` sanitizes to `"..-foo"`.

### Prior Finding 4 (bundle naming underscore/hyphen inconsistency) — **not addressed; downgraded**

Still `bundle: "patch_draft_compiler"` at `work_replay.py:259` vs `bundle: "work-loop-model-failure"` at `work_replay.py:159`. Cosmetic; was flagged as non-blocker in revision 1 and remains non-blocker. Filed under residual risks.

### Prior Finding 5 (test coverage gaps) — **materially resolved**

- Non-dict payload path: now covered by the invalid-payload test.
- Round-trip through the compiler: now covered by the fixture round-trip test.
- `session_id=0`: still uncovered. `_sanitize_replay_path_component(0)` returns `"0"`, which writes a valid `session-0/` bundle — benign. Not worth adding a test.
- Per-`(session, todo)` attempt counter isolation: still uncovered, still correct by construction (the counter is scoped to `base_dir.glob("attempt-*")`, and `base_dir` includes session and todo).

## Residual risks

- **Bundle-name convention.** `patch_draft_compiler` (underscores) next to `work-loop-model-failure` (hyphens). Cosmetic; harmonize next time either helper is touched.
- **Lossy ID correlation in metadata.** `metadata["session_id"]` and `metadata["todo_id"]` at `work_replay.py:260-261` store the *sanitized* form, not the original. If a live caller ever passes an id containing `/` (Phase 1 format-controlled ids won't, but nothing here enforces that), the original is unrecoverable from the bundle alone. Low priority unless Phase 3 adopts opaque id shapes.
- **Round-trip assertion is narrow.** The new test checks `artifact["kind"]` / `artifact["status"]` against the fixture's `expected` (`tests/test_work_replay.py:275-276`), but not `assertEqual(artifact, scenario["expected"])`. Compiler correctness is presumably pinned elsewhere; this test's job is bundle round-trip, so narrowness is OK — but a tighter `self.assertEqual(artifact, payload["validator_result"])` would also lock the bundle against *its own* stored output, which is the strongest possible replay guarantee. Optional.
- **Process-wide `os.chdir` in tests.** Six tests now rely on `os.chdir(tmp)` + `finally: os.chdir(old_cwd)`. Same fragility as revision 1; a pytest-style `tmp_path` fixture or a `self.addCleanup(os.chdir, old_cwd)` pattern would be more robust. Not blocking.
- **`REPLAYS_ROOT` hardcoded** (`work_replay.py:10`). Carried over from the prior helper; not introduced by this slice.
- **Bundle is intentionally narrower than the full live-failure spec.** Design doc at `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:669-678` lists `resume.json`, `model_output.json`, `follow_status.json`, `notes.txt` on top of what's here. Intentionally deferred; the `bundle: "patch_draft_compiler"` discriminator gives readers a way to distinguish compiler-only bundles from future live-failure bundles sharing the same root.

## Recommended next step

Land the slice. When Phase 3 wires the call site, feed the same six compiler inputs through the new helper verbatim — no adapter layer needed. If the narrower round-trip assertion is tightened to `assertEqual(artifact, payload["validator_result"])` while in the area, it would pay small dividends as compiler logic evolves.
