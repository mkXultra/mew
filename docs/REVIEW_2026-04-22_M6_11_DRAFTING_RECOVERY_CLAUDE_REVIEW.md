# M6.11 Drafting Recovery Slice Review — Claude (re-review)

**Date:** 2026-04-22 (revision 2)
**Branch:** main (uncommitted working tree)
**Scope:** `src/mew/dogfood.py`, `tests/test_dogfood.py`,
`tests/fixtures/work_loop/drafting_recovery/blocker_code_parity/scenario.json`
**Prior commit:** 8303098 (registered scenario as `not_implemented`)
**Previous review:** same file, revision 1 (8 checks, 7 findings)

## Verdict: **approve** — commit-ready

The follow-up edits materially strengthen the slice: the scenario now runs
**15 checks** (was 8) covering full `active_work_todo` payload equality,
`next_action` text parity, `suggested_recovery` reason + shape parity,
`snapshot status == "stale"`, and an explicit assertion that the overlay
is selected via the *equal-timestamp "richer resume"* branch rather than
the "session newer" branch. The fixture was also made self-consistent
(session and snapshot both at `2026-04-22T00:00:10Z`) and the in-place
`setdefault` mutation was replaced with a shallow copy. All 80 dogfood
tests pass locally (`.venv/bin/python -m pytest tests/test_dogfood.py -o
addopts=""`), and `m6_11-draft-timeout`, `m6_11-refusal-separation`,
`m6_11-phase4-regression` remain honestly `not_implemented`.

Live scenario artifacts (captured via `run_dogfood_scenario`):

```json
{
  "blocker_code": "ambiguous_old_text_match",
  "blocker_detail": "Deterministic offline blocker for parity assertion.",
  "next_recovery_action": "narrow_old_text",
  "next_action": "inspect the active patch blocker and refresh the exact cached windows or todo source before retrying",
  "todo_id": "todo-recovery-parity-01",
  "resume_source": "session_overlay",
  "session_state_newer": false,
  "session_id": 402,
  "task_id": 402,
  "follow_status": "stale",
  "command_exit_code": 0,
  "suggested_recovery_kind": "needs_human_review"
}
```

### Prior-review findings — disposition

| # | Finding (rev 1) | Status | Notes |
|---|---|---|---|
| 1 | Scenario name overstates scope | **Deferred** | Name unchanged; fixture dir still `blocker_code_parity`. New checks broaden to overlay-propagation parity but don't exercise a recovery transition. Acceptable for this bounded slice. |
| 2 | "Parity" shares a source of truth | **Mitigated** | follow-status still calls `build_work_session_resume` internally, but the new full-object `active_work_todo_matches`, `next_action_matches`, `suggested_recovery_*` checks now catch any filtering/post-processing drift in follow-status. Single-path semantics unchanged. |
| 3 | Unreachable `task_id_text is None` branch | **Not fixed** | `src/mew/dogfood.py:741–747` still present. |
| 4 | Fixture dict mutated in place | **Fixed** | `dogfood.py:752` now uses `dict(follow_payload)`. |
| 5 | `command_succeeds` ignored snapshot status | **Fixed** | New check `m6_11_drafting_recovery_snapshot_status_is_stale` (`dogfood.py:906–912`) locks status to `"stale"`. |
| 6 | Snapshot pre-overlay phase never observed | **Mitigated** | New `m6_11_drafting_recovery_equal_timestamp_overlay_path` (`dogfood.py:880–888`) forces `session_state_newer=False` and still demands `resume_source=="session_overlay"`, which only holds when `_work_follow_status_resume_is_richer` fires — which requires snapshot `phase=="drafting"` + session `phase=="blocked_on_patch"`. Indirect but load-bearing. A direct raw-snapshot assertion is still nice-to-have. |
| 7 | Tuple ordering inconsistency | **Not fixed** | Production `DOGFOOD_SCENARIOS` still orders `drafting-recovery` after `refusal-separation` (`dogfood.py:77–81`); test mock keeps the alphabetical reorder. Functionally irrelevant; stylistic. |

## Remaining findings

### 1. [LOW — robustness] Unreachable `task_id_text is None` branch is still a footgun
- **Where:** `src/mew/dogfood.py:741–747`
- **Issue:** The branch sets `task_id_text = None`, which is then passed as an
  element of argv to `_scenario_command(...)`, yielding
  `[python, -m, mew, "work", None, ...]`. subprocess rejects `None`
  positional args with `TypeError`.
- **Why it matters:** Unreachable with today's fixture (`task_id=402`), but
  any future fixture that omits `task_id` would fail with an opaque
  TypeError rather than a clear scenario message. Cost to eliminate is tiny.
- **Concrete fix:** Replace the three-branch block with
  `task_id_text = str(task_id)` guarded by an `assert task_id is not None,
  "drafting_recovery fixture must set task_id"`, or split the command line
  so no positional is emitted when `task_id is None`.

### 2. [LOW — coverage] Only the "equal + richer" overlay branch is exercised
- **Where:** fixture `follow_snapshot.session_updated_at = "2026-04-22T00:00:10Z"`,
  matching `session.updated_at`; also `dogfood.py:755` now defaults to
  `session.get("updated_at")` rather than a fixed prior time.
- **Issue:** The previous revision drove the `session_state_newer` branch.
  This revision deliberately drives the `session_state_equal AND
  _work_follow_status_resume_is_richer` branch. Both production scenarios
  exist (stale snapshot vs state that advanced), but only one is covered.
- **Why it matters:** A regression that e.g. inverts the `>` in
  `_work_follow_status_session_state_newer` (`commands.py:6564`) would
  still leave this test green, because that branch is never consulted.
- **Concrete fix:** Add a sibling fixture variant (e.g.
  `session_state_newer` directory) that keeps the snapshot
  `session_updated_at` strictly older than `session.updated_at` and asserts
  `session_state_newer is True` and `resume_source == "session_overlay"`.
  Both dogfood scenarios can iterate `_iter_fixture_dirs` like
  `m6_11-compiler-replay` already does.

### 3. [LOW — semantics] "Parity" shares one codepath
- **Where:** `src/mew/commands.py:6797` (`session_resume =
  build_work_session_resume(session, task=session_task, state=state)`);
  `src/mew/dogfood.py:770` re-invokes the same function.
- **Issue:** When both sides originate from the same call, full-object
  equality is close to a tautology; its strength is bounded by the code
  between that call and follow-status's JSON emit (`commands.py:6822–6886`).
- **Why it matters:** The new `active_work_todo_matches`,
  `next_action_matches`, and `suggested_recovery_*` checks do legitimately
  cover that middle layer. But a reviewer taking the slice's "parity"
  framing at face value may expect independent implementations. Worth a
  line of wording in ROADMAP or the fixture README to set expectations.
- **Concrete fix:** Either (a) document that the scenario proves
  *overlay-propagation parity*, not two-implementation parity; or
  (b) eventually add a second parity source (e.g., a real producer run
  that produces a snapshot, compared against `build_work_session_resume`
  of the same session — this belongs in a later slice).

### 4. [LOW — robustness] `os.chdir` wraps `build_work_session_resume`
- **Where:** `src/mew/dogfood.py:767–772`
- **Issue:** Temporarily mutates process-global cwd. Precedent exists at
  `dogfood.py:8245–8309` (verifier-confidence scenario), so it's not a new
  pattern; still, the try/finally pair protects only against exceptions
  inside `build_work_session_resume`. `pytest-xdist` parallel workers would
  serialize within a worker but would race if another test in the same
  process touches `os.chdir`.
- **Why it matters:** Low risk today (no xdist usage detected, tests run
  serially in a single process). Flagging for durability.
- **Concrete fix:** If `build_work_session_resume`'s cwd-sensitivity is
  only for path resolution inside the fixture's `target_paths`, consider
  passing an explicit `workspace` parameter through the call instead of
  relying on cwd. Out of scope for this slice.

### 5. [LOW — hermeticity] `suggested_recovery.command` is host-absolute
- **Where:** `src/mew/dogfood.py:897–903`; observed value
  `"/Users/mk/dev/personal-pj/mew/mew work 402 --session --resume ..."`.
- **Issue:** The check asserts only non-empty, so it is portable. But the
  embedded absolute path means anyone inspecting artifacts across
  machines/CI will see environment-specific strings.
- **Why it matters:** Cosmetic for this scenario, but will complicate
  diffing or snapshotting recovery commands in richer future dogfood
  scenarios.
- **Concrete fix:** None required here; future scenarios that snapshot the
  command string should canonicalize to a relative `mew` invocation.

### 6. [TRIVIAL — style] Production tuple order diverges from test mock
- **Where:** `src/mew/dogfood.py:77–81` (production) vs
  `tests/test_dogfood.py:603–607`, `:624–629` (mock).
- **Issue:** Same as rev 1 — the test mock alphabetizes m6_11 entries; the
  production tuple does not.
- **Concrete fix:** Reorder the production tuple to match; both the set
  comparison and the `assertIn` on formatted text are order-insensitive,
  so the change is safe.

## Residual risks

- **Single overlay branch:** With `session_state_newer` now always `False`
  in this fixture, regressions in the "session newer" gating are invisible
  to the scenario. See Finding 2.
- **Self-referential parity:** follow-status and the dogfood scenario share
  `build_work_session_resume` as the ultimate producer. See Finding 3.
- **Cwd fragility:** `os.chdir` in `run_m6_11_drafting_recovery_scenario`
  is correct today but becomes load-bearing if parallel test execution is
  ever introduced. See Finding 4.
- **State-shape drift:** The fixture hand-assembles `tasks` and
  `work_sessions` on top of `default_state()` without passing through
  `migrate_state(...)`. If required state keys are added in the future
  (e.g., a new `schema_version` gate), the scenario will desync silently.
- **Stale-status coupling:** The scenario asserts
  `status == "stale"`. If `_work_follow_status_from_snapshot`'s freshness
  heuristic (`commands.py:6777`) is retuned (e.g., widens the 10s
  threshold or introduces a "fresh-without-pid" case), this check will
  fail and require a fixture update.

## Suggested validation additions

1. **Add a `session_state_newer` fixture variant** (one new directory
   under `drafting_recovery/`) with `follow_snapshot.session_updated_at`
   strictly older than `session.updated_at`; assert
   `session_state_newer is True` and `resume_source == "session_overlay"`.
   This closes the coverage gap described in Finding 2 and brings the
   scenario in line with `m6_11-compiler-replay`'s multi-fixture pattern.
2. **Assert raw pre-overlay snapshot phase** by reading `follow_path`
   directly (or by adding the raw JSON to the scenario artifacts) and
   checking `resume.phase == "drafting"`. Complements the indirect
   equal-timestamp check.
3. **Lock `suggested_recovery.command` shape** to a pattern, e.g.
   `endswith("--session --resume --allow-read . --auto-recover-safe")`,
   so recovery-command regressions surface cleanly.
4. **Remove the unreachable `task_id_text is None` branch** per Finding 1
   to shrink the scenario's failure surface.
5. **Align the production `DOGFOOD_SCENARIOS` order with the test mock**
   per Finding 6 (trivial).
6. **Document in ROADMAP_STATUS.md or a fixture README** that this slice
   proves *follow-status overlay propagation parity*, not two-implementation
   parity — aligns wording with what the 15 checks actually cover
   (Finding 3).

None of the remaining findings block the commit; items 1 and 4 are the
highest value follow-ups for the next slice.
