# M6.24 Runtime Component Behavior Proof Repair

Date: 2026-05-05

## Trigger

After quota reset, the same-shape `build-cython-ext` retry ran:

- job:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-lifecycle-narrow-build-cython-ext-1attempt-20260505-0935`
- trial: `build-cython-ext__wPScYFt`
- Harbor runner errors: `0`
- mew result: `mew_exit_code=0`, `stop_reason=finish`
- external reward: `0.0`
- verifier: `10 passed`, `1 failed`

The previous lifecycle parameter pollution repair worked: replay/dogfood shows
no lifecycle identity loss, no managed contract loss, no runtime identity
mismatch, and no lifecycle parameter pollution.

## Failure Class

New generic class:
`runtime_component_behavior_import_only_finish_false_positive`.

The model proved that Cython extension modules imported and that their `.so`
paths existed. It also ran the package's visible repository tests. It then
claimed "compiled extensions should work".

The hidden verifier failed `test_ccomplexity` by invoking
`pyknotid.spacecurves.ccomplexity.cython_higher_order_writhe(...)`, which hit a
remaining `np.int` runtime path inside `ccomplexity.pyx`.

This is not a pyknotid-specific solver gap. It is a finish-evidence gap:
for loadable runtime components, import/load/path proof is loadability or
existence proof, not behavior proof.

## Repair

Implemented generic substrate:

- `src/mew/acceptance.py`
  - adds a runtime-component behavior finish blocker;
  - blocks `task_done=true` when the task says a native module, extension,
    shared library, plugin, or similar runtime component should work but
    verified evidence only proves import, load, or path existence;
  - accepts evidence that invokes exported extension behavior or
    component-specific tests in the original runtime context.
- `src/mew/work_loop.py`
  - adds implementation-lane guidance that load/path evidence is insufficient
    and a behavior-level smoke is required.
- `src/mew/dogfood.py`
  - extends the repository-test-tail emulator to detect
    `finish_false_positive` when mew exits 0 / finishes but external reward is
    0 with failed verifier tests.
- `tests/test_acceptance.py`, `tests/test_dogfood.py`
  - cover import-only rejection, behavior proof acceptance, and the latest
    finish false-positive summary shape.

## Validation

Local validation observed:

- `uv run pytest --no-testmon -q tests/test_acceptance.py -k 'runtime_component or compiled_extension'`
  passed.
- `uv run pytest --no-testmon -q tests/test_dogfood.py -k 'repository_summary_detects_finish_false_positive or repository_test_tail_emulator or lifecycle_parameter_pollution'`
  passed.
- `./mew dogfood --scenario m6_24-repository-test-tail-emulator --terminal-bench-job-dir proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-lifecycle-narrow-build-cython-ext-1attempt-20260505-0935 --terminal-bench-task build-cython-ext --json`
  passed and detected `finish_false_positive=true`.

## Next

Before another live `speed_1`:

1. Run scoped ruff and focused full local tests for touched surfaces.
2. Ask `claude-ultra` to review the repair.
3. If approved, rerun exactly one same-shape `build-cython-ext` `speed_1`.

Do not add pyknotid, NumPy, or Cython-symbol-specific solver rules.
