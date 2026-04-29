# M6.24 Compile CompCert Follow-up Speed Rerun - 2026-04-30

Task: `compile-compcert`

Job:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-build-state-followup-compile-compcert-1attempt-20260430-0418/result.json`

Work report:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-build-state-followup-compile-compcert-1attempt-20260430-0418/compile-compcert__AxZ9bja/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`

## Result

- trials: `1`
- runner errors: `0`
- reward: `0/1`
- runtime: `31m 43s`
- mew status: partial report before oneshot completion
- step pressure: `29/30`, one tool call running at handoff
- frozen Codex target: `5/5`

External verifier failure:

```text
/tmp/CompCert/ccomp does not exist
```

## Observed Behavior

The v0 build-state contract changed the failure shape but did not close the
gap.

Useful progress:

- `long_dependency_build_state` was present in the partial report.
- mew preserved the `/tmp/CompCert` source tree and `/tmp/opam` switch rather
  than reverting to the old `/tmp` permission blocker.
- the run reached an opam Coq `8.16.1` toolchain, configured CompCert, ran a
  `make depend` continuation, and entered the real `make -j2 ccomp` proof build.
- the final running build output had advanced through many Coq files, including
  `backend/Asmgenproof0.v` and `x86/Asmgenproof1.v`.

Remaining blockers:

- mew still spent too much wall budget on invalidated toolchain/package paths:
  Ubuntu Coq/Menhir, missing `coq-flocq` repository state, and an opam
  `ocamlbuild` preinstalled-tool conflict.
- the session needed multiple model/tool turns to discover that the project
  required `make depend` before the target-specific `make ccomp` continuation.
- the partial `long_dependency_build_state` did not include the actively
  running final build command as the latest build state because running tools
  were ignored.
- long prerequisite/source-build commands used default-size timeout slices in
  several places instead of one bounded command sized to the remaining wall
  budget.

## Decision

Do not escalate to a five-trial proof.

Next repair:

`long_dependency_toolchain_compatibility_and_continuation_contract`

This remains a generic implementation-lane repair with no new lane:

- surface invalidated toolchain/package paths in reentry so they are not
  retried;
- treat running/interrupted long build commands as active build state in partial
  reports;
- guide long source builds to inspect version constraints before distro
  package installs;
- guide dependency-generation/configure targets before target-specific builds
  when project errors indicate missing generated dependencies;
- allow the model to choose a bounded per-command timeout for genuinely long
  build/verifier commands instead of repeatedly slicing the same build.

Same-shape validation after repair:

`compile-compcert` one-trial speed rerun.
