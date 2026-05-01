# M6.24 External-Branch Help-Probe Speed Rerun: compile-compcert

Date: 2026-05-01 JST

## Command Shape

- Task: `terminal-bench/compile-compcert`
- Harbor command: `-k 1 -n 1`
- Agent: `mew_terminal_bench_agent:MewTerminalBenchAgent`
- Model: `gpt-5.5`
- Auth: mounted `~/.codex/auth.json`
- Mew command: `mew work --oneshot ... --model-backend codex --model gpt-5.5 --max-steps 30`

## Result

- Reward: `0.0`
- Trials: `1`
- Runner errors: `0`
- Runtime: about `30m22s`

Artifacts:

- Root result: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-external-branch-help-probe-compile-compcert-1attempt-20260501-1841/result.json`
- Trial result: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-external-branch-help-probe-compile-compcert-1attempt-20260501-1841/compile-compcert__MrchxMQ/result.json`
- Agent report: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-external-branch-help-probe-compile-compcert-1attempt-20260501-1841/compile-compcert__MrchxMQ/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- Verifier stdout: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-external-branch-help-probe-compile-compcert-1attempt-20260501-1841/compile-compcert__MrchxMQ/verifier/test-stdout.txt`

## What Improved

The previous selected repair worked. The run no longer spent the remaining wall
budget building a version-pinned OPAM Coq toolchain after a narrow configure
help probe.

Observed chain:

1. The run fetched the official CompCert `v3.13.1` source archive.
2. It read the configure failure, saw installed Coq `8.18.0` was unsupported.
3. It used the source-provided branch:
   `-ignore-coq-version -use-external-Flocq -use-external-MenhirLib`.
4. It ran `make depend`.
5. It built a real `/tmp/CompCert/ccomp`.

The external verifier confirmed this movement:

- `test_compcert_exists_and_executable`: passed
- `test_compcert_rejects_unsupported_feature`: passed
- `test_compcert_valid_and_functional`: failed

## Failure Shape

The remaining verifier failure was the default runtime library path:

```text
/usr/bin/ld: cannot find -lcompcert: No such file or directory
collect2: error: ld returned 1 exit status
ccomp: error: linker command failed with exit code 1
```

Inside the work session, the runtime recovery path then hit a narrower Makefile
target error:

```text
make -j"$(nproc)" ccomp runtime/libcompcert.a
make: *** No rule to make target 'runtime/libcompcert.a'.  Stop.
```

The model then inspected `runtime/Makefile` and saw:

```text
LIB=libcompcert.a
all: $(LIB)
install:: install -m 0644 $(LIB) $(DESTDIR)$(LIBDIR)
```

However, the remaining wall/model budget was too small; three compact-recovery
planning turns timed out before issuing the obvious continuation:

```text
make -C runtime all
make -C runtime install
```

## Classification

This is not a recurrence of `external_branch_help_probe_too_narrow_before_source_toolchain`.
That repair moved the run past source-compatible dependency selection and into
runtime-link recovery.

This is a narrower runtime-link proof failure:

`runtime_library_subdir_target_path_invalid`

The generic issue is:

- the model inferred a parent Makefile target path such as `runtime/libfoo.a`;
- parent make reported no rule for that subdir target path;
- the subdir Makefile already declared the library target and install rule;
- a direct `make -C <runtime-dir> all/install` continuation was needed.

## Next Repair

Add a generic resume blocker and RuntimeLinkProof guidance:

- detect `No rule to make target 'runtime/lib*.a'` or similar subdir runtime
  library target failures;
- surface `runtime_library_subdir_target_path_invalid`;
- steer the next action to the runtime subdirectory's own Makefile, for example
  `make -C runtime all` then `make -C runtime install`;
- clear the blocker after a later successful runtime-library build/install or
  default compile/link smoke.

Layer: `runtime_link_proof` / implementation profile.

Same-shape rerun condition:

- run one `compile-compcert` speed_1 after validation and review;
- if it passes, escalate to resource-normalized proof_5;
- keep broad measurement paused.
