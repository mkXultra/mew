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
M6.24 -> long_dependency_toolchain_build_strategy_contract -> profile_contract -> vendored_dependency_patch_surgery_before_supported_branch speed_1 -> compile-compcert
```

Broad measurement remains paused. The source-acquisition profile and
runtime-link recovery repairs both passed one-trial same-shape speed proofs at
`1/1`. The latest resource-normalized proof_5 missed on a new
long-dependency/toolchain strategy shape: the failed valid trial started from a
VCS-generated source archive fallback, configured against unsupported Coq
`8.18.0`, then spent recovery attempts editing bundled Flocq proof-library
files before timing out without `/tmp/CompCert/ccomp`. This is now a
profile/contract consolidation point, not another narrow Flocq or CompCert
prompt clause. The current repair is
`vendored_dependency_patch_surgery_before_supported_branch`; the next action is
one same-shape `compile-compcert` speed_1 before another proof_5.

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
| v0.9 timed-out artifact proof calibration | Do not mark required final artifacts proven from timed-out or nonzero commands. | instrumentation/report | Speed `1/1`; first proof_5 invalidated by auth expiry; rerun pending after OAuth refresh repair. |
| proof infra OAuth refresh | Refresh ChatGPT OAuth tokens from legacy/Codex auth shapes and retry one 401. | proof infrastructure | Auth-expiry failure removed; same-shape proof reached valid completed trials `1/2`; next failure final recovery budget. |
| v1.0 final recovery-budget reserve | Preserve recovery wall budget for long build commands that include final validation smoke. | tool/runtime | Speed `1/1`; proof `2/3`; next failure malformed JSON plan recovery. |
| v1.1 malformed JSON plan recovery | Treat backend `failed to parse JSON plan` as a recoverable one-shot transient model error. | loop recovery | Speed `1/1`; proof `1/2`; next failure timeout-ceiling full-context recovery. |
| v1.2 timeout-ceiling compact recovery | Use compact recovery context when wall-clock pressure reduces model timeout. | model context budgeting | Speed `1/1`; proof `2/3`; next failure compatibility branch budget. |
| v1.3 compatibility branch budget | Commit earlier to coherent prebuilt/external dependency compatibility branches for long source-build tasks and avoid starting the final long build after serial probes consumed the wall budget. | profile/contract | Speed `1/1`; proof_5 pending. |
| source acquisition profile | Surface VCS-generated archive fallback plus compatibility/toolchain surgery without authoritative source-channel evaluation. | source acquisition profile + detector/resume | Speed `1/1`; proof `0/1`; next failure default runtime link. |
| default runtime link failure recovery | Surface failed default compile/link smoke after compiler build as a runtime-link recovery blocker. | runtime link proof + detector/resume | Speed `1/1`; proof `0/1`; next failure vendored dependency proof surgery before supported branch. |
| v1.4 vendored dependency patch surgery | Stop local vendored/third-party dependency or proof-library mutation when source-provided external/prebuilt branch evidence exists and final artifacts are still missing. | profile/contract + detector/resume | Implemented and reviewed; speed_1 pending. |

## Pattern Readout

- Most successful repairs are not pure prompt changes. They combine
  detector/resume state with targeted guidance.
- The repeated long-dependency chain is now dominated by ordering and
  proof-boundary contracts.
- v1.3 keeps the repair in the existing implementation profile: resume state
  surfaces `compatibility_branch_budget_contract_missing` from generic evidence
  (prebuilt package-manager dependencies, source-exposed external/prebuilt
  branch, serial probe churn, timed-out external-branch build, missing final
  artifacts) and guidance stays bounded to branch commitment plus wall-budget
  reserve.
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
- The first v0.9 resource-normalized proof_5 is not clean score evidence:
  `auth.plus.json` expired mid-run and four trials hit `HTTP 401 token_expired`.
  Treat this as proof-infrastructure evidence. Rerun the same shape after Codex
  OAuth refresh is validated before selecting another mew-core repair.
- The OAuth-refresh proof rerun is clean auth evidence: no `token_expired`
  recurrence. The failed valid trial repeated the runtime-link class, but the
  differentiator was exhausted recovery budget, not missing runtime-link policy:
  a passing contrast trial used the already-known runtime-library build/install
  recovery route successfully.
- The v1.0 recovery-budget same-shape speed proof passed `1/1`: `mew work`
  finished cleanly, built `/tmp/CompCert/ccomp`, installed default runtime
  support, ran a default-path smoke, and the external verifier passed. Escalate
  to resource-normalized proof_5 before any next repair or broad measurement.
- The v1.0 resource-normalized proof miss is not another long-dependency
  sequencing rule. The failed valid trial stopped before task work because a
  structured model response was malformed and one-shot treated the parser error
  as terminal. Keep the fix in loop recovery, not long-dependency prompt
  guidance.
- The v1.1 malformed-JSON recovery speed proof passed `1/1`, so return to
  proof_5 before another repair or broad measurement.
- The v1.1 resource-normalized proof miss is not another runtime-link or
  runtime-install prompt rule. The blocker was already visible as
  `runtime_install_before_runtime_library_build`; the failure was that a
  low-wall recovery turn used a ~193k char full prompt and timed out repeatedly.
  Keep the v1.2 repair in model-context budgeting.
- The v1.2 timeout-ceiling compact-recovery speed proof passed `1/1`: `mew
  work` finished cleanly after 9 steps, installed default runtime support, ran
  a default-path smoke, and the external verifier passed. Escalate to
  resource-normalized proof_5 before another repair or broad measurement.
- The v1.2 resource-normalized proof miss is not another compact-recovery or
  runtime-link regression. Two valid trials passed; the failed trial found the
  right `-use-external-Flocq` branch but only after serially spending most of
  the wall budget on weaker compatibility probes. This should be repaired as a
  long-dependency profile/contract budget issue, not by appending another
  task-local prompt sentence.
- The source-acquisition profile speed proof passed `1/1`, but its proof_5
  miss repeated the known runtime-link failure after building `ccomp`; that was
  repaired by `default_runtime_link_path_failed` and validated by another
  speed proof.
- The default-runtime-link recovery proof miss did not repeat runtime-link
  failure. It fell back to a VCS-generated source archive, then edited bundled
  Flocq proof-library files under unsupported Coq while the final compiler
  artifact was missing. The transferable issue is local vendored dependency
  patch surgery after source-provided external/prebuilt branch evidence exists.
- v1.4 keeps the repair in the existing implementation profile. It should not
  fire from package-manager evidence alone, configure override attempts alone,
  read-only inspection, or normal project source patches.

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
detector plus guidance clauses. v1 consolidation introduced prompt section
registry support for normal work THINK prompts, with named sections for
`ImplementationLaneBase`, `LongDependencyProfile`, `RuntimeLinkProof`,
`RecoveryBudget`, `CompactRecovery`, `DynamicFailureEvidence`, schema, and
context. Another narrow prompt guidance repair should update the relevant
section or structural profile, not append inline THINK text, unless the failure
is clearly new and low-risk.

## Non-Goals

- No Terminal-Bench-specific solver.
- No new authoritative lane for M6.24 coding tasks.
- No broad prompt rewrite without the one-run trial boundary required by the
  controller.
