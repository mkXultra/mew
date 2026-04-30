# M6.24 Runtime Install Target Speed Rerun - 2026-04-30

Purpose: validate v0.7 `long_dependency_runtime_install_requires_runtime_target_contract`
with the same `compile-compcert` speed shape before spending proof_5 or broad
measurement.

## Artifact

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-install-target-compile-compcert-1attempt-20260430-1559/2026-04-30__16-07-36/result.json
```

Trial:

```text
compile-compcert__sBezfNS
```

## Result

- reward: `0/1`
- runner errors: `0`
- runtime: `7m 48s`
- external verifier: `3 failed`
- verifier failure: `/tmp/CompCert/ccomp does not exist`
- work stop reason: `model_error`
- model error: `response did not contain assistant text`

## Observed Shape

This run did not reach the v0.6 runtime-install failure shape. It failed
earlier:

1. Step 2 fetched the versioned CompCert release archive from the `v3.13.1`
   tag but aborted with `exit 3` because it required internal source markers
   to contain the exact patch string `3.13.1`.
2. The source archive/root identity was already grounded by the URL/tarball
   path and archive extraction. Internal `VERSION` only reported `3.13`, which
   is not enough reason to stop a patch-level release source build.
3. Step 3 tried to continue from the fetched source tree, but `/tmp/CompCert/ccomp`
   remained missing.
4. The next model turn failed with `response did not contain assistant text`,
   so one-shot did not get a chance to recover from the failed continuation.

This is a valid failed speed proof, but it does not invalidate the v0.7 runtime
install repair. The new gap is a narrower long-dependency source identity and
transient model-response resilience issue.

## Decision

Continue M6.24 improvement phase.

Next bounded generic repair:

```text
long_dependency_source_archive_identity_and_empty_response_recovery_contract
```

Expected repair:

- treat versioned release archive/tag/root identity as valid patch-level source
  evidence when internal source files only report a coarse major/minor version;
- surface `source_archive_version_grounding_too_strict` in
  `work_session.resume.long_dependency_build_state`;
- steer THINK away from aborting solely because internal `VERSION` omits an
  archive-grounded patch suffix;
- let one-shot continue after a transient `response did not contain assistant text`
  model backend failure, matching existing timeout/5xx recovery behavior.

Validation after repair remains one same-shape `compile-compcert` speed rerun.
Do not run proof_5 or broad measurement first.
