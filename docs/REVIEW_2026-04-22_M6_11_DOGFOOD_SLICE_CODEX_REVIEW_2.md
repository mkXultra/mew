Verdict: revise

Prior finding status: the earlier compiler-replay proof-strength issues appear resolved in the current diff. The earlier weak `m6_11-draft-timeout` proof is no longer present because that scenario was removed, but that leaves the slice short of the intended implemented coverage.

Findings:
1.
- severity: high
- file:line: src/mew/dogfood.py:77-81; src/mew/dogfood.py:670-675; src/mew/dogfood.py:10602-10605; tests/test_dogfood.py:527-617
- issue: `m6_11-draft-timeout` is still registered as part of this bounded slice, but the handler now returns `not_implemented` and the tests were updated to expect that stub behavior.
- why it matters: The stated slice contract was to land two offline deterministic scenarios: `m6_11-compiler-replay` and `m6_11-draft-timeout`. The current diff only delivers one. That removes close-gate evidence for the timeout-before-draft path and turns the intended 2-pass / 3-pending slice into 1-pass / 4-pending.
- concrete fix: Restore the deterministic `m6_11-draft-timeout` scenario using the recovery fixture and `build_work_session_resume`, then switch the tests back to asserting a passing blocked-on-patch recovery report instead of a stub.

2.
- severity: medium
- file:line: src/mew/dogfood.py:350-359; src/mew/dogfood.py:678-698; src/mew/dogfood.py:10591-10599; tests/test_dogfood.py:575-617
- issue: Aggregate close-gate semantics still collapse `not_implemented` into a generic top-level `fail`, and the new subset aggregate test now codifies that as the expected outcome.
- why it matters: An `all` run cannot distinguish "implemented scenario failed" from "coverage intentionally pending". That is still misleading close-gate signaling and hides the actual per-scenario split behind a single failure bit.
- concrete fix: Keep per-scenario `not_implemented`, but add explicit aggregate accounting or non-strict handling so `scenario=\"all\"` can report the pass/not_implemented split without reducing the whole run to an undifferentiated failure. Update the aggregate test to lock that clearer contract.

Residual risks
- `m6_11-compiler-replay` is still scoped to every fixture directory under `tests/fixtures/work_loop/patch_draft`, so unrelated future fixture additions will change the dogfood surface area unless the scenario is explicitly bounded.

Suggested validation additions
- Add a focused passing test for the restored `m6_11-draft-timeout` scenario that asserts the blocked-on-patch recovery invariants from the deterministic fixture.
- Add one negative compiler-replay test that removes required fixture hashes and verifies the stronger replay checks fail cleanly.
