# M6.24 `compile-compcert` Source Identity / Empty Response Speed Rerun

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> implementation_profile/no_lane_change -> long_dependency_source_archive_identity_and_empty_response_recovery_contract -> speed_1 compile-compcert
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-identity-compile-compcert-1attempt-20260430-1736/result.json
```

Trial:

```text
compile-compcert__GVwtAez
```

## Summary

- requested shape: `-k 1 -n 1`
- auth: `auth.plus.json` mounted as `/codex-auth/auth.json`
- score: `1/1`
- runner errors: `0`
- Harbor mean: `1.000`
- total runtime: `24m 23s`
- agent execution: `22m 31s`
- external verifier: `3 passed`

The v0.8 repair did not regress the score path. The run accepted the
`v3.13.1` archive/tag/root identity even though internal `VERSION` reported
`3.13`, recovered past the earlier source-identity blocker, built
`/tmp/CompCert/ccomp`, installed the runtime library into the default path, and
passed the external verifier.

## Observed Path

Important progress:

1. The run fetched and extracted
   `https://github.com/AbsInt/CompCert/archive/refs/tags/v3.13.1.tar.gz`.
2. It treated archive/root identity as sufficient patch-level source evidence
   while preserving the internal `VERSION=3.13` evidence.
3. It installed `libmenhir-ocaml-dev` after configure found the Menhir API
   library missing.
4. It ran `make depend` after direct `make ccomp` initially failed to locate
   Coq source files.
5. It patched the local bundled Flocq source for Coq 8.18 compatibility.
6. It built `ccomp`, built `runtime/libcompcert.a`, ran `make install`, and
   verified a default-path compile/link smoke with `/tmp/CompCert/ccomp`.
7. The external verifier passed:
   - `test_compcert_exists_and_executable`
   - `test_compcert_valid_and_functional`
   - `test_compcert_rejects_unsupported_feature`

## Repair Readout

The selected v0.8 repair is validated for `speed_1`.

The run also produced useful next-risk evidence: mew solved the remaining
compatibility problem by patching bundled Flocq for Coq 8.18 rather than taking
the older compatible Coq route. Since the score passed, this is not a blocker
for the selected repair. If a resource-normalized proof fails on this family,
use the gap-class dossier preflight before adding another narrow prompt rule.

## Evidence

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-identity-compile-compcert-1attempt-20260430-1736/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-identity-compile-compcert-1attempt-20260430-1736/compile-compcert__GVwtAez/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-identity-compile-compcert-1attempt-20260430-1736/compile-compcert__GVwtAez/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-identity-compile-compcert-1attempt-20260430-1736/compile-compcert__GVwtAez/verifier/test-stdout.txt`

## Next

Escalate to resource-normalized five-trial proof for `compile-compcert` using
`-k 5 -n 1` and `auth.plus.json`. Do not resume broad measurement first.

If that proof misses the frozen Codex target `5/5`, do not start another local
guidance repair directly. First read
`docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md` and classify whether the
failure is new, a repeated older blocker, or prompt/profile accretion.
