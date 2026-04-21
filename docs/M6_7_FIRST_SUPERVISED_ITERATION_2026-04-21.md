# M6.7 First Supervised Iteration 2026-04-21

Status: passed.

This document records the first bounded reviewer-gated M6.7 self-hosting
iteration.

## Iteration Shape

- task: `#364` `M6.7 first supervised loop: visible scope fence`
- session: `#352`
- reviewer: Codex
- implementer: mew native work session
- scope fence: `src/mew/work_session.py`, `tests/test_work_session.py`
- explicit non-goals: `ROADMAP.md`, `ROADMAP_STATUS.md`, `docs/`, and
  unrelated files

## Drift Canary

Ran before the iteration:

```bash
uv run pytest -q \
  tests/test_work_session.py::WorkSessionTests::test_work_accept_edits_escalates_self_improve_governance_edit \
  tests/test_work_session.py::WorkSessionTests::test_work_session_does_not_persist_sensitive_write_roots \
  --no-testmon
```

Result: `2 passed in 0.27s`

## Reviewer-Gated Run

The live run started with bounded guidance and write roots limited to
`src/mew` and `tests`. mew stayed inside the declared surface:

1. searched only the two scoped files
2. read exact anchored windows in those same files
3. produced a paired dry-run diff
4. stopped on pending approval
5. after reviewer approval, ran focused verification, then broader module
   verification
6. performed a same-surface audit in `src/mew/work_session.py`
7. finished with an explicit audit conclusion

Reviewer actions:

- approved dry-run test edit `#2795`
- approved dry-run source edit `#2796`
- no direct reviewer code edits

## Change Landed

Files changed:

- `src/mew/work_session.py`
- `tests/test_work_session.py`

Behavior added:

- `build_work_session_resume()` now exposes `declared_write_roots`
- `format_work_session_resume()` now renders a `Declared write roots` section

## Verification

Focused verifier after approval:

```bash
uv run pytest -q tests/test_work_session.py -k 'declared_write_scope' --no-testmon
```

Result: `1 passed, 415 deselected in 0.33s`

Broader verifier before finish:

```bash
uv run python -m unittest tests.test_work_session
```

Result: `Ran 416 tests ... OK`

Additional reviewer checks after the run:

```bash
uv run ruff check src/mew/work_session.py tests/test_work_session.py
uv run python -m py_compile src/mew/work_session.py tests/test_work_session.py
git diff --check
```

Result: pass

## Why This Counts

This iteration satisfies the first M6.7 gate item:

- one bounded roadmap task
- reviewer-gated dry-run approval surface
- usable proof artifact
- no reviewer rescue edits

It also provides partial proof for the remaining M6.7 items:

- proof-or-revert: present in process, but not yet an explicit enforced credit
  gate
- scope fence: present through declared write roots plus reviewer-bounded task
  scope, but not yet a dedicated M6.7 enforcement mechanism

## Next Gap

The next M6.7 task should harden one of these partial items directly:

1. explicit proof-or-revert enforcement
2. explicit scope-fence enforcement beyond visible declared write roots
