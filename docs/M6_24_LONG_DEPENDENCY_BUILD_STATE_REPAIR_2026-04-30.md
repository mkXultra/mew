# M6.24 Long Dependency Build State Repair - 2026-04-30

Gap:

`long_dependency_build_state_progress_contract_missing`

Trigger evidence:

- `docs/M6_24_COMPILE_COMPCERT_SPEED_RERUN_2026-04-30.md`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-toolchain-compile-compcert-1attempt-20260430-0317/result.json`

## Problem

For long dependency/toolchain/source builds, mew could make real prerequisite
progress but fail to preserve enough build-state semantics across turns.

The `compile-compcert` rerun reached a compatible opam/Coq path, generated
CompCert dependencies, and started `make ccomp`, but the final artifact
`/tmp/CompCert/ccomp` was still missing when the external verifier ran. The
missing contract was not "more permissions"; it was explicit continuity between
prerequisite progress, final build continuation, and final artifact proof.

## Repair

This repair adds a generic implementation-lane contract:

- classify long dependency/toolchain/source-build tasks;
- extract required final absolute artifacts from task text;
- block finish when only prerequisite/configure/dependency/partial-build
  evidence exists and the required final artifact is unproven;
- surface `work_session.resume.long_dependency_build_state` with:
  - progress stages such as package setup, toolchain selection, configure,
    dependency generation, and build attempt;
  - expected and missing final artifacts;
  - latest build command and incomplete reason;
  - a continuation-oriented suggested next action;
- update THINK guidance to avoid restarting package/source setup after a
  compatible toolchain path is found.

## Validation

Focused validation:

```text
uv run pytest tests/test_acceptance.py -k 'long_dependency' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'long_dependency_build_state or work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py src/mew/work_loop.py tests/test_acceptance.py tests/test_work_session.py
```

Result:

- acceptance long-dependency tests: `4 passed`
- work-session long-dependency tests: `2 passed`
- work-session/prompt tests: `2 passed`
- ruff: passed

## Review Follow-up

`codex-ultra` reviewed commit `ef5abf8` and found two correctness risks before
the validation rerun:

- command-only executable smoke proofs such as
  `test -x /tmp/CompCert/ccomp && /tmp/CompCert/ccomp -version` could be
  rejected when stdout did not repeat the artifact path;
- a fresh long-dependency session with no completed progress could still emit a
  "resume existing source tree/toolchain" hint because missing artifacts were
  initialized before any progress existed.

The follow-up fix keeps the final-artifact blocker strict, but evaluates the
successful tool command together with stdout/stderr, and suppresses
`long_dependency_build_state` until there is actual build progress or proven
artifact state.

The same `codex-ultra` review session re-reviewed the follow-up diff and
returned `APPROVED`.

## Next Validation

Run a one-trial same-shape speed rerun for `compile-compcert`.

Do not resume broad measurement and do not escalate to five trials before this
speed rerun is recorded.
