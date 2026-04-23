STATUS: PASS

COUNTEDNESS: partial

DECISION: Ledger task #460 / session #444 as non-counted for M6.11 replay incidence, but accepted as live validation that the generalized no-verifier-only finish gate is working on frozen HEAD `b747700`. Do not increment `current_head` replay incidence and do not treat the passing `PatchDraftTests` verifier as a replay artifact.

The decisive behavior is the finish-gate conversion. Session #444 read the fenced `src/mew/patch_draft.py` and `tests/test_patch_draft.py` windows, recovered from a stale verifier command, passed the corrected verifier, then attempted to finish by claiming a same-session replay bundle. The persisted action was converted to `wait` with:

`finish is blocked: calibration-measured tasks require a same-session replay artifact or reviewer-visible paired patch evidence; verifier-only closeout is not enough for this task`

This validates the no-verifier-only finish gate, but it does not count for replay incidence. There is no replay directory for `.mew/replays/work-loop/2026-04-23/session-444`, `latest_patch_draft_compiler_replay` is empty, `draft_attempts=0`, `cached_window_ref_count=0`, and the current `proof-summary` output on HEAD `b747700` reports `calibration.cohorts.current_head.total_bundles=0`.

Ledger disposition for `#460`: append one non-counted partial gate-validation row, not a counted replay row.

```json
{"recorded_at":"2026-04-23T13:01:19Z","head":"b74770081c532d2f25a943648ebcbc30c9650b76","task_id":460,"session_id":444,"attempt":null,"scope_files":["src/mew/patch_draft.py","tests/test_patch_draft.py"],"verifier":"uv run python -m unittest tests.test_patch_draft.PatchDraftTests.test_compile_patch_draft_blocks_cached_window_text_truncated","counted":false,"countedness":"partial_gate_validation_only","non_counted_reason":"Finish gate correctly converted a verifier-only no-change finish to wait after the corrected focused verifier passed, but session #444 emitted no same-session replay artifact, no reviewer-visible paired dry-run patch evidence, no source/test diff, and no exact live draft-lane replay/model-failure blocker.","blocker_code":null,"reviewer_decision":"accepted_as_live_finish_gate_validation_not_replay_incidence","replay_bundle_path":null,"review_doc":"docs/REVIEW_2026-04-23_M6_11_POST_460_CODEX.md","notes":"Initial tool_call_id=3639 used stale PatchDraftCompilerTests and failed with AttributeError; same session recovered with corrected tool_call_id=3640 using PatchDraftTests and passed. Treat the stale verifier as a note on #460, not a separate operator-error/non-counted ledger row, because it was corrected before the decisive finish-gate outcome."}
```

Stale verifier disposition: mention it only in the #460 row notes. Do not ledger it as a separate operator-error/non-counted sample. The task description had already been corrected to `PatchDraftTests`, and the same session successfully reran the corrected verifier before the finish-gate behavior under review. The stale command is relevant provenance, not the reason this sample is non-counted.

Next bounded action under M6.11: keep HEAD frozen at `b747700`, but rotate away from this already-covered cached-window truncation seam to a different bounded surface that is more likely to emit a real replay bundle, reviewer-visible paired dry-run patch, or exact draft-lane blocker. Do not fix a substrate issue from #460 alone; the substrate behavior under test worked. After the next sample, rerun:

```sh
PYTHONPATH=src python3 -m mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json
```
