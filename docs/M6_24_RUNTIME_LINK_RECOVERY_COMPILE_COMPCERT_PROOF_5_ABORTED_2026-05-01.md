# M6.24 `compile-compcert` Runtime-Link Recovery Proof_5 Abort

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> default_runtime_link_path_failed recovery v1 -> compile-compcert proof_5 with -k 5 -n 1
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-5attempts-seq-20260501-1350/result.json
```

## Summary

- requested shape: `-k 5 -n 1`
- auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- completed valid trials before abort: `1`
- score before abort: `0/1`
- close target: `5/5`
- completed-trial runner errors: `0`
- job-level `n_errors`: `1`, caused by manual cancellation of the second
  trial after the close target became impossible
- result: close target became impossible after the first valid trial failed,
  so the remaining sequential trials were stopped to avoid wasting time and
  tokens

Completed trial:

- `compile-compcert__yadJDAt`: reward `0.0`

Stopped trial:

- `compile-compcert__y55ohDi`: `CancelledError` after manual supervisor stop.

## Failure Shape

The first valid trial did not reproduce the previous runtime-link miss. It
failed earlier: `/tmp/CompCert/ccomp` was never created.

The work session selected a VCS-generated tag archive fallback:

```text
source_url=https://github.com/AbsInt/CompCert/archive/refs/tags/v3.13.1.tar.gz
source_kind=upstream_vcs_tag_fallback
```

It then configured against an unsupported distro Coq version and moved into
local proof-library surgery under the bundled/vendored Flocq tree:

```text
Testing Coq... version 8.18.0 -- UNSUPPORTED
Error: CompCert requires a version of Coq between 8.12.0 and 8.16.1
```

Representative later errors:

```text
Error: The variable Z_div_mod_eq was not found in the current environment.
```

```text
The relation (inbetween ...) is not a declared reflexive relation.
```

The final long build attempt timed out after a local patch:

```text
command timed out after 398.113 second(s)
```

External verifier result:

```text
test_compcert_exists_and_executable: failed
test_compcert_valid_and_functional: failed
test_compcert_rejects_unsupported_feature: failed
```

This is not a Terminal-Bench-specific solver issue and not a reason to add
another narrow Flocq patch hint. The generic failure class is:

```text
vendored_dependency_patch_surgery_before_supported_branch
```

When a source/toolchain task has visible source-provided compatibility branch
evidence, final artifacts are still missing, and repair starts editing
vendored/third-party dependency or proof-library files, mew should stop local
dependency patch surgery and switch to a supported dependency version or
source-provided external/prebuilt dependency branch before another long
rebuild.

## Evidence

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-5attempts-seq-20260501-1350/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-5attempts-seq-20260501-1350/compile-compcert__yadJDAt/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-5attempts-seq-20260501-1350/compile-compcert__yadJDAt/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-5attempts-seq-20260501-1350/compile-compcert__yadJDAt/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-5attempts-seq-20260501-1350/compile-compcert__yadJDAt/verifier/test-stdout.txt`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-5attempts-seq-20260501-1350/compile-compcert__y55ohDi/result.json`

## Next

Implement a generic `vendored_dependency_patch_surgery_before_supported_branch`
resume blocker and LongDependencyProfile guidance:

- require source-provided external/prebuilt compatibility branch evidence
  before flagging;
- do not flag package-manager dependency availability alone;
- do not flag read-only inspection of vendored paths;
- flag native edit tools and shell/Python mutation commands targeting
  vendored/third-party dependency or proof-library paths while final artifacts
  are missing;
- make the blocker visible in formatted resume even when several other
  strategy blockers exist.

After validation and review, rerun one same-shape `compile-compcert` speed_1
before spending another proof_5.
