STATUS: FAIL

COUNTEDNESS: counted

The sample counts for M6.11, but the current source/test diff should not be committed as-is.

Evidence inspected:

- HEAD is `e1734f73a56e7043441617e36a47887bcfa86022`.
- Same-session replay metadata exists for session `443`, task `todo-443-1`, attempts `1`, `2`, and `3` under `.mew/replays/work-loop/2026-04-23/session-443/todo-todo-443-1/`.
- All three replay metadata files report `git_head=e1734f73a56e7043441617e36a47887bcfa86022` and `calibration_counted=true`.
- Attempt `3` reports `blocker_code=old_text_not_found`.
- `PYTHONPATH=src python3 -m mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json` reports `errors=[]`, `current_head.total_bundles=3`, and `current_head.blocker_code_counts.old_text_not_found=1`.
- `.mew/follow/session-443.json` shows the live run stopped at step `4` with `tool_failed` / `old text was not found`; the last failed tool was a dry-run edit against `tests/test_patch_draft.py`.

This satisfies the stop rule because the run produced same-session current-head replay bundles and an exact live draft-lane blocker. It is not a verifier-only finish. The passing verifier commands are useful validation, but they are not the countedness basis.

Ledger disposition for `#459`: record as counted. Use `task_id=459`, `session_id=443`, `head=e1734f7`, scope `src/mew/patch_draft.py` and `tests/test_patch_draft.py`, and cite attempt `3` with `blocker_code=old_text_not_found`. Notes should mention that attempts `1` and `2` were also current-head counted `patch_draft_compiler` bundles with reviewer-visible paired dry-run source/test patches, while attempt `3` is the exact live blocker that ended the run. A suitable reviewer decision is `accepted_as_counted_current_head_replay_with_cleanup_required`.

Must-fix code quality issues before commit:

- `src/mew/patch_draft.py` now has three effective `seen_paths.add(path)` calls in the preview loop: two added by the dirty diff plus the existing one from `e1734f7`. The new calls are redundant. They do not appear to break behavior, but they are commit noise and make the validation flow harder to reason about.
- `tests/test_patch_draft.py` now has three duplicate-path preview tests: the two newly added tests plus the existing `test_compile_patch_draft_previews_rejects_duplicate_same_path_entries` that was already present in `e1734f7`. The added tests exercise the same behavior and should not be kept.
- The root cause of the redundant patch is visible in the replay evidence: the live model only had cached windows through line `220`, while the existing `seen_paths.add(path)` and existing duplicate-path test were below that visible window. That is valid calibration evidence, not a reason to keep duplicate implementation.

Disposition for the mew-generated patch: simplify by reverting the dirty changes in `src/mew/patch_draft.py` and `tests/test_patch_draft.py`. Do not keep the current diff as-is. A full revert of those two files to `e1734f7` is the minimal intended final shape because the duplicate-path behavior and test already existed before sample `#459`.

Exact minimal intended final shape:

- `src/mew/patch_draft.py`: keep only the original `seen_paths.add(path)` after the `edit_file` single-edit validation and before preview assembly. Remove the newly inserted earlier `seen_paths.add(path)` calls.
- `tests/test_patch_draft.py`: keep the existing `test_compile_patch_draft_previews_rejects_duplicate_same_path_entries`; remove the two newly added duplicate-path tests.
- No behavior change is needed in these two files for this sample.

Validation commands after cleanup:

```sh
git diff -- src/mew/patch_draft.py tests/test_patch_draft.py
uv run python -m unittest tests.test_patch_draft.PatchDraftTranslatorFixtureTests.test_compile_patch_draft_previews_rejects_duplicate_same_path_entries
uv run python -m unittest tests.test_patch_draft
uv run ruff check src/mew/patch_draft.py tests/test_patch_draft.py
python3 -m py_compile src/mew/patch_draft.py
git diff --check
PYTHONPATH=src python3 -m mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json
```

The first command should show no diff for `src/mew/patch_draft.py` and `tests/test_patch_draft.py` after cleanup. The proof-summary command should continue to report the counted current-head replay evidence for session `443`; cleanup of the dirty source/test patch does not invalidate the collected replay artifacts.
