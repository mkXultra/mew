# M6.7 Sixth Supervised Iteration 2026-04-21

Status: passed.

This document records the fresh clean post-fix bounded M6.7 supervised
iteration that closes the short-loop proof gap after the live-verifier runtime
repairs.

## Iteration Shape

- task: `#374` `M6.7 sixth supervised loop: hide blocked stale work sessions from focus brief`
- session: `#362`
- reviewer: Codex
- implementer: mew native work session
- scope fence: `src/mew/brief.py`, `tests/test_brief.py`
- explicit non-goals: `ROADMAP.md`, `ROADMAP_STATUS.md`, `docs/`, and
  unrelated files

## Drift Canary

Ran before the iteration:

```bash
uv run pytest -q tests/test_brief.py -k "focus or brief or active_work_session" --no-testmon
```

Result: `50 passed in 0.56s`

## Reviewer-Gated Run

The live run stayed inside the declared brief/test surface and completed the
full reviewer-gated loop without reviewer rescue edits:

1. ran the drift canary first on the bounded brief surface
2. searched only the focused `build_focus_data()` / `build_brief_data()` /
   `active_work_session_items()` anchors and nearby brief regressions
3. read exact source and test windows in `src/mew/brief.py` and
   `tests/test_brief.py`
4. produced a paired dry-run diff
5. stopped for explicit reviewer approval
6. after reviewer approval, ran the focused verifier and then the broader
   `tests.test_brief` module verifier
7. performed a same-surface audit in `src/mew/brief.py`
8. finished with an explicit clean-audit conclusion

Reviewer actions:

- approved dry-run test edit `#2957`
- approved dry-run source edit `#2958`
- no reviewer code edits

## Change Landed

Files changed:

- `src/mew/brief.py`
- `tests/test_brief.py`

Behavior added:

- `active_work_session_items()` now skips tasks that are not actionable, so a
  stale blocked work session no longer appears as active work in
  `mew focus --kind coding` or `mew brief --kind coding`
- regression coverage now proves the stale blocked-session path falls back to
  the expected next useful move instead of treating the blocked item as live
  active work

## Verification

Focused verifier after approval:

```bash
uv run pytest -q tests/test_brief.py -k "focus or brief or active_work_session" --no-testmon
```

Result: `51 passed in 0.68s`

Broader verifier before finish:

```bash
uv run python -m unittest tests.test_brief
```

Result: `Ran 51 tests in 0.805s ... OK`

Additional reviewer checks after the run:

```bash
./mew focus --kind coding
./mew brief --kind coding
git diff --check
```

Result: pass; the stale blocked work-session surface no longer appears as live
active work, and both commands keep the expected checkpoint-recovery next move.

## Same-Surface Audit Conclusion

No additional sibling `brief.py` change was needed.

- The active-work filtering belongs in `active_work_session_items()`.
- `build_focus_data()` and `build_brief_data()` already consume that filtered
  surface and therefore inherit the corrected behavior without extra branching.
- The remaining blocked M6.6 tasks are still visible as open tasks in the
  broader brief output, which is acceptable because the regression targeted
  only the "active work session" surface.

## Why This Counts

This iteration provides the clean post-fix bounded proof that M6.7 still
lacked after the live-verifier runtime repairs:

- reviewer-gated dry-run approval surface
- focused and broader proof both passed inside the bounded loop
- no reviewer rescue edits
- same-surface audit completed before finish
- product behavior is visible through `mew focus` / `mew brief`, not only
  internal state

## Next Gap

The remaining M6.7 gate is the supervised 8-hour proof:

1. at least three real roadmap items
2. reviewer decisions recorded on each iteration
3. zero proof-or-revert failures
4. green drift canary throughout
