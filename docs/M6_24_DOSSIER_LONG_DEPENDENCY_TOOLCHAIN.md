# M6.24 Dossier: Long Dependency / Toolchain Build Strategy

Gap class: `long_dependency_toolchain_build_strategy_contract`

Status: active improvement-phase dossier

Primary task evidence: `compile-compcert`

Related task family: `mcmc-sampling-stan`, `protein-assembly`,
`adaptive-rejection-sampler`

Controller: `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`

Decision ledger: `docs/M6_24_DECISION_LEDGER.md`

Gap ledger: `proof-artifacts/m6_24_gap_ledger.jsonl`

## Current Decision

Current selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> instrumentation/report -> long_dependency_timed_out_artifact_proof_calibration proof_5 -> compile-compcert
```

Broad measurement remains paused. The next score action is a
resource-normalized proof_5 for `compile-compcert` using `-k 5 -n 1` and
`auth.plus.json`. Before another code repair after that proof, read this dossier
and decide whether the next fix is a
new blocker, a repeated older blocker, or prompt/profile accretion.

## Repair Timeline

| Stage | Trigger / result | Repair layer | Outcome |
|---|---|---|---|
| Initial speed rerun | `compile-compcert` reached real CompCert/Coq path but missed `/tmp/CompCert/ccomp` by wall time. | selected long-dependency gap | Repair needed. |
| v0 build-state progress | Preserve package/toolchain/source/build state and final-artifact completion boundary. | detector/resume + THINK guidance | Improved continuity; still missed final artifact. |
| v0 follow-up | Review fixed command-only proof and fresh-session misleading hints. | detector correctness | Approved before rerun. |
| v0.1 compatibility/continuation | Preserve invalidated toolchain/package paths, running build command, dependency-generation order, bounded timeouts. | detector/resume + THINK guidance | Exposed wall-clock/full-build target gap. |
| v0.2 wall-clock/targeted artifact | Cap tool timeout to remaining wall budget; flag untargeted full project builds for specific artifacts. | tool/runtime + detector/profile guidance | Speed `1/1`; parallel proof invalid due contention; resource-normalized proof `1/2`. |
| v0.3 compatibility override ordering | Prefer cheap source override/help probes before heavy alternate toolchain construction. | detector/resume + THINK guidance | Speed `1/1`; proof `2/3`; next failure runtime link. |
| v0.4 runtime link library | Require runtime/library link proof for compiler/toolchain source builds. | detector/resume + THINK guidance | Speed `1/1`; proof `0/1`; next failure prebuilt-vs-source ordering. |
| v0.5 prebuilt dependency override precedence | Prefer prebuilt dependencies plus source override before source-building older dependencies. | detector/resume + THINK guidance | Speed `1/1`; proof `4/5`; next failure default runtime path. |
| v0.6 default runtime link path | Treat custom `-stdlib`/`-L`/env runtime proof as diagnostic until default path proof passes. | detector/resume + THINK guidance | Speed `0/1`; behavior moved to runtime install missing library. |
| v0.7 runtime install target | Build shortest explicit runtime-library target before install/default-link smoke. | detector/resume + THINK guidance | Speed `0/1`; failure moved earlier to source archive identity + empty response. |
| v0.8 source archive identity / empty response recovery | Accept archive/tag/root identity when internal markers are coarse; recover empty assistant response. | detector/resume + recovery + THINK guidance | Speed `1/1`; proof `4/5`; next failure timed-out artifact proof calibration. |
| v0.9 timed-out artifact proof calibration | Do not mark required final artifacts proven from timed-out or nonzero commands. | instrumentation/report | Speed `1/1`; proof `5` pending. |

## Pattern Readout

- Most successful repairs are not pure prompt changes. They combine
  detector/resume state with targeted guidance.
- The repeated long-dependency chain is now dominated by ordering and
  proof-boundary contracts.
- Prompt guidance is accumulating in the same surface. If the next failure is
  another narrow sequencing rule, evaluate a `LongDependencyProfile` or prompt
  section registry before adding another sentence.
- Resource normalization matters. Parallel proof failures can be harness
  artifacts for CPU-heavy dependency builds.
- The v0.8 speed proof patched bundled Flocq locally for Coq 8.18
  compatibility. That is useful task-solving evidence while score passes, but
  a proof miss in the same family should run this dossier preflight before more
  narrow guidance is added.
- The v0.8 proof miss was a report/resume calibration defect, not another
  prompt rule: `long_dependency_build_state` marked `/tmp/CompCert/ccomp` as
  proven after a timed-out build even though the external verifier found it
  missing.
- The v0.9 speed rerun passed external verification, but the internal final
  finish remained conservatively blocked with stale `missing_or_unproven`
  long-dependency state. Treat this as finish-ergonomics evidence, not a reason
  to skip the resource-normalized proof.

## Preflight Before Next Repair

Before any next repair in this gap class:

1. Identify whether the failure repeats one of: final artifact missing,
   untargeted build, compatibility override ordering, runtime link/install
   default path, source identity, or transient backend recovery.
2. Cite the previous stage that tried to handle it.
3. Explain why the next fix is not a duplicate detector/prompt patch.
4. Choose the layer:
   `instrumentation/report -> detector/resume -> profile/contract ->
   tool/runtime -> prompt section registry`.
5. If the fix touches prompt wording, state whether it belongs in a profile or
   prompt section instead of inline THINK guidance.

## Current Open Risk

`prompt_profile_accretion_risk`: the long-dependency policy now has many
detector plus guidance clauses. Another narrow prompt guidance repair should be
treated as evidence for consolidation unless the failure is clearly new and
low-risk.

## Non-Goals

- No Terminal-Bench-specific solver.
- No new authoritative lane for M6.24 coding tasks.
- No broad prompt rewrite without the one-run trial boundary required by the
  controller.
