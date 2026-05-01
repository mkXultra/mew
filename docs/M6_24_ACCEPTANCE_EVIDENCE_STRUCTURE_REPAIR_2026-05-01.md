# M6.24 Acceptance Evidence Structure Repair - 2026-05-01

## Decision

Do not grow `acceptance_evidence.py` as a task-semantic parser for
`compile-compcert` or any other benchmark task.

The accepted structure is closer to Codex / Claude Code:

- terminal-success tool calls are the evidence base
- command shape and final-state proof are deterministic
- opaque shell/interpreter segments after proof are treated conservatively
- task-specific semantics stay outside the core acceptance substrate

## Trigger

The resource-normalized `compile-compcert` proof after vendored patch surgery
had valid external PASS trials, but an internal finish gate false-negative
blocked completion because the final artifact proof was multiline and included
earlier failed evidence refs.

The first repair draft started to add task-semantic output markers. That was
rejected as the wrong structural direction.

## Repair

Implemented a generic final-artifact evidence substrate:

- allow verified checks to cite earlier failed tool refs when a terminal-success
  ref for the same check exists
- require real artifact proof segments for output-based proof
- reject generated marker output from `echo`, `printf`, `awk`, `python`, `sh`
  and similar opaque generators without a real proof segment
- use exact path/token boundaries so `artifact.old` and unrelated absolute
  basename matches do not prove `artifact`
- allow normal build/install/chmod before a later final proof segment
- reject mutation, redirection, parent-glob removal, and opaque interpreter
  artifact references after the accepted proof segment
- support cwd-relative `artifact` / `./artifact` only when the cwd is the
  artifact parent
- require exact `test -x <artifact>` and `[ -x <artifact> ]` shapes

## Validation

- `uv run pytest --no-testmon tests/test_acceptance.py -q` = 115 passed
- `uv run pytest --no-testmon tests/test_work_session.py -k 'long_dependency or acceptance_evidence_refs or finish_block' -q` = 24 passed, 823 deselected, 25 subtests passed
- `uv run ruff check src/mew/acceptance.py src/mew/acceptance_evidence.py tests/test_acceptance.py` = passed
- `codex-ultra` reviewer session `019de270-4b79-7c90-9e32-ca7c46e81b8b` returned `PASS`

## Next

Run one same-shape `compile-compcert` speed_1 on this head before spending
another resource-normalized proof_5.
