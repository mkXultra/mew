Verdict: revise

Findings:
1.
- severity: medium
- file:line: src/mew/dogfood.py:370-449; tests/test_dogfood.py:478-501
- issue: `m6_11-compiler-replay` is presented as deterministic replay evidence, but the scenario auto-hydrates missing fixture hashes and only asserts coarse outputs like kind, counts, and diff substrings. It never proves the hash-bearing compiler artifact surface itself.
- why it matters: This can stay green even if the replay inputs are incomplete or if deterministic outputs such as `validator_version`, `window_sha256s`, `pre_file_sha256`, `post_file_sha256`, or a stable draft artifact id regress. That makes the close-gate proof materially weaker than the scenario name suggests.
- concrete fix: Treat fixture hash fields as required instead of backfilling them in the dogfood runner, and extend `expected` plus `_append_patch_draft_expected_checks` to assert the deterministic artifact fields that downstream code consumes. Update the dogfood test to check for those stronger check names instead of only fixture count and a single `kind` check.

2.
- severity: medium
- file:line: src/mew/dogfood.py:572-584; tests/test_dogfood.py:526-529
- issue: The `m6_11-draft-timeout` scenario only fails if the first recovery item becomes `replan`. Any other wrong recovery action still passes the dogfood report.
- why it matters: This slice is supposed to prove the blocked-on-patch timeout recovery surface. A regression from the intended `needs_user_review` safe-resume path to `retry_tool`, `retry_verification`, or another unrelated action would still produce a passing scenario artifact.
- concrete fix: Make the scenario check the exact first recovery action (`needs_user_review`) and the expected safe-resume hints/steps, then tighten the unit test to assert the stronger check is present and passing.

3.
- severity: medium
- file:line: src/mew/dogfood.py:72-76; src/mew/dogfood.py:610-653; src/mew/dogfood.py:10591-10599; tests/test_dogfood.py:531-555
- issue: The three explicit `not_implemented` M6.11 handlers are now part of `DOGFOOD_SCENARIOS`, but top-level aggregation still treats only `status == "pass"` as success.
- why it matters: Any `dogfood --scenario all` or other all-scenarios consumer now gets a hard `fail` solely because pending scenarios are registered. That collapses "registered but intentionally unimplemented" into "scenario execution failed" and blocks a clean aggregate 2-pass / 3-not_implemented close-gate readout.
- concrete fix: Either keep pending scenarios out of the default `all` set until they are executable, or add explicit top-level `not_implemented` accounting/strictness so aggregate runs can report the split without converting the whole run into a generic failure. Add a focused test that locks the intended `scenario='all'` semantics.

Residual risks
- `m6_11-compiler-replay` currently sweeps every directory under `tests/fixtures/work_loop/patch_draft`, so unrelated future fixture additions will silently change the dogfood scenario scope and expected artifact count.
- There is no negative-path dogfood coverage for malformed fixture payloads, so a broken fixture may still crash or produce misleading evidence instead of a clean scenario failure.

Suggested validation additions
- Add a targeted `run_dogfood_scenario(..., scenario="all")` test that locks the intended aggregate handling of `pass` vs `not_implemented`.
- Add a compiler replay test that fails when required fixture hashes are removed or when deterministic artifact fields change unexpectedly.
- Add a draft-timeout test that asserts the exact recovery action plus `--auto-recover-safe` guidance, not just "not replan".
