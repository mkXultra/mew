# M6.11 Draft-Timeout Phase Review — Claude

**Date:** 2026-04-22
**Branch:** main (uncommitted working tree, 1 commit ahead of origin)
**Scope:**
- `src/mew/work_session.py`
- `src/mew/commands.py`
- `src/mew/dogfood.py`
- `tests/test_work_session.py`
- `tests/test_dogfood.py`
- `tests/fixtures/work_loop/recovery/401_exact_windows_timeout_before_draft/scenario.json`

## Verdict: **approve_with_nits**

The phase is structurally correct and safe to commit. It replaces generic
`replan` with a guarded `resume_draft_from_cached_windows` recovery item
for write-ready timeouts that preserve the cached edit frontier,
threads a blocker-sourced `preferred_action` into
`work_recovery_suggestion_from_plan`, surfaces a matching follow-status
suggestion, and promotes `m6_11-draft-timeout` from `not_implemented` to
an 18-check honest scenario. Targeted runs all pass:

- `pytest tests/test_work_session.py -q` → **488 passed, 24 subtests**
- `pytest tests/test_dogfood.py -q` → **80 passed, 8 subtests**
- `pytest tests/ -q` (full suite) → 1374 passed, 3 pre-existing failures
  in `test_desk.py`, `test_dream.py`, `test_self_memory.py` confirmed
  present on HEAD via `git stash` reproducer — **not introduced by this
  phase**.

The nits below are low severity and should not block the commit.

## Findings

### 1. [LOW — structural] Redundant `if turn.get("status") in {"interrupted", "failed"}` guard
- **Where:** `src/mew/work_session.py:4404–4416`
- **Issue:** The loop now reads
  ```python
  for turn in turns:
      if (turn.get("status") not in {"interrupted", "failed"}) or turn.get("recovery_status"):
          continue
      if turn.get("status") in {"interrupted", "failed"}:  # always True here
          timeout_recovery_turn_plan_item = _timeout_before_draft_model_recovery_plan_item(...)
          if timeout_recovery_turn_plan_item:
              items.append(timeout_recovery_turn_plan_item)
              continue
      if turn.get("status") != "interrupted":
          continue
      # ... existing replan handling for interrupted
  ```
  The second `if status in {"interrupted", "failed"}` is always true at
  that point and can be dropped.
- **Why it matters:** Reader friction — the stacked guards obscure that
  the new branch runs for both statuses and the existing branch only for
  `interrupted`. A future maintainer might wrongly infer the middle
  guard filters something.
- **Concrete fix:** Flatten to a single pass:
  ```python
  for turn in turns:
      status = turn.get("status")
      if status not in {"interrupted", "failed"} or turn.get("recovery_status"):
          continue
      timeout_item = _timeout_before_draft_model_recovery_plan_item(...)
      if timeout_item:
          items.append(timeout_item)
          continue
      if status != "interrupted":
          continue
      if turn.get("tool_call_id") in interrupted_tool_ids:
          continue
      items.append({... "action": "replan" ...})
  ```

### 2. [LOW — ergonomics] Timeout recovery item skips the dedup helper
- **Where:** `src/mew/work_session.py:4413–4414`
- **Issue:** The new item is appended via `items.append(...)` directly,
  while the tiny-draft item (`_append_unique_recovery_plan_item`, used at
  line 5271+) and other append sites guard against duplicates.
  If a session has multiple failed/interrupted write-ready turns that all
  meet the timeout criteria, the recovery plan gets one
  `resume_draft_from_cached_windows` item per turn. The plan is then
  trimmed to `items[-limit:]` at line 4435, so absolute safety is
  preserved, but the plan may surface N near-identical items whose only
  differences are `model_turn_id`/`source_summary`.
- **Why it matters:** Cosmetic inflation of the plan; downstream
  `work_recovery_suggestion_from_plan` picks `matching_items[-1]` for the
  preferred action so the user-facing suggestion is still correct. But
  the raw `recovery_plan.items` list is noisier than necessary.
- **Concrete fix:** Route the append through
  `_append_unique_recovery_plan_item` (or a small deduper keyed by
  `(action, active_work_todo_id)`) so at most one item is emitted per
  todo.

### 3. [LOW — API gap] `native_work_recovery_suggestion_from_plan` has no explicit branch
- **Where:** `src/mew/runtime.py:837–869`
- **Issue:** The runtime's companion suggestion builder has explicit
  arms for `retry_tool`, `retry_verification`, `needs_user_review`,
  `retry_apply_write`, `verify_completed_write`, and `replan` but not
  for `resume_draft_from_cached_windows`. It falls through to the
  generic branch:
  ```python
  label = action.replace("_", " ") if action else "review"
  command = item.get("hint") or item.get("auto_hint") or item.get("review_hint") or ""
  ```
  which yields `label = "resume draft from cached windows"` and the
  plan item's `hint` command — functionally correct.
- **Why it matters:** The runtime notification text for this recovery
  reads "resume draft from cached windows" verbatim, which is acceptable
  but inconsistent with the hand-authored labels (e.g.
  "side-effect review", "verification recovery"). If an ops dashboard
  pattern-matches on labels, this falls into the "generic" bucket.
- **Concrete fix:** Add an explicit arm (one line) e.g.
  ```python
  elif action == "resume_draft_from_cached_windows":
      label = "write-ready draft resume"
  ```
  Not a regression — purely a polish item. `select_runtime_work_recovery_plan_item`
  and `prepare_runtime_native_work_tool_recovery` correctly no-op on this
  action (`tool_call_id` is absent by design, so the `safe_tool_only`
  gate fails fast — intentional since the resume requires model
  supervision).

### 4. [LOW — style] Four-space over-indent in the aggregate-test block
- **Where:** `tests/test_dogfood.py:604–612` (the `with … patch(...)` block)
- **Issue:** The tuple passed to `patch(...)` is now indented at 16
  columns where the surrounding `with` body uses 12. Python accepts it
  for implicit line continuation, but ruff would normally flag it and
  it's out of step with the rest of the file. Confirmed by reading the
  file — the `):` closing the `with` context manager is also
  over-indented.
- **Why it matters:** Cosmetic; local acceptance ran ruff clean,
  suggesting the `--extend-select` scope doesn't include this rule —
  but the diff noise distracts from the semantic change.
- **Concrete fix:** Re-dedent by 4 spaces so the tuple aligns with
  `"mew.dogfood.DOGFOOD_SCENARIOS",`.

### 5. [LOW — coverage gap] No test for `preferred_action` override against a higher-priority sibling
- **Where:** `src/mew/commands.py:2198–2203`; new test
  `tests/test_work_session.py:966–991`
- **Issue:** The new unit test exercises the happy path (plan has a
  single `resume_draft_from_cached_windows` item → returned). It does
  NOT exercise the more interesting override semantic: a plan with
  *both* a higher-priority action (e.g. `retry_verification` or
  `needs_user_review`) **and** a `resume_draft_from_cached_windows`
  item, where `preferred_action="resume_draft_from_cached_windows"`
  should still pick the resume item instead of the default priority
  winner.
- **Why it matters:** The `preferred_action` threading is the load-bearing
  change in `commands.py`; without a test that pits it against a
  higher-priority item, a future regression that ignores
  `preferred_action` would not be caught by this file.
- **Concrete fix:** Add a second unit test: plan with both items, assert
  `work_recovery_suggestion_from_plan(..., preferred_action="resume_draft_from_cached_windows")`
  returns the resume item and that the same plan without the
  `preferred_action` kwarg returns the higher-priority item.

### 6. [NIT — scenario loose acceptance] `snapshot_status_is_stale` accepts stale/overdue/dead
- **Where:** `src/mew/dogfood.py:963–969`
- **Issue:** The check name asserts `_is_stale`, but the body accepts
  `{"stale", "overdue", "dead"}`. In this fixture (no producer PID,
  `heartbeat_at = 2026-04-22T00:00:05Z`) only `stale` is reachable:
  `overdue` needs a live producer + `phase=="planning"`; `dead` needs a
  recorded producer. Verified by running the scenario and confirming
  `follow_status == "stale"`.
- **Why it matters:** Name/shape mismatch invites future fixture
  changes to land in a silently-widened check. The loose set is not
  wrong, just slightly over-permissive for the fixture.
- **Concrete fix:** Tighten to `== "stale"` to match both the name and
  the test's own `self.assertEqual(scenario["artifacts"]["follow_status"], "stale")`
  at `tests/test_dogfood.py:543`.

### 7. [NIT — scenario] `--auto-recover-safe` hint substring check is brittle to flag order
- **Where:** `src/mew/dogfood.py:935–941`, check
  `m6_11_draft_timeout_recovery_resume_hint_has_exact_roots`
- **Issue:** The assertion uses `"--allow-read src/mew/work_session.py"
  in resume_recovery_hint`. If a future builder changes arg order or
  adds quoting for paths with special chars, this substring test would
  break in a way that looks like a correctness regression. Today the
  paths are bare simple paths so `shlex.quote` is a no-op.
- **Why it matters:** Low today, but the test is coupled to exact
  string formatting rather than structural parsing.
- **Concrete fix:** Optional — use `shlex.split(resume_recovery_hint)`
  and assert the sequence of `("--allow-read", expected_path)` pairs is
  present. Not required for this commit.

### 8. [NIT — scenario] Unreachable `task_id_text is None` branch (carried over)
- **Where:** `src/mew/dogfood.py:703–709`
- **Issue:** Same pattern called out in the drafting-recovery scenario:
  `task_id_text = None` reaches `_scenario_command("work", None, ...)`
  which would raise `TypeError` in subprocess. The fixture's
  `task_id=401` keeps it unreachable today.
- **Why it matters:** Redundant defensive code that produces a broken
  invocation if ever exercised.
- **Concrete fix:** Drop the `elif task_id is None` branch and assert
  `task_id is not None` at fixture load.

## Residual risks / test gaps

- **Pre-existing failures elsewhere:** `test_desk`, `test_dream`, and
  `test_self_memory` each have one unrelated failure on `main`. They
  do not touch `work_session.py`, `commands.py`, or `dogfood.py`. Not
  blocking this phase, but worth a separate triage before the next
  release-ish commit.
- **Runtime notification label:** `native_work_recovery_suggestion_from_plan`
  will emit the generic fallback label/command for this action (see
  Finding 3). If passive runtime cockpit users rely on a hand-crafted
  label, they'll see the underscore-derived one until Finding 3 is
  addressed.
- **Multi-turn proliferation:** A session with multiple failed/interrupted
  write-ready turns that all meet the timeout criteria will accumulate
  one `resume_draft_from_cached_windows` item per turn (Finding 2). Not
  visible in the fixture (single turn), but reachable in production.
- **`_is_write_ready_timeout_candidate_turn` "timeout" substring match**
  (`work_session.py:4542–4543`) is case-insensitive and matches any
  token containing `"timeout"` in `summary`/`error`. This is appropriately
  narrow for the current failure-reporting vocabulary but would drift
  if future failure summaries use e.g. "timed-out" — confirm with the
  failure-recording producer that "timeout" is the canonical token.
- **Coverage of the override branch in `work_recovery_suggestion_from_plan`**
  is thin (Finding 5). Worth adding before the preferred_action
  pathway sees additional callers.

## Final recommendation

**Ship it.** The structural shape is correct, the new helper is
appropriately narrow (4 guard conditions before producing the item),
and the dogfood scenario is substantively honest (18 checks covering
blocker code, blocker detail, todo identity, cached-window frontier
parity between resume and follow-status, suggested-recovery shape, and
recovery-plan replacement of `replan`). Address Findings 1–5 opportunistically
in a follow-up tidy slice; Findings 6–8 can ride along or be left for a
later scenario pass.
