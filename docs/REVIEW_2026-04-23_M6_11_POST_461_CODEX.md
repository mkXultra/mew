STATUS: PASS

COUNTEDNESS: partial

DECISION: Ledger task #461 / session #445 as a non-counted partial finish-gate validation, not as M6.11 replay incidence. The session usefully confirms that the generalized no-verifier-only finish gate blocks a dogfood verifier-green no-change closeout, but it produced no same-session replay bundle, no reviewer-visible paired dry-run patch, no source/test diff, and no exact live draft-lane model-failure/blocker artifact.

Evidence:

- Session #445 ended in `wait`, not `finish`, with the persisted reason: `finish is blocked: calibration-measured tasks require a same-session replay artifact or reviewer-visible paired patch evidence; verifier-only closeout is not enough for this task`.
- The focused verifier ran and passed: `uv run pytest -q tests/test_dogfood.py -k 'm6_11_drafting_recovery' --no-testmon`.
- The session then read the anchored `tests/test_dogfood.py` and `src/mew/dogfood.py` windows and attempted to finish by treating the existing dogfood scenario as the requested sample.
- `.mew/replays/work-loop/2026-04-23/session-445` has no files, and session #445 records `draft_attempts=0`, `cached_window_ref_count=0`, and `latest_patch_draft_compiler_replay={}`.
- `PYTHONPATH=src python3 -m mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json` on HEAD `b74770081c532d2f25a943648ebcbc30c9650b76` reports `calibration.cohorts.current_head.total_bundles=0`.

Ledger disposition for `#461`: append one non-counted partial gate-validation row. Do not increment replay incidence, do not populate `replay_bundle_path`, and do not treat the passing dogfood verifier as a substitute for a live replay/draft-lane artifact.

```json
{"recorded_at":"2026-04-23T13:15:31Z","head":"b74770081c532d2f25a943648ebcbc30c9650b76","task_id":461,"session_id":445,"attempt":null,"scope_files":["src/mew/dogfood.py","tests/test_dogfood.py"],"verifier":"uv run pytest -q tests/test_dogfood.py -k 'm6_11_drafting_recovery' --no-testmon","counted":false,"countedness":"partial_gate_validation_only","non_counted_reason":"Focused dogfood verifier passed and the model attempted a no-change finish by claiming the existing dogfood scenario already yielded the requested sample, but the generalized calibration finish gate converted finish to wait because session #445 emitted no same-session replay artifact, no reviewer-visible paired dry-run patch evidence, no source/test diff, and no exact live draft-lane model-failure/blocker.","blocker_code":null,"reviewer_decision":"accepted_as_live_finish_gate_validation_not_replay_incidence","replay_bundle_path":null,"review_doc":"docs/REVIEW_2026-04-23_M6_11_POST_461_CODEX.md","notes":"This is another verifier-green dogfood-surface no-change closeout caught by the finish gate. It validates the gate, not the replay incidence path. proof-summary on b747700 still reports current_head.total_bundles=0."}
```

This is only another finish-gate validation, not replay incidence. The stop rule required one same-session replay bundle, one reviewer-visible paired dry-run patch, or one exact live draft-lane model-failure/blocker. #461 satisfied none of those; it only demonstrated that the gate refuses a verifier-only closeout after a model tries to over-read fixture evidence.

Next bounded M6.11 action: stop sampling verifier-green dogfood surfaces for now. More runs on this dogfood scenario are likely to produce the same low-information pattern: passing verifier, no live draft attempt, no replay directory, and another finish-gate block. Keep HEAD frozen if the batch requires it, but choose a task that reaches the live `patch_draft`/draft lane directly: a tightly scoped source/test pair whose success criterion is a reviewer-visible paired dry-run patch or an exact native draft-lane blocker before any finish. After that run, rerun:

```sh
PYTHONPATH=src python3 -m mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json
```
