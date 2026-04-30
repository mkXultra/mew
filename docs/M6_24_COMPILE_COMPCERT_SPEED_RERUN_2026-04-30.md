# M6.24 Compile CompCert Speed Rerun - 2026-04-30

Task: `compile-compcert`

Job:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-toolchain-compile-compcert-1attempt-20260430-0317/result.json`

Work report:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-toolchain-compile-compcert-1attempt-20260430-0317/compile-compcert__XfufMwC/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`

## Result

- trials: `1`
- runner errors: `0`
- reward: `0/1`
- runtime: `31m 02s`
- stop reason: `wall_timeout`
- steps: `13/30`
- frozen Codex target: `5/5`

External verifier failure:

```text
/tmp/CompCert/ccomp does not exist
```

## Interpretation

The SR-016 `/tmp` scratch permission blocker did not recur. The run created and
worked inside `/tmp/CompCert`, installed the OCaml/Coq/opam toolchain path,
downloaded CompCert `3.13.1`, attached the `coq-released` opam repository, and
reached a configured source tree with Coq `8.16.1`.

The run also made meaningful strategy progress:

- it rejected the Ubuntu Coq `8.18.0` path after incompatibility symptoms;
- it moved to an opam switch with Coq `8.16.1`;
- it generated CompCert dependencies with `make depend`;
- it started the real `make ccomp` build path.

The remaining failure is not native permission or verifier handoff. It is a
long dependency/toolchain build strategy gap: mew spent most of the wall budget
discovering and installing the compatible proof toolchain, then failed to
preserve enough build-state progress and budget to produce the required final
artifact `/tmp/CompCert/ccomp`.

## Decision

Do not escalate this to a five-trial proof. The one-trial speed rerun already
classified the post-SR-016 shape.

Next repair:

`long_dependency_build_state_progress_contract`

The repair should stay generic and implementation-lane scoped:

- preserve long-build state across turns: source tree, package-manager env,
  selected toolchain versions, configure status, dependency status, build logs,
  expected final artifact, and exact continuation command;
- distinguish prerequisite progress from task completion when the required
  final executable/artifact is still missing;
- avoid restarting package-manager or source-tree setup after a compatible
  path is found;
- allocate remaining budget explicitly between prerequisite completion and the
  final build command;
- surface a resume-visible next action when the task is not finishable within
  the current wall budget.

Same-shape validation after repair:

`compile-compcert` one-trial speed rerun.
