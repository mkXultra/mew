# M6.11 Tiny Reasoning-Low — Actual-Code Review (Claude, final)

Subject: the current uncommitted diff on `main` implementing the
tiny write-ready draft lane reasoning-effort override to `"low"`.
Files: `src/mew/work_loop.py`, `tests/test_work_session.py`.

## Current verdict (third pass)

**Commit-ready.** Both prior findings are addressed. Diff hash moved
from `0cbd2c14…` (findings open) to `2f3651f4…` (findings fixed).
All 7 tiny-lane tests pass; full `tests/test_work_session.py`
passes (461 passed, 7 deselected by testmon cache, 19 subtests
passed, 28s).

## Status timeline

| Pass | Diff md5 | Finding #1 (env_override) | Finding #2 (sink) | Verdict |
| --- | --- | --- | --- | --- |
| 1 (proposal review) | n/a | not raised | not raised | Approve |
| 2 (first actual-code) | `0cbd2c14` | open | open | Revise |
| 3 (re-inspection, no change) | `0cbd2c14` | open | open | Revise |
| 4 (this pass) | `2f3651f4` | **fixed** | **fixed** | **Commit-ready** |

## Finding #1 — env_override semantics — resolved

The implementer chose **Option 1** from the prior review (thread
the policy `source` into the tiny lane, pass through the inherited
effort when `source == "env_override"`). Concretely:

- New keyword-only parameter `reasoning_effort_source=""` on
  `_attempt_write_ready_tiny_draft_turn`
  (`src/mew/work_loop.py:1529`).
- Logic at `work_loop.py:1535`-`:1546`:
  - `inherited_source = reasoning_effort_source or "auto"` — treats
    empty/unknown source as `"auto"`, matching the default path.
  - If `inherited_source == "env_override"`, the *effective* effort
    used inside `codex_reasoning_effort_scope` is the caller's
    inherited effort; otherwise it is the module constant `"low"`.
  - Effective source is recorded as `"env_override"` or
    `"tiny_draft_auto_override"` so downstream readers can tell
    which branch fired.
- Scope call at `work_loop.py:1581` now uses the computed effective
  effort.
- Caller forwards `reasoning_effort_source=reasoning_policy.get(
  "source") or ""` at `work_loop.py:2748`.
- Pre-model mirror at `work_loop.py:2710`-`:2725` replicates the
  same conditional so the sink sees the same effective value and
  source before the tiny call runs. Python precedence on
  `a or "" if cond else b` parses as `(a or "") if cond else b`,
  which is the intended semantics; verified by the new tests.
- Four metrics keys now surface on every tiny-lane attempt:
  - `tiny_write_ready_draft_reasoning_effort` — what the call
    actually used.
  - `tiny_write_ready_draft_reasoning_effort_source` — `"env_override"`
    or `"tiny_draft_auto_override"`.
  - `tiny_write_ready_draft_inherited_reasoning_effort` — caller's
    raw effort.
  - `tiny_write_ready_draft_inherited_reasoning_effort_source` —
    caller's raw source (`"auto"`, `"env_override"`, etc.).

Behavior matrix is now what Finding #1 asked for:

| Caller source | Caller effort | Tiny lane scope effort | Fallback THINK |
| --- | --- | --- | --- |
| `auto` | `medium` | `low` | `medium` |
| `auto` | `high` | `low` | `high` |
| `env_override` | `xhigh` | `xhigh` | `xhigh` |

Operator intent is preserved end-to-end on env_override; the `low`
calibration cohort is clean because env_override bundles are
self-tagged via `tiny_write_ready_draft_reasoning_effort_source`
and can be excluded from post-slice dominant-share analysis
mechanically rather than by manual bundle filtering.

Test coverage:
`test_tiny_write_ready_draft_reasoning_effort_respects_auto_and_env_override_source`
(`tests/test_work_session.py:7161`) runs three subtests —
`(auto, medium, "low", tiny_draft_auto_override)`,
`(auto, high, "low", tiny_draft_auto_override)`,
`(env_override, xhigh, "xhigh", env_override)` — asserting both
what `codex_reasoning_effort_scope` was entered with and all four
new metrics keys on each. The `xhigh` case is the regression that
was missing from the prior diff and is now directly locked in.

## Finding #2 — pre_model_metrics_sink coverage — resolved

The new test
`test_tiny_write_ready_draft_pre_model_sink_records_reasoning_effort_context`
(`tests/test_work_session.py:7208`) actually exercises the sink:

- Passes `pre_model_metrics_sink=capture_pre_model_metrics` to
  `plan_work_model_turn`.
- Asserts `pre_model_payloads[0]` (the pre-tiny-call emission) has
  the four reasoning-effort keys with the expected
  auto→`"low"`/env_override→pass-through values.
- Asserts `"tiny_write_ready_draft_exit_stage" not in
  pre_model_payloads[0]` — a clever invariant that confirms the
  payload is the pre-model snapshot (exit_stage is only populated
  after the tiny call returns via `_finalize_tiny_draft_metrics`).
- Runs two subtests (auto + env_override) so the pre-model mirror
  block's conditional is exercised on both branches.

If the pre-model mirror at `work_loop.py:2710`-`:2725` were
deleted, the first subtest would fail because
`pre_model_payloads[0]` would not contain the new keys. This is
exactly what Finding #2 asked for.

The test also re-asserts on the final `planned["model_metrics"]`
after the tiny call fails over, preserving the original contract
check without losing it.

## Validation

- `uv run python -m pytest -q tests/test_work_session.py -k
  'tiny_write_ready_draft'` → `7 passed, 461 deselected, 5 subtests
  passed` (0.69s).
- `uv run python -m pytest -q tests/test_work_session.py` → `461
  passed, 7 deselected, 19 subtests passed` (28s). No failures, no
  flake this run. (The 7 deselected are pytest-testmon cache hits,
  not skips; previously-seen timing flake on
  `test_work_loop_model_calls_enforce_hard_timeout_without_retries`
  did not fire this pass.)

## Residual style notes (non-blocking)

- The pre-model mirror block at `work_loop.py:2710`-`:2725`
  duplicates the effort/source decision already made inside the
  helper. Extracting a small pure function
  `_resolve_tiny_reasoning_effort(reasoning_policy)` returning
  `(effort, source)` would remove the duplication and make the
  intent legible in one place. Optional cleanup; not required for
  this commit.
- The compact ternary `reasoning_policy.get("effort") or "" if
  cond else CONST` relies on Python's conditional-expression
  precedence rules. Correct, but `((reasoning_policy.get("effort")
  or "")) if cond else CONST` with explicit parentheses is easier
  to read and eliminates any doubt during future edits. Either is
  fine.
- The `v2 → v3` prompt contract version bump is unchanged from the
  prior pass. The tiny prompt *text* is still the same; the bump
  functions as a cohort label for manual grouping. With the new
  `tiny_write_ready_draft_reasoning_effort_source` now providing a
  cleaner cohort split, the v3 label is redundant but harmless.
  Keep or drop per commit-message clarity.

## Summary

Both load-bearing findings from the prior passes are addressed by
real code, not by prose. The env_override escape hatch is preserved
through the tiny lane, its presence is self-reported in metrics,
and the pre-model sink is now a tested contract rather than an
untested claim. No new findings surfaced on this pass.

**Commit-ready.** Safe to land as a single commit titled roughly
`Force M6.11 tiny draft lane to low reasoning effort, honoring
env_override` or similar. Suggest noting the env_override
pass-through in the commit message so operators and calibration
reviewers know to expect `tiny_write_ready_draft_reasoning_effort_source`
in the bundles.

## Re-inspection footer

Pass 4 transitions the verdict from Revise to Commit-ready. If any
subsequent change happens to the diff before the commit is taken,
another pass should be requested; this doc should stay updated in
place so the timeline table remains the single source of truth.
