# M6.11 Post-405 Malformed Bundle Review

## 1. Verdict: does this require a substrate fix before more counted samples?

Yes.

Current-head calibration is not self-protecting. A reviewer-rejected, explicitly non-counted sample from `session-405` still enters the current-head cohort, and `proof-summary` then mislabels its valid `patch_draft` outputs as malformed. That means the checkpoint is not trustworthy enough to keep collecting counted samples first.

## 2. What is the true bug?

There are two coupled substrate bugs:

1. `proof-summary` treats `validator_result.code` as mandatory for every `patch_draft_compiler` bundle. In [`src/mew/proof_summary.py`](../src/mew/proof_summary.py), `_read_validator_result_code()` returns only `validator.get("code")` at lines `226-238`, and `_summarize_patch_draft_compiler_bundle()` marks the bundle malformed when that value is `None` at lines `286-289`. But successful compiler outputs from [`compile_patch_draft()`](../src/mew/patch_draft.py) are valid `{"kind":"patch_draft","status":"validated",...}` artifacts with no `code` field at lines `53-95`. The two `session-405` `validator_result.json` files are exactly that shape, so they are valid artifacts being misclassified as malformed.

2. Replay bundles do not encode whether they are calibration-counted. [`write_patch_draft_compiler_replay()`](../src/mew/work_replay.py) writes every compiler replay with bundle/git/session/todo metadata only at lines `273-354`; there is no `counted/non_counted` or reviewer-disposition field. Meanwhile `.mew/state.json` explicitly says `session-405` "does not count toward the current-head calibration cohort" at line `908111`, and records the replay paths for the two polluted attempts at lines `908581` and `908692`. So the countedness decision exists only in operator/session state, not in the artifact that `proof-summary` actually consumes.

The malformed-bundle symptom is real, but the deeper bug is that calibration eligibility is external to the replay bundle.

## 3. What is the narrowest correct fix?

The narrowest correct fix is a small two-part substrate patch:

1. Fix compiler bundle parsing in `proof-summary` so a valid `validator_result.json` with `kind=="patch_draft"` and `status=="validated"` is accepted even when `code` is absent, and bucketed as `patch_draft_compiler.other`. Only unreadable JSON, non-dicts, or unrecognized validator shapes should count as malformed.

2. Add an explicit calibration-eligibility field to replay metadata, for example `calibration_counted: true|false` plus `calibration_exclusion_reason`. Have `proof-summary` skip `calibration_counted=false` bundles from `relevant_bundles`, `total_bundles`, and malformed-count gates.

That is smaller and more correct than teaching `proof-summary` to scrape `.mew/state.json`, and more durable than deleting files by hand.

## 4. Should session #405 artifacts be excluded from current-head calibration by code, by metadata, or by operator process?

By metadata, enforced by code.

Operator process alone is already proven insufficient: the operator rejected `session-405`, but the artifacts still polluted the checkpoint. Code-only exclusion without metadata would require brittle heuristics or ad hoc coupling to `.mew/state.json`. The replay artifact itself should declare whether it is calibration-counted, and `proof-summary` should honor that declaration.

For the already-written `session-405` artifacts, the least-bad immediate cleanup is a one-time metadata backfill to mark them non-counted after the field lands.

## 5. Recommended next bounded action

Land one bounded slice in `src/mew/proof_summary.py`, `src/mew/work_replay.py`, and focused tests:

- accept validated `patch_draft` replay results without `code`
- add `calibration_counted` / exclusion-reason metadata to compiler replay bundles
- exclude non-counted bundles from calibration math
- backfill the two `session-405` `replay_metadata.json` files to `calibration_counted=false`
- rerun `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json`

Do that before collecting any more counted current-head samples.
