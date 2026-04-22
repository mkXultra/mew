# Findings

No active findings.

The current uncommitted prompt-reduction slice meets the four review checks:

1. Output schema compatibility appears intact. `build_work_write_ready_think_prompt()` still instructs the model to "Return the standard work JSON schema" and still embeds the unchanged `_work_action_schema_text()` that `normalize_work_model_action()` already consumes. [`src/mew/work_loop.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1520) [`src/mew/work_loop.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1656) [`src/mew/work_loop.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1682) The tests also explicitly pin that the write-ready prompt still contains the standard action schema and does not switch to `patch_proposal` / `patch_blocker`. [`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:6225)

2. The prompt reduction is substantive, not cosmetic. `build_write_ready_work_model_context()` no longer injects the prior broad `task`, `date`, `work_session.resume`, recent decisions, notes, and target-path cached-window observation payloads; it now limits the prompt context to `active_work_todo`, exact cached window texts, allowed roots, and one focused verify command. [`src/mew/work_loop.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1496) The new bounded-size test freezes that reduced shape at <= 9k total chars on the representative two-window fixture, well below the previously observed 40k+ timeout regime. [`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:6233)

3. The contract version bump to `v2` is propagated consistently in runtime metrics and readouts. The runtime constant is bumped at [`src/mew/work_loop.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:64), the planning-path metrics assertion is updated at [`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:6916), and the downstream resume / latest-failure surfaces are all updated to `v2`. [`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:7295) [`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:7449) [`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:22813)

4. I do not see unintended behavior changes outside prompt content/version in this slice. The only production behavior changes in scope are the v2 constant and the write-ready prompt/context builder. `normalize_work_model_action()` is unchanged. [`src/mew/work_loop.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1682)

# Verdict

Green for this bounded Phase 2.5 prompt-reduction slice.

# Residual Non-Blocking Risks

- The new bounded-size assertion is fixture-based, not replay-based. It is good enough for this slice, but it will not catch future prompt-growth drift from real live shadow sessions unless a replay-backed size assertion is added later. [`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:6233)
- The v2 prompt still uses the generic work action schema rather than the eventual tiny patch contract. That is intentional for this slice, but it means timeout reduction is being pursued by context narrowing only, not by schema narrowing yet.

## Addendum: Live Task #402 Follow-Up

The new live evidence does **not** make this slice a dead end. Prompt size dropped materially (`~42k -> ~20k`, with `tool_context_chars` also reduced), so this is still worth landing as **bounded progress** rather than abandoning.

But it is also clearly **not sufficient** by itself: the live sample is still `100% work-loop-model-failure.request_timed_out` and `compiler_bundles` is still `0`, so this slice should be treated as a preparation step, not the fix. The correct next move is still a smaller dedicated write-ready draft lane / tiny draft call, not rollback of this v2 reduction.
