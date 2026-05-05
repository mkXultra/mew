# M6.24 Runtime Subdir Target Repair

Date: 2026-05-01 JST

## Selected Gap

`runtime_library_subdir_target_path_invalid`

This repair follows the failed speed rerun recorded in
`docs/M6_24_EXTERNAL_BRANCH_HELP_PROBE_COMPILE_COMPCERT_SPEED_RERUN_2026-05-01.md`.

The external-branch help-probe repair succeeded in moving `compile-compcert`
past dependency selection and into runtime-link recovery. The new miss was that
mew tried an invalid parent Makefile target path:

```text
make -j"$(nproc)" ccomp runtime/libcompcert.a
make: *** No rule to make target 'runtime/libcompcert.a'.  Stop.
```

Afterwards, mew inspected `runtime/Makefile`, but low remaining wall/model
budget prevented the final continuation.

## Why This Is Not A Duplicate

Prior runtime-link repairs covered:

- `default_runtime_link_path_failed`: default compile/link smoke failed with a
  missing runtime library.
- `runtime_install_before_runtime_library_build`: runtime install failed because
  the library artifact did not exist.

This gap sits between those two:

- mew knew runtime support was needed;
- it tried to build the runtime library before install;
- it addressed the wrong Makefile surface by inventing a parent target path
  instead of invoking the runtime subdirectory's own `all/install` rules.

The lowest durable repair layer is resume state plus RuntimeLinkProof guidance.

## Implemented Shape

Code changes:

- `src/mew/work_session.py`
  - detects failed command output containing `No rule to make target` plus a
    `runtime/lib*.a`-style target;
  - emits `runtime_library_subdir_target_path_invalid`;
  - clears the blocker after a later successful runtime-library build/install
    or default runtime-link smoke;
  - renders the blocker in `format_work_session_resume()`.
- `src/mew/work_loop.py`
  - extends `RuntimeLinkProof` to prefer the runtime subdirectory's Makefile
    when parent make rejects a subdir library target path.
- `tests/test_work_session.py`
  - pins detection, clear-after-subdir-build, false-positive suppression, and
    prompt guidance.

## Architecture Fit

- Authoritative lane: `implementation/tiny`
- New lane: no
- Helper lane: no
- Rationale: this is still a normal implementation-lane toolchain recovery
  contract. It does not change the artifact authority, success metric, or task
  kind.

## Validation

Local validation passed:

- `uv run pytest --no-testmon tests/test_work_session.py -q`
  - `854 passed, 1 warning, 67 subtests passed`
- `uv run pytest --no-testmon tests/test_acceptance.py -q`
  - `115 passed`
- `uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py`
  - passed
- `jq -c . proof-artifacts/m6_24_gap_ledger.jsonl >/dev/null`
  - passed
- `git diff --check`
  - passed

External review passed:

- `codex-ultra` session `019de311-1fef-7de3-9e47-cca79922a088`
  initially returned REQUIRED_CHANGES for stale broad blockers and a `cmake`
  false positive.
- After fixes, the same session returned PASS.

Next score action:

`M6.24 -> runtime_library_subdir_target_path_invalid -> compile-compcert speed_1`
