# Review 2026-05-02: M6.24 Compile-CompCert Timeout Classification

Reviewer: Codex

Artifact:
`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-timeout-recovery-compile-compcert-1attempt-20260502-1755`

## Verdict

`e2c1f75` improved the prior blocker, but did not close the shape.

Evidence:

- Terminal-Bench reward remained `0.0`, runner exceptions stayed `0`, and
  `/tmp/CompCert/ccomp` was still missing at verifier time.
- The prior same-evidence unreached `make install` masking did improve:
  `resume.long_build_state.cleared_strategy_blockers` now records
  `untargeted_full_project_build_for_specific_artifact` / `make install` from
  tool call `10` as cleared.
- Compact recovery also improved materially: the final failed recovery turns
  used `compact_recovery` prompts around `53k-56k` chars with `context_json`
  around `39.8k-42.4k`, not the prior roughly `124k` prompt.
- The live run reached the intended path: source archive readback, external
  Flocq/MenhirLib configuration, `make depend`, then
  `make -j"$(nproc)" ccomp`.

## Failure Class

Current primary class:
`long-build wall-time/continuation budget`.

This is not primarily `toolchain strategy still wrong`: the agent had already
installed the missing MenhirLib package, used
`-ignore-coq-version -use-external-Flocq -use-external-MenhirLib`, generated
dependencies, and was inside the explicit `ccomp` build when killed.

This is not primarily `closeout verification wrong`: no successful final
artifact existed to close out. There is residual closeout/reducer noise
(`current_failure=source_authority_unverified`, stale blockers, and
`recovery_decision=null` in the final resume), but that did not cause the
external miss. The external miss is explained by command `10` having
`exit_code=null` and the verifier later finding no `/tmp/CompCert/ccomp`.

The decisive signal is budget: `work_report.stop_reason=wall_timeout`,
`work_exit_code=1`, command `10` was killed during the final build, and the
last model turns had only about `23.8s`, `11.5s`, then `5.4s` available before
the work loop stopped with about `14.6s` wall remaining.

## Repair Decision

Do not start another narrow toolchain-strategy or closeout-verification repair
before one more diagnostic rerun. The same-shape repair already moved the
blocker to a resource/continuation boundary.

Under the M6.24 improvement-phase rules, the next action should be recorded as
a run-shape diagnostic, not as broad measurement and not as proof_5.

## Recommended Next Single Action

Record a one-run M6.24 run-shape exception, then rerun one
`compile-compcert` speed_1 with enough matched outer agent/task timeout and
`mew --max-wall-seconds` headroom to answer one question:

```text
Does the current strategy pass when the final ccomp build is allowed to finish?
```

Close only if the usual gate holds: reward `1.0`, runner errors `0`,
`mew work` exit `0`, invokable `/tmp/CompCert/ccomp`, default smoke passed,
`source_authority=satisfied`, and no stale `current_failure` or strategy
blockers.

If that run passes only because of extra wall, do not escalate directly to
proof_5. Record that M6.24 needs a generic long-build continuation/budget
repair before close proof. If it still times out inside `make ccomp`, open that
tool/runtime repair immediately.

## Blocking Concerns

- Just raising `--max-wall-seconds` is not enough if the Terminal-Bench
  agent/task timeout remains effectively `1800s`; this run already used
  `--max-wall-seconds 1740`, so the outer timeout must be adjusted with it.
- Raising wall for speed_1 changes the timeout shape. That is acceptable only
  as a documented one-run run-shape diagnostic because the selected failure is
  now wall-time/continuation budget.
- Adding continuation support is the durable product direction, but it should
  be generic and stage-aware: continue idempotent long builds, preserve
  source/proof state, cap retries, and avoid masking real strategy blockers.
- Before implementing continuation support, account for the residual final
  resume noise. A continuation policy must follow the latest killed build state
  instead of rerouting to stale source-authority or old dependency blockers.
