# M6.11 Phase 1 WorkTodo Claude Review

## Scope

Re-reviewed the uncommitted Phase 1 first slice after the latest fixes:
- [`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py)
- [`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py)
- [`docs/REVIEW_2026-04-22_M6_11_PHASE1_WORKTODO_IMPL.md`](/Users/mk/dev/personal-pj/mew/docs/REVIEW_2026-04-22_M6_11_PHASE1_WORKTODO_IMPL.md)

The prior review flagged eight findings (two echoing [`docs/REVIEW_2026-04-22_M6_11_PHASE1_WORKTODO_CODEX_REVIEW.md`](/Users/mk/dev/personal-pj/mew/docs/REVIEW_2026-04-22_M6_11_PHASE1_WORKTODO_CODEX_REVIEW.md)). All eight are addressed to the extent required by the Phase 1 "smallest persisted skeleton" scope. No new blocker-level issues were found. A handful of residual risks remain around stale session state, forward-compatibility, and uncovered corners; they are enumerated in the final section and are acceptable for a first slice but worth capturing before Phase 2.

## Verdict

- **All 8 prior findings: resolved** at the code path and covered by tests, with two caveats for findings #2 and #8 called out below.
- No regressions introduced by the fixes.
- I did not run the test suite for this review; validation is static reading plus the impl note's own validation block.

## Findings Resolution

### 1. High: Phase 0 draft observability regression — RESOLVED

- `_build_draft_state_from_turns()` now populates `draft_runtime_mode`, `draft_prompt_contract_version`, `draft_prompt_static_chars`, `draft_prompt_dynamic_chars`, and `draft_retry_same_prefix` from the latest `write_ready_fast_path` turn **before** checking for an `active_work_todo` ([`src/mew/work_session.py:4544-4553`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L4544)). The todo branch at lines 4554-4568 only overrides `draft_phase`, `draft_attempts`, `cached_window_ref_count`, and `cached_window_hashes`, leaving the Phase 0 fields intact on return.
- Test [`test_build_work_session_resume_prefers_persisted_active_work_todo`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L6944) now pins the intended behavior: with a `blocked_on_patch` todo and a `write_ready_fast_path=True` turn, it asserts `draft_runtime_mode="guarded"`, `draft_prompt_contract_version="v1"`, `draft_prompt_static_chars=100`, `draft_prompt_dynamic_chars=200`, and `draft_retry_same_prefix=True` ([`tests/test_work_session.py:7038-7042`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L7038)).

### 2. High: Stale `active_work_todo` outliving the working-memory frontier — RESOLVED (with a narrow caveat)

- `_observe_active_work_todo()` now has three exclusive branches ([`src/mew/work_session.py:4479-4529`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L4479)):
  - **Ignore**: `candidate == {}` (first plan item not `edit_ready`, or target paths/cached windows missing) → return `{}` without writing to `session`. The resume path then feeds `active_work_todo={}` into `_build_draft_state_from_turns` and `work_session_phase`, which correctly falls through to `idle`.
  - **Replace**: frontier key changes → mint a new ordinal and overwrite the persisted todo ([lines 4506-4509](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L4506)).
  - **Merge**: frontier key matches → fold the fresh `source` and `cached_window_refs` into `existing` and only write back when the normalized shape actually changed ([lines 4511-4528](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L4511)).
- Tests cover both new branches:
  - [`test_build_work_session_resume_ignores_stale_active_work_todo_when_frontier_is_not_edit_ready`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L7055) asserts `resume["phase"] == "idle"`, `resume["active_work_todo"] == {}`, `resume["draft_phase"] == ""`, the formatter omits the `active_work_todo:` line, **and** `session == before` (proving the stale todo was not mutated).
  - [`test_build_work_session_resume_replaces_stale_active_work_todo_on_frontier_change`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L7111) asserts the replacement mints `todo-1-2`, bumps `last_work_todo_ordinal` to 2, and flips phase back to `drafting`.
- **Caveat**: the ignore branch deliberately does **not** clear `session["active_work_todo"]`. The resume path correctly ignores the stale entry (because the observer now returns `{}` and both downstream consumers honor the explicit kwarg), but the on-session value lingers. In practice this is safe today because the only direct reader without the kwarg is the fallback at [`src/mew/commands.py:5035`](/Users/mk/dev/personal-pj/mew/src/mew/commands.py#L5035), and that fallback is unreachable whenever `resume.get("phase")` is truthy (which `build_work_session_resume` always guarantees). It is, however, a latent footgun for future callers — see residual risks below.

### 3. Medium: Todo phase masking fresher tool-failure state — RESOLVED

- `work_session_phase()` now short-circuits on `failed` **before** consulting the todo ([`src/mew/work_session.py:3915-3920`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L3915)). The ordering is:
  1. `awaiting_approval`, `running_tool`, `planning`, `interrupted` (pre-existing short-circuits)
  2. `failed` (line 3915, moved above the todo branch)
  3. `todo_phase` when status is in `WORK_TODO_PHASE_STATUSES` (line 3919)
  4. `idle` fallback
- [`test_work_session_resume_failure_beats_active_work_todo_phase`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L7260) pins the exact precedence: a failing `read_file` call alongside a `drafting` todo yields `phase="failed"`, `next_action="inspect the latest failure and decide whether to retry, edit, or ask the user"`, and `draft_phase="drafting"` (the draft-state surface is still populated so the caller can see both the fault and the in-flight todo).

### 4. Medium: Resume-time mutation of `session` — RESOLVED

- `_observe_active_work_todo()` no longer writes to `session` in the ignore branch (line 4501 `return {}`) or in the merge branch when the merge is a no-op (lines 4525-4528 guard the assignment on `normalized_updated != existing`). Mutation is now limited to the three substantive cases: first creation, frontier replacement, and merges that actually changed the shape.
- [`test_build_work_session_resume_creates_active_work_todo_for_edit_ready_frontier`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L7190) covers idempotence directly: it calls `build_work_session_resume(session)` twice in a row on the same session and asserts that the ordinal stays at 1 and that the second resume sees the same `active_work_todo.id` as the first ([lines 7257-7258](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L7257)).
- The ignore-branch "no mutation" guarantee is pinned by the `session == before` assertion on [`tests/test_work_session.py:7108`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L7108).

### 5. Low: Spurious `last_work_todo_ordinal` bumps on empty-id todos — RESOLVED

- `_next_active_work_todo_id(session)` is now invoked only at [line 4503](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L4503) (create) and [line 4507](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L4507) (frontier mismatch), never in the merge branch. The old `existing.get("id") or _next_active_work_todo_id(session)` pattern is gone. If an `existing` todo survives normalization with `id=""`, the merge branch preserves the empty id rather than consuming a new ordinal; not ideal but no longer a counter leak.

### 6. Low: New `drafting` / `blocked_on_patch` `next_action` strings — RESOLVED

- The exact strings are asserted by tests:
  - `drafting` → [`tests/test_work_session.py:7256`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L7256) (`"draft one bounded patch from the cached paired windows or record one exact blocker"`).
  - `blocked_on_patch` → [`tests/test_work_session.py:7043-7046`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L7043) (`"inspect the active patch blocker and refresh the exact cached windows or todo source before retrying"`).
- The `recovery_plan["next_action"]` override at [`src/mew/work_session.py:5064`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L5064) and `refresh_stale_memory_next_action` at [line 5066](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L5066) are still gated on `phase in ("interrupted", "idle", "failed")`, so neither new phase is clobbered. No test pins the guard semantics directly, but the `blocked_on_patch` test would catch a regression that widened the override set to include the new phases.

### 7. Low: `format_work_session_resume()` rendering of `active_work_todo` — RESOLVED

- Positive case: [`tests/test_work_session.py:7048-7053`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L7048) asserts the formatter emits `"active_work_todo: id=todo-1-1 status=blocked_on_patch draft_attempts=4"` and the `active_work_todo_plan_item:` continuation line.
- Negative case: [`tests/test_work_session.py:7109`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L7109) asserts the `active_work_todo:` prefix does **not** appear when `resume["active_work_todo"]` is empty.

### 8. Low: Unknown `status` silently dissolves the todo — RESOLVED (with caveat)

- `WORK_TODO_STATUSES` is now the full seven-status enum (`drafting`, `blocked_on_patch`, `awaiting_review`, `awaiting_approval`, `applying`, `verifying`, `completed` at [`src/mew/work_session.py:40-48`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L40)), and `WORK_TODO_PHASE_STATUSES` (line 49) correctly narrows phase derivation to the two Phase 1 statuses. Forward-compat with a Phase 2 binary writing `awaiting_review`/`applying`/`verifying`/`completed` is therefore preserved: the todo survives normalization, `work_session_phase()` falls through to `idle` for those statuses, and the draft state still reads `status` via the todo.
- **Caveat**: a genuinely unknown status string (e.g. from a corrupted state file or a much later binary) is still dropped silently at [line 4350](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L4350) with no log and no test. The practical surface of this is small — the seven valid statuses cover the whole planned enum — but the defensive drop behavior is worth a one-line comment or a structured log in Phase 2 when the enum may grow.

## Residual Risks / Test Gaps

These are not blockers for the first slice but should be picked up before Phase 2 locks in behavior:

- **Stale `session["active_work_todo"]` is never cleared** ([observer ignore branch](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L4500)). The resume path is safe because it passes `active_work_todo={}` to downstream consumers, but any future direct read of `session["active_work_todo"]` that does not go through `build_work_session_resume()` will see stale data. Today only [`src/mew/commands.py:5035`](/Users/mk/dev/personal-pj/mew/src/mew/commands.py#L5035) calls `work_session_phase()` without the kwarg, and it is shielded by `resume.get("phase") or …`, so the bug is unreachable — but nothing locks that contract in place. Recommend either clearing the persisted todo in the ignore branch or adding a comment at the observer call site that explains the "resume-only ignore" semantics.
- **`verify_command` silent overwrite in the merge branch** ([line 4512](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L4512)). `updated["source"] = candidate["source"]` replaces the persisted `verify_command` on every merge, even though the frontier key ignores it. This is almost certainly intentional (the design wants the newest verifier), but nothing pins the choice. If Phase 2 ever attaches multiple verifiers per plan item, the silent overwrite will be a subtle drift vector.
- **`cached_window_refs[*].window_sha1` drift is unguarded**. The existing test only asserts the sha1 *format* ([line 7254](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py#L7254)), not that the persisted hash still matches the live file window. The design defers the real check to Phase 2's `PatchDraftCompiler`, so this is known work, but Phase 1 can still persist a hash that diverges silently.
- **Legacy state round-trip untested**. `create_work_session()` initializes `active_work_todo: {}` for new sessions ([line 960](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L960)), and the read sites use `session.get("active_work_todo") or {}` / `int(session.get("last_work_todo_ordinal") or 0)`, so pre-Phase-1 on-disk JSON loads safely. A fixture-based round-trip test on a state file that predates these keys would be cheap insurance before Phase 2 adds any field that isn't tolerant to missing-key loads.
- **`commands.py:5035` phase contract is unpinned**. No test covers the `work_session_phase(session, calls, turns, pending_ids)` call without the `active_work_todo` kwarg. It is currently backward-compatible (the kwarg is optional and falls back to `session["active_work_todo"]`), but a future refactor that makes it required would silently break follow-status JSON. One direct test of that fallback would close the door.
- **Guard semantics for `recovery_plan["next_action"]` on the new phases are inferred, not asserted**. If a future change rewrites [line 5064](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py#L5064) to `if recovery_plan.get("next_action") and phase not in (...):`, the drafting guidance would be silently overwritten. A test with `recovery_plan["next_action"]` populated and `phase == "drafting"` that asserts the original drafting string survives would make this intent explicit.
- **Truly unknown `status` drop has no log or test**. As noted in Finding #8's caveat — the defensive drop is reasonable but silent.

## Validation Performed For This Review

- Static reading of the updated `work_session.py` at lines 40-49 (`WORK_TODO_STATUSES` / `WORK_TODO_PHASE_STATUSES`), 3896-3921 (`work_session_phase`), 4320-4529 (`_hash_value` through `_observe_active_work_todo`), 4532-4584 (`_build_draft_state_from_turns`), 4999-5067 (resume integration and `next_action` branches), and 5201-5221 (`format_work_session_resume`).
- Static reading of all new tests in [`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py) at 6830-7357 and cross-check against each finding.
- Cross-checked the impl note's "Review-Driven Corrections" bullets against the code and tests.
- Enumerated callers of `work_session_phase()` and `session["active_work_todo"]` to re-validate the Finding #2 caveat about session-state staleness.
- Did **not** run `uv run pytest` or `uv run ruff` — the impl note lists the expected validation commands but executing them was out of scope for this re-review.
