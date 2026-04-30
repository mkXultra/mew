# M6.24 `compile-compcert` Default Runtime Link Path Speed Rerun

Task: `compile-compcert`

Result root:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-default-runtime-link-path-compile-compcert-1attempt-20260430-1508/2026-04-30__15-07-47/result.json`

## Summary

- requested shape: `-k 1 -n 1`
- auth: `auth.plus.json` mounted as `/codex-auth/auth.json`
- score: `0/1`
- runner errors: `0`
- Harbor mean: `0.000`
- total runtime: `30m 25s`

Do not resume proof_5 or broad measurement from this result.

## Failure Shape

The repair changed behavior in the intended direction: mew no longer accepted a
custom `-stdlib` smoke as close evidence. It built `/tmp/CompCert/ccomp`, saw
the default link failure, and attempted to install runtime support into the
default configured path.

The selected failed trial:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-default-runtime-link-path-compile-compcert-1attempt-20260430-1508/2026-04-30__15-07-47/compile-compcert__2e9veG6
```

The concrete failure was:

```text
make -C runtime install
install -m 0644 libcompcert.a /usr/local/lib/compcert
install: cannot stat 'libcompcert.a': No such file or directory
```

Interpretation: when the default runtime link path is missing, `make install`
may not be enough. The work loop needs to build the runtime library target
first, then install/configure it, then rerun the default compile/link smoke.

## Next Repair Candidate

Generic class:

`long_dependency_runtime_install_requires_runtime_target_contract`

Bounded repair:

For compiler/toolchain source-build tasks, if runtime install fails because the
runtime library artifact is absent, preserve that as a long-dependency strategy
blocker and steer the next action toward the shortest explicit runtime-library
target, such as `make -C runtime libcompcert.a`, `make runtime/libcompcert.a`,
or the project equivalent, before retrying install and default-link smoke.

After repair, run `compile-compcert` speed_1 again. Do not spend proof_5 or
broad measurement until speed_1 passes or materially changes the failure shape.
