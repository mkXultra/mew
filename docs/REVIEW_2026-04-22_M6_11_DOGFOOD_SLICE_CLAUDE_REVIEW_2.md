# M6.11 Dogfood Scenario Slice Re-review (2026-04-22, claude)

Scope: same working-tree diff as before
(`src/mew/dogfood.py` + `tests/test_dogfood.py`) after the author's
response to `docs/REVIEW_2026-04-22_M6_11_DOGFOOD_SLICE_CLAUDE_REVIEW.md`
and `docs/REVIEW_2026-04-22_M6_11_DOGFOOD_SLICE_CODEX_REVIEW.md`.
Focus: correctness, milestone honesty, implemented-vs-not_implemented
coverage.

## Verdict

**Approve.**

All HIGH/MEDIUM blockers from the prior review are fully resolved. The
slice is now honest about what it proves and what it defers.

## Prior findings — status

### 1. HIGH (draft-timeout scenario was misleading `#401` evidence) — **resolved**

- `run_m6_11_draft_timeout_scenario` now returns
  `_scenario_not_implemented_report` with reason
  `"#401 timeout-before-draft recovery coverage is not implemented in
  this slice"` (`src/mew/dogfood.py:581-586`). No assertions about
  `refresh_cached_window` / "not replan" / session-level recovery are
  made. The scenario can no longer be cited as `#401` coverage.
- The misleading fixture
  `tests/fixtures/work_loop/recovery/402_timeout_before_draft/` has
  been removed from the tree (`ls tests/fixtures/work_loop/` now
  returns only `patch_draft`). No source file references
  `RECOVERY_FIXTURE_ROOT`, `402_timeout_before_draft`, or
  `refresh_cached_window` anymore.
- `test_run_dogfood_m6_11_draft_timeout_scenario`
  (`tests/test_dogfood.py:542-560`) pins the new contract: aggregate
  `report["status"] == "fail"`, scenario `status == "not_implemented"`,
  and the reason string contains `"401"`. The traceability from "this
  scenario slot is reserved for `#401`" to the roadmap bullet is
  preserved without overclaiming.

### 2. MEDIUM (weak "not replan" positive assertion) — **resolved**

- The weak `_not_replan` and `canonical_action == "refresh_cached_window"`
  checks were removed along with the `run_m6_11_draft_timeout_scenario`
  body. Nothing in the slice now asserts a recovery-plan shape that
  would silently bless an incorrect `#401` recovery.

### 3. LOW (observed/predicate mismatch in compiler-replay) — **resolved**

- `src/mew/dogfood.py:581-589` now emits
  `observed={"has_todo": ..., "has_model_output": ...,
  "fixture_name": ...}`, matching the predicate
  (`bool(todo) and bool(model_output)`). Debug output for a failing
  fixture will now point at the missing field directly.

### 4. LOW (fixture directory name overstated content) — **resolved**

- The fixture directory no longer exists, so the mislabel cannot
  persist. Nothing in `tests/fixtures/work_loop/` encodes a
  `#401`-shaped claim without the content to back it.

## What this re-review also confirms (net new)

The diff did more than address the prior findings; it also tightened
the compiler-replay scenario in substantive ways worth recording:

- `_scenario_patch_draft_fixture_checks` (`src/mew/dogfood.py:405-462`)
  now asserts every fixture includes `window_sha256`, `file_sha256`,
  and a live-file `sha256` for every target path, with an
  observed-value payload that pinpoints which path/index is missing.
  Previously the diff silently hydrated missing hashes via
  `_hydrate_patch_draft_fixture_payload`, which hid fixture laziness;
  that helper is gone and hashes are now required inputs.
- `_append_patch_draft_expected_checks`
  (`src/mew/dogfood.py:469-574`) adds
  `validator_version`, `artifact_id`, per-file `window_sha256s`,
  `pre_file_sha256`, and `post_file_sha256` (plus a structural
  `post != pre` check). For the blocker arm it pins
  `recovery_action` to `PATCH_BLOCKER_RECOVERY_ACTIONS`. The
  compiler-replay scenario now produces real close-gate-grade evidence
  for `#399`-shaped recovery (validator identity, provenance hashes,
  blocker→recovery mapping), not just a kind-match smoke test.
- `_expected_patch_draft_artifact_id` mirrors
  `src/mew/patch_draft.py:677-680` (`_stable_artifact_id("draft", ...)`)
  — sha1(json.dumps(payload, sort_keys=True, separators=(",", ":")))
  truncated to 12 hex, prefix `draft-`. Payload shape (`todo_id`,
  `summary`, `files`) matches what `compile_patch_draft` hashes, and
  the producer pops `_unified_diff` from each file before the hash, so
  the reconstruction against `artifact["files"]` is faithful. Drift in
  the producer algorithm will flip this check — intentional coupling.
- `test_run_dogfood_m6_11_all_subset_aggregate_reflects_not_implemented`
  (`tests/test_dogfood.py:587-629`) patches `DOGFOOD_SCENARIOS` to
  just the `m6_11-*` names and asserts the aggregate is `fail`, the
  implemented scenario is `pass`, and the four deferred ones are
  `not_implemented`. This is the shape the close artifact will cite.

Aggregate honesty path still holds: `src/mew/dogfood.py:10591` still
does `passed = all(report.get("status") == "pass" for report in
reports)`, so any `not_implemented` scenario flips
`report["status"]` to `"fail"`.

## Residual risks

- **Artifact-id / validator-version parity coupling.**
  `_expected_patch_draft_artifact_id` and the `validator_version`
  check hardcode producer-side implementation details
  (`_stable_artifact_id`'s prefix/digest length and
  `PATCH_DRAFT_VALIDATOR_VERSION`'s value at test time). This is the
  correct trade-off for an evidence scenario — the point is to
  detect drift — but the fix path when the producer legitimately
  bumps the version will be: update both producer and scenario in
  the same slice. Worth a one-line comment only if future bumps
  become frequent; not a blocker.
- **Single implemented scenario.** The close-gate artifact derived
  from this slice can only honestly cite `m6_11-compiler-replay`
  (three fixtures: paired-happy, stale-cached-window, ambiguous).
  `#401`, refusal separation, drafting recovery, and phase-4
  regression remain `not_implemented`. The slice's test harness
  makes that status machine-readable (the new aggregate test pins
  it), but the close artifact narrative must not roll up all five
  scenario names into a single "passing" claim. Narrative risk, not
  a code defect.
- **Compiler-replay has no allow-list.** Any new directory dropped
  into `tests/fixtures/work_loop/patch_draft/` is silently folded
  into `m6_11-compiler-replay`. That is fine for the current three
  fixtures but means a future fixture contributor can change what
  this scenario proves without editing `dogfood.py`. Consider an
  explicit expected-fixture-set assertion later — not required for
  this slice.

## Suggested validation additions

- None required for this slice. The aggregate test
  (`test_run_dogfood_m6_11_all_subset_aggregate_reflects_not_implemented`)
  already covers the shape the close-gate artifact will cite, and
  the per-scenario tests already pin both the implemented and
  not_implemented contracts.
- Optional, for a follow-up slice: a negative-fixture test that
  confirms the new `validator_version` / `artifact_id` /
  `recovery_action` checks actually flip to `fail` when the
  producer-side invariant is violated (e.g. temporarily monkey-patch
  `PATCH_DRAFT_VALIDATOR_VERSION` and assert the scenario fails).
  This would be load-bearing only if producer-side drift becomes a
  real risk vector.
