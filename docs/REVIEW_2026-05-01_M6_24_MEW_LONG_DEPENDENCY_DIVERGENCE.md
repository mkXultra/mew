# Review: M6.24 Long Dependency Divergence

Date: 2026-05-01

Scope reviewed:
- `src/mew/work_session.py`
- `src/mew/work_loop.py`
- `src/mew/commands.py`
- `src/mew/acceptance.py`
- `src/mew/acceptance_evidence.py`
- `src/mew/prompt_sections.py`
- `docs/M6_24_DECISION_LEDGER.md`
- `docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md`
- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`
- `proof-artifacts/m6_24_gap_ledger.jsonl`
- `tests/test_work_session.py`
- `tests/test_acceptance.py`

## Verdict

Recommendation: redesign before another compile-compcert `proof_5`.

Divergence severity: high for the long dependency/toolchain substrate, medium for the broader implementation lane, low-to-medium for the acceptance evidence layer.

The current implementation has improved real generic machinery, especially terminal evidence validation, finish blocking, wall timeout handling, prompt section measurement, and structured resume state. However, the compile-compcert loop has also become the dominant design driver. Mew is now accumulating a CompCert-shaped recovery architecture through prompt clauses, transcript detectors, resume blockers, and narrowly matched tests. The latest `runtime_library_subdir_target_path_invalid` repair may justify one bounded `speed_1` validation if the team wants the data point already selected in the ledger, but it should not be escalated to another `proof_5` before consolidation.

## Current Architecture Map

Mew currently handles this class through five cooperating layers:

1. Prompt policy: `src/mew/work_loop.py` still starts from a large legacy implementation prompt and slices it into named sections with `build_work_think_prompt_sections()`. The relevant sections are `source_acquisition_profile`, `long_dependency_profile`, `runtime_link_proof`, `recovery_budget`, `compact_recovery`, `dynamic_failure_evidence`, and `context_json`.

2. Prompt metadata: `src/mew/prompt_sections.py` gives sections ids, versions, hashes, stability, cache policy, and metrics. This is observability and presentation metadata, not an independent policy engine.

3. Resume state and blockers: `src/mew/work_session.py` reconstructs `long_dependency_build_state` from session calls. It tracks progress, expected artifacts, missing artifacts, latest build command, incomplete reason, strategy blockers, and `suggested_next`. Blockers are structured dictionaries with codes, layers, tool ids, and excerpts, but they are still inferred from transcripts and string heuristics.

4. Command runtime: `src/mew/commands.py` enforces finish gates, wall timeout ceilings, long-tool recovery reserves, and continuation after deterministic finish blockers. `src/mew/work_loop.py` switches to compact recovery under timeout pressure.

5. Acceptance evidence: `src/mew/acceptance.py` and `src/mew/acceptance_evidence.py` provide the strongest deterministic substrate. Long dependency completion requires terminal-success tool evidence proving the final artifact. Timed-out calls, masked probes, fake echo output, path-prefix spoofing, post-proof mutations, and opaque mutation chains are rejected.

The control loop is documented externally in the M6.24 gap loop, dossier, decision ledger, and JSONL gap ledger. Those files are valuable process memory, but they are not runtime architecture.

## Accumulation Points

`LongDependencyProfile` is currently a prompt section, not a typed profile object. Its responsibilities have expanded to include source acquisition ordering, package-manager versus source builds, compatibility override probing, help-output probe width, prebuilt/system dependency preference, vendored patch avoidance, archive identity, dependency-generation ordering, build target choice, wall budget awareness, and final artifact proof reminders. Several of these now overlap with `SourceAcquisitionProfile`, `RuntimeLinkProof`, `RecoveryBudget`, and acceptance evidence.

`RuntimeLinkProof` is also partly prompt guidance and partly detector behavior. It has accumulated responsibility for distinguishing custom runtime path smoke tests from default link proof, detecting `cannot find -l...` failures, requiring default runtime link recovery, handling runtime library install/build ordering, and now detecting invalid parent `make runtime/lib*.a` targets. This is close to a runtime/library state machine, but it is implemented as prompt text plus transcript-derived blockers.

`RecoveryBudget` is prompt guidance plus some real command-runtime behavior. The real behavior is in timeout ceilings, compact recovery mode, and `work_tool_recovery_reserve_seconds()`. The missing piece is a durable budget ledger that records what budget was spent, what recovery reserve remains, and what recovery actions are allowed next.

Resume blockers have become the main typed recovery surface. They preserve progress and carry blocker codes such as compatibility branch budget, external branch help-probe width, vendored patch surgery, default runtime link path failed, runtime install before runtime library build, and runtime library subdir target path invalid. They are useful, but they are stringly typed and reconstructed from logs rather than emitted by an explicit build/dependency state machine.

Acceptance evidence has accumulated final-authority responsibilities. It now decides whether a final artifact was actually proven, whether evidence refs are valid, whether a finish attempt must continue, and whether proof remains valid after later mutations. This accumulation is healthy because it is deterministic and provider-neutral.

## Typed State vs Prompt-Only Guidance

| Area | Typed or evidence-backed today | Prompt-only or mostly guidance today |
| --- | --- | --- |
| Long dependency progress | `long_dependency_build_state` dict with progress, artifacts, latest build, blockers, and suggested next | Long profile prose describing ordering and strategy |
| Source acquisition | Source provenance and branch blockers in `work_session.py` | Profile guidance about authoritative sources, generated archives, prebuilt/system branches |
| Runtime link proof | Blocker codes and artifact proof helpers for default link failures, runtime install, and subdir target failures | Runtime proof prose in `work_loop.py` |
| Recovery budget | Wall timeout ceiling, compact recovery switch, recovery reserve heuristic | Recovery budget section text and model-facing reminders |
| Finish gate | `acceptance_done_gate_decision()`, structured blockers, invalid evidence refs, continuation prompt | Prompt reminders to cite evidence and not finish early |
| Final artifact proof | `acceptance_evidence.py` terminal-success and strict artifact proof parser | Minimal prompt guidance to prove artifact with tool evidence |
| Prompt sections | Section ids, versions, hashes, metrics | Section content remains sliced legacy prompt text |
| M6.24 controller memory | Dossier, ledger, gap JSONL records | Human/controller process guidance, not executable runtime policy |

## Evidence of Generalization

The acceptance evidence layer is genuinely generic. Tests cover artifact paths beyond CompCert, reject fake terminal proof shapes, and share proof logic between acceptance and resume state.

Wall timeout ceiling, compact recovery, process-group command killing, and recovery reserves solve broad long-running tool problems rather than a single benchmark.

Prompt section hashing and metrics make policy growth visible. This is useful infrastructure for later reducing prompt bloat.

Several detectors are framed as generic long dependency behaviors: source provenance, generated source archives, external/prebuilt branch discovery, broad full-project builds before artifact targets, runtime library proof, and default versus custom link paths.

## Evidence of Overfitting and Prompt Accretion

The repair history is now heavily dominated by compile-compcert. The dossier and gap ledger show many consecutive repairs in the same family: compatibility override ordering, wall-clock target choice, runtime link library proof, prebuilt dependency precedence, default runtime path, runtime install target, source archive identity, compatibility branch budget, source acquisition, vendored patch surgery, acceptance evidence structure, external branch help-probe width, and runtime subdir target path.

Many repairs follow the same pattern: a proof or speed run exposes a narrow next failure; mew adds a detector, a resume blocker, prompt wording, and tests for that shape. Some of these are good substrate changes, but the repeated shape is now a process signal rather than just a backlog of small bugs.

The same recovery fact often exists in three places: prompt prose, resume `suggested_next` text, and Python detector logic. That makes transfer risk higher because a rule can be generalized in one layer while remaining benchmark-shaped in another.

The test vocabulary is still mostly CompCert-shaped for the long dependency path: Coq, Flocq, Menhir, opam, `/tmp/CompCert/ccomp`, `libcompcert.a`, runtime Makefiles, and source/toolchain branch selection. There are some generic fixtures, but not enough transfer coverage to justify another expensive proof escalation as the main evidence source.

The prompt section registry exposes `prompt_profile_accretion_risk`; it does not solve it. `LongDependencyProfile` remains a growing tactical policy paragraph, even though it is now wrapped in section metadata.

## Structural Divergence From Robust Coding CLI Architecture

Robust coding CLIs typically separate executor state, project instructions, permission/sandbox policy, command history, hooks/settings, and verification. Mew currently blends several of those responsibilities into implementation prompt text, transcript-derived blockers, and external milestone ledgers.

The largest divergence is the absence of a first-class long-build contract. Mew does not yet have a durable model for source acquisition, dependency branch selection, configure state, dependency generation, target build, runtime library build/install, default smoke proof, final artifact proof, and recovery budget. Instead, it reconstructs that shape from command text and output after the fact.

The second divergence is that prompt policy is doing executor work. `LongDependencyProfile`, `RuntimeLinkProof`, and `RecoveryBudget` should mostly present a compact policy derived from state. Today they also carry operational logic that should live in typed state transitions, command runtime policy, or acceptance evidence.

The third divergence is controller externalization. The M6.24 dossier, decision ledger, and gap ledger are rigorous, but they guide a human/model loop outside the runtime. They do not yet form an internal scheduler or repair policy that can prevent another narrow compile-compcert patch from being selected.

The acceptance evidence layer is the main exception. It is close to the right architecture: deterministic, terminal-evidence based, and shared by acceptance and resume logic.

## Recommendation

Do not run another compile-compcert `proof_5` on the current substrate. Treat the latest runtime subdir target repair as the end of the current patch chain unless a bounded `speed_1` is needed to record the already-selected repair outcome.

Before proof escalation, redesign the long dependency substrate around a typed `LongBuildContract` or equivalent state machine. Minimum fields should include:

- requested final artifacts and proof requirements
- source acquisition method and source authority
- dependency strategy candidates and rejected branches
- configured/dependency-generated/build-attempted stages
- selected build target, cwd, timeout, and result
- runtime library build/install status
- default runtime link proof status
- wall budget spent, reserve remaining, and recovery ceiling
- current blocker code, clear condition, and next allowed recovery action

Move blocker codes into a stable taxonomy with explicit prerequisites and clear conditions. New blockers should map to state transitions, not become another free-standing detector plus prompt sentence.

Shorten `LongDependencyProfile`, `RuntimeLinkProof`, and `RecoveryBudget` so they render state-backed policy rather than accumulating tactical memories. Keep prompt sections and metrics, but make them the transport for policy, not the source of truth.

Expand validation before the next proof run. Add at least a few non-CompCert transcript fixtures or related long-dependency benchmark candidates with different source, dependency, artifact, and runtime-link shapes. The goal is transfer testing, not immediate pass-rate improvement.

Preserve the acceptance evidence system. It is the part of the current design most aligned with robust coding CLI architecture and should remain generic rather than becoming a benchmark parser.

Bottom line: continue the M6.24 improvement loop only after consolidating the substrate. The current compile-compcert patch loop is still producing useful facts, but another `proof_5` would mostly measure adaptation to one troublesome benchmark, not the reliability of mew's generic long dependency implementation lane.
