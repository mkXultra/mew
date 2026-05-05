# M6.24 Source-Authority Path Correlation Review - 2026-05-02

Reviewer: codex-ultra
Session: `019de907-194c-7841-b84f-8f9f6e6f33d9`

## Scope

Review the reducer repair for the `compile-compcert` speed rerun that passed
externally but left internal closeout blocked on `source_authority_unverified`.

The repair is generic source-archive identity correlation:

- authoritative absolute archive acquisition
- later relative archive hash/list readback by basename
- validated direct source-root extraction with `tar --strip-components=1`

## Review Rounds

Round 1: `REQUEST_CHANGES`

- Relative basename readback accepted any earlier `cd` to the authoritative
  parent, even if a later `cd` moved away before hash/list readback.

Round 2: `REQUEST_CHANGES`

- Global assignment resolution could rewrite an earlier `cd "$d"` using a
  later reassignment.

Round 3: `REQUEST_CHANGES`

- Unsafe/control-flow `cd` was treated as a no-op, preserving stale parent cwd.

Round 4: `REQUEST_CHANGES`

- `pushd`/`popd` were not treated as cwd-changing.

Round 5: `REQUEST_CHANGES`

- Wrapped shell builtins such as `builtin cd` were not treated as cwd-changing.

Final round: `APPROVE`

- No findings.
- No remaining test gaps for the basename/cwd spoof path.

## Final Guardrails

- Relative readback only correlates when both hash and archive-list readbacks
  execute from the authoritative archive parent.
- Absolute path mismatches remain rejected.
- Relative parent escape paths remain rejected.
- Variable-based, wrapped, control-flow, and unmodeled cwd-changing commands
  invalidate cwd tracking rather than preserving the prior parent cwd.

## Final Validation

- `uv run pytest -q tests/test_long_build_substrate.py -k 'source_authority and readback' --no-testmon`
  - `35 passed, 231 deselected`
- `uv run pytest -q tests/test_long_build_substrate.py --no-testmon`
  - `266 passed`
- `uv run pytest -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py -k 'source_authority or runtime_link or compact_recovery or long_build or default_smoke' --no-testmon`
  - `283 passed, 994 deselected`
- `uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`
  - passed
- `git diff --check`
  - passed

## Decision

Run exactly one same-shape `compile-compcert` speed rerun. Do not run `proof_5`
or broad measurement before that rerun records clean internal closeout or a
newer narrower gap.
