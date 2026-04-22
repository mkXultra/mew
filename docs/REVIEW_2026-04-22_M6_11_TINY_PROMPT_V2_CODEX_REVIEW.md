# M6.11 Tiny Prompt v2 Codex Review

## Verdict

Approve. No blocking findings in the scoped diff.

## Findings

None.

## Review Notes

### 1. Generic/write-ready behavior outside the tiny lane

Preserved. The behavioral shrink is isolated to the tiny-lane contract builder and tiny prompt serialization in [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1825) and [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:2034). The regular write-ready fast-path prompt builder and its broader contract are unchanged. The only shared runtime change outside the tiny context body is the tiny contract version bump to `v2` at [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:66).

### 2. Tiny context load-bearing fields

The slice keeps the fields the tiny model actually needs to draft a patch artifact:

- `active_work_todo.source.plan_item`
- `active_work_todo.source.target_paths`
- `write_ready_fast_path.cached_window_texts[].path`
- `write_ready_fast_path.cached_window_texts[].text`
- `allowed_roots.write`

That is sufficient for model-side draft generation. Patch-draft correctness is still enforced against the full runtime/compiler environment, not the shrunken tiny prompt context: `_attempt_write_ready_tiny_draft_turn(...)` compiles against the original `context` plus `write_ready_fast_path`, and the compiler reconstructs line/hash/live-file validation from the authoritative fast-path windows at [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1453) and [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1515). Removing `id`, `status`, `attempts`, `blocker`, `verify_command`, line spans, and hashes from the tiny prompt therefore reduces prompt weight without weakening validator correctness.

### 3. Tests

The new tests are correctly scoped and materially useful:

- Actionable-surface narrowing is covered at [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:6245).
- Minimal tiny-contract shape and compact serialized JSON are covered at [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:6333).
- Contract-version propagation through planning metrics is covered at [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:7019).

Existing end-to-end tiny-lane tests for successful preview compilation and validated blocker translation remain in place immediately below that area, so this slice adds the missing contract-shrink assertions without broadening scope.

Scoped verification run:

```text
uv run python -m pytest -q tests/test_work_session.py -k 'tiny_write_ready_draft_context_and_prompt_are_minimal_contract or test_plan_work_model_turn_extends_timeout_for_write_ready_fast_path or test_tiny_write_ready_draft_lane_returns_authoritative_preview_batch or test_tiny_write_ready_draft_lane_returns_wait_for_patch_blocker or test_tiny_write_ready_draft_context_prefers_first_actionable_plan_item_surface'
.....                                                                    [100%]
5 passed, 460 deselected in 2.16s
```

### 4. Regressions / dead branches

No subtle regression or newly introduced unreachable branch stood out in the scoped diff. The defensive fallbacks in `build_write_ready_tiny_draft_model_context(...)` predate this slice. This change mainly removes non-load-bearing fields from the tiny context and switches the tiny prompt JSON to compact serialization at [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:2054).

### 5. Bounded M6.11 landing call

This should land now as bounded M6.11 progress. It matches the stated intent, keeps the non-tiny write-ready path stable, and materially shrinks the tiny prompt surface. On the scoped fixture, the new tiny prompt is 786 characters shorter than the previous shape while preserving the same drafting contract shape at the compiler boundary.

## Landing Recommendation

Land it.

Residual risk is limited to live-task variability: the fix is structurally sound, but prompt pressure should still be monitored via `tiny_write_ready_draft_prompt_chars` on the next #402-like retries after merge.
