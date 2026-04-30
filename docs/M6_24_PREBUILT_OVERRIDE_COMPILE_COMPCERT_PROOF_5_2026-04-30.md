# M6.24 `compile-compcert` Prebuilt Override Proof Result

Task: `compile-compcert`

Result root:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-prebuilt-override-compile-compcert-5attempts-seq-20260430-1230/2026-04-30__12-30-26/result.json`

## Summary

- requested shape: `-k 5 -n 1`
- auth: `auth.plus.json` mounted as `/codex-auth/auth.json`
- score: `4/5`
- runner errors: `0`
- Harbor mean: `0.800`
- total runtime: `2h 11m 31s`

This improves the prior v0.4 resource-normalized proof (`0/1` valid completed)
but does not reach the frozen Codex close target of `5/5`.

Do not resume broad measurement from this result.

## Trial Outcomes

| Trial | Reward | Notes |
|---|---:|---|
| `compile-compcert__g5PYLuw` | `1.0` | Built `ccomp`, installed runtime library, and passed all external verifier checks. |
| `compile-compcert__ZxbgecM` | `1.0` | Built `ccomp`, installed runtime support, and passed all external verifier checks. |
| `compile-compcert__7iehBSF` | `1.0` | Had `work_exit_code=1` in the report but external verifier passed all checks; score evidence is the verifier result. |
| `compile-compcert__3ZQgSS2` | `1.0` | Patched the local proof surface, installed runtime under a local prefix, and passed all external verifier checks. |
| `compile-compcert__cvvujgi` | `0.0` | Built `ccomp` and passed a local smoke only by giving `ccomp` a custom `-stdlib` path. External verifier used default invocation and failed linking with `cannot find -lcompcert`. |

## Failed Trial Shape

Failed trial:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-prebuilt-override-compile-compcert-5attempts-seq-20260430-1230/2026-04-30__12-30-26/compile-compcert__cvvujgi
```

Important evidence:

- mew built a real `/tmp/CompCert/ccomp`;
- mew found a local `libcompcert.a`;
- the local smoke compile used an explicit `-stdlib "$(dirname "$libcompcert")"`
  argument;
- the external verifier invoked `/tmp/CompCert/ccomp` without that custom
  runtime path and failed:

```text
/usr/bin/ld: cannot find -lcompcert: No such file or directory
ccomp: error: linker command failed with exit code 1
```

This is not a source-fetch, permission, or prebuilt-dependency-ordering miss.
The remaining blocker is that toolchain/compiler tasks need a default-user
runtime/link proof, not only a custom-path local smoke.

## Next Repair Candidate

Generic class:

`long_dependency_default_runtime_link_path_contract`

Bounded repair:

For compiler/toolchain source-build tasks, a local smoke that adds custom
runtime/library flags such as `-stdlib`, `-L`, `LD_LIBRARY_PATH`, or equivalent
does not prove the default external verifier path. The work loop should either:

- install/configure the runtime library into the compiler's default lookup path;
  or
- prove the exact default invocation that the external verifier will use.

This is a generic long-dependency/toolchain proof repair, not a
`compile-compcert` or Terminal-Bench-specific solver.

After repair, run `compile-compcert` speed_1 first. Escalate only if the speed
proof passes or materially changes the selected failure shape.
