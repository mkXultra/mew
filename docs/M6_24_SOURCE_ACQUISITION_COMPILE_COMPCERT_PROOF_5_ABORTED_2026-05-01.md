# M6.24 `compile-compcert` Source-Acquisition Proof_5 Abort

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> source_acquisition_profile v1 -> compile-compcert proof_5 with -k 5 -n 1
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-acquisition-compile-compcert-5attempts-seq-20260501-1219/result.json
```

## Summary

- requested shape: `-k 5 -n 1`
- auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- completed valid trials before abort: `1`
- score before abort: `0/1`
- close target: `5/5`
- runner errors before manual abort: `0` on the completed trial
- result: close target became impossible after the first valid trial failed, so
  the remaining sequential trials were stopped to avoid wasting time and tokens

Completed trial:

- `compile-compcert__hiAd54u`: reward `0.0`

Stopped trial:

- `compile-compcert__naCK9bW`: cancelled by supervisor after the first failure
  made the frozen `5/5` close target impossible.

## Failure Shape

The first trial built `/tmp/CompCert/ccomp`, but the default compile/link smoke
failed because the runtime library was not installed into the default linker
path:

```text
/usr/bin/ld: cannot find -lcompcert: No such file or directory
ccomp: error: linker command failed with exit code 1
```

The external verifier reproduced the same class:

```text
test_compcert_exists_and_executable: passed
test_compcert_valid_and_functional: failed
test_compcert_rejects_unsupported_feature: passed
```

This is not a Terminal-Bench-specific solver issue. It is a generic
compiler/toolchain acceptance failure: after a source build produces the final
compiler executable, a default compile/link smoke can still fail because the
runtime or standard library was not built/installed into the default lookup
path.

## Secondary Loop Signal

After the failed smoke, the next model turn timed out under the remaining wall
budget:

```text
stop_reason=wall_timeout
remaining_seconds=17.462
available_model_timeout_seconds=3.731
```

The repair should make this failure class visible earlier in reentry and prompt
the next attempt to build/install the shortest runtime/library target before
restarting source acquisition, configure, or clean rebuild work.

## Evidence

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-acquisition-compile-compcert-5attempts-seq-20260501-1219/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-acquisition-compile-compcert-5attempts-seq-20260501-1219/compile-compcert__hiAd54u/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-acquisition-compile-compcert-5attempts-seq-20260501-1219/compile-compcert__hiAd54u/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-acquisition-compile-compcert-5attempts-seq-20260501-1219/compile-compcert__hiAd54u/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-acquisition-compile-compcert-5attempts-seq-20260501-1219/compile-compcert__hiAd54u/verifier/test-stdout.txt`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-acquisition-compile-compcert-5attempts-seq-20260501-1219/compile-compcert__naCK9bW/result.json`

## Next

Implement a generic `default_runtime_link_path_failed` resume blocker and
sharpen `RuntimeLinkProof` guidance:

- when a default compiler/toolchain smoke fails with `cannot find -l...`,
  preserve the source/build state;
- do not restart source acquisition, configure, or clean rebuild;
- build/install the shortest runtime/library target into the default lookup
  path;
- rerun the same default compile/link smoke.

After validation and review, rerun one same-shape `compile-compcert` speed_1
before spending another proof_5.
