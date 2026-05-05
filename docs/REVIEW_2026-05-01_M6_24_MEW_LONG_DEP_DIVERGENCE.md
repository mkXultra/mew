# Review: M6.24 Long Dependency Divergence

Date: 2026-05-01

Scope:
- `src/mew/work_session.py`
- `src/mew/work_loop.py`
- `src/mew/commands.py`
- `src/mew/acceptance.py`
- `src/mew/acceptance_evidence.py`
- `src/mew/prompt_sections.py`
- `tests/test_work_session.py`
- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`
- `docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md`
- `docs/M6_24_DECISION_LEDGER.md`
- `proof-artifacts/m6_24_gap_ledger.jsonl`

External comparison anchors:
- Codex CLI official docs: https://developers.openai.com/codex/cli/features
- Codex non-interactive docs: https://developers.openai.com/codex/noninteractive
- Codex CLI getting started: https://help.openai.com/en/articles/11096431-openai-codex-cli-getting-started
- Claude Code headless mode: https://code.claude.com/docs/en/headless
- Claude Code settings/hooks/memory docs: https://code.claude.com/docs/en/settings, https://docs.claude.com/en/docs/claude-code/hooks, https://docs.claude.com/en/docs/claude-code/memory
- Local Codex reference source: `references/fresh-cli/codex`

## Executive Conclusion

Conditional yes: pause compile-compcert proof escalation and start redesign prep now.

The already-reviewed `runtime_library_subdir_target_path_invalid` repair can justify at most one bounded `compile-compcert` `speed_1` data point if the team wants to confirm the latest fix. It should not be followed by `proof_5`, broad measurement, or another compile-compcert-shaped repair before redesign prep. If that speed run passes, the result should be recorded as "latest local blocker likely repaired", not "architecture stable". If it fails, the next action should still be redesign prep rather than another narrow patch.

Reason: the current implementation has become effective at moving one long dependency benchmark forward, but its center of gravity is now a growing compile-compcert-shaped substrate: transcript detectors, prompt clauses, resume blockers, wall-clock exceptions, and tests all reinforce the same path. That is useful evidence, but it is no longer enough evidence to justify more proof reruns as the primary learning loop.

## Mew Architecture Map For This Gap

### Prompt and Profile Surface

The implementation-lane prompt lives primarily in `src/mew/work_loop.py`.

`_build_work_think_prompt_legacy()` still contains the full monolithic implementation-lane policy. `build_work_think_prompt_sections()` then slices that legacy text into prompt sections:
- `implementation_lane_base`
- `source_acquisition_profile`
- `long_dependency_profile`
- `runtime_link_proof`
- `recovery_budget`
- `implementation_lane_base_continuation`
- `schema`
- `compact_recovery`
- `dynamic_failure_evidence`
- `context_json`

`src/mew/prompt_sections.py` gives those sections ids, versions, hashes, cache policies, and metrics. This is a real improvement over one opaque prompt, but it currently wraps an accumulated legacy text body. The policy is sectioned, not yet truly modeled.

The long dependency prompt/profile clauses now encode guidance for source acquisition, package-manager prebuilt avoidance, version-pinned source branches, runtime library proof, default-vs-custom runtime link proof, recovery reserve, continuation behavior, and avoiding repeated broad builds.

### Resume Blockers and Build State

The long dependency state model lives mostly in `src/mew/work_session.py`.

`build_long_dependency_build_state()` derives a structured resume object for long dependency tasks. It mines session calls for:
- stage progress
- expected and missing artifacts
- latest build command and status
- incomplete reasons
- strategy blockers
- suggested next action

Important blocker helpers include:
- source toolchain before override blockers
- source provenance blockers
- compatibility branch budget blockers
- external branch help-probe width blockers
- vendored patch surgery blockers
- default runtime link path blockers
- default runtime link failure blockers
- runtime install before runtime library blockers
- runtime library subdir target path blockers
- untargeted full-build blockers

`format_work_session_resume()` then renders these blockers back into model-facing resume guidance, with special priority ordering for long dependency recovery cases.

This is the strongest sign that mew is trying to grow a state model, but the state is still mostly inferred from transcripts and text patterns rather than captured as first-class execution events or an explicit dependency/build graph.

### Tool Runtime and Wall Budget

The tool/runtime behavior lives primarily in `src/mew/commands.py` and `src/mew/work_loop.py`.

`cmd_work_ai()` enforces wall-clock constraints across model turns and tool calls. `apply_work_tool_wall_timeout_ceiling()` caps tool timeouts based on remaining wall budget. `work_tool_recovery_reserve_seconds()` reserves a long-tool recovery budget for long dependency validation commands, except when a recent runtime recovery blocker already exists.

`plan_work_model_turn()` adapts model timeout, prompt context mode, and fallback behavior. Under timeout pressure, it may switch from full context to compact recovery. This is directionally aligned with mature coding CLI behavior: a long-running executor must avoid spending the whole budget on one opaque attempt and must preserve enough time for recovery.

The remaining gap is that command execution is still treated mostly as isolated shell calls plus transcript parsing. There is no durable long-running build job model, no explicit build target graph, and no generic continuation contract beyond prompt/resume guidance.

### Acceptance Evidence and Done Gate

The done gate is split between `src/mew/acceptance.py` and `src/mew/acceptance_evidence.py`.

This is one of the healthier parts of the current design. `acceptance_done_gate_decision()` blocks task completion when evidence is missing or invalid. Long dependency final artifacts must be proven by terminal command evidence. `acceptance_evidence.py` rejects weak evidence shapes such as timed-out proofs, masked probes, opaque command chains, and post-proof mutations.

The important architectural strength is that this layer is mostly provider-neutral and command-evidence based. It does not parse compile-compcert semantics directly as the proof. That should be preserved.

### Model Context Budgeting

Context budgeting lives in `src/mew/work_loop.py`.

The relevant controls are:
- `WORK_CONTEXT_BUDGET`
- `WORK_COMPACT_CONTEXT_BUDGET`
- compact/recovery context window candidates
- compact task/resume limits
- `compact_resume_for_prompt()`
- `work_prompt_context_mode()`
- `_effective_prompt_context_mode()`
- `_prompt_context_mode_for_wall_clock()`
- `build_work_model_context()`

The current behavior tracks prompt metrics, resume size, active memory size, recent read windows, and prompt section metrics. Compact recovery is triggered for timeout ceilings and timed-out recent model turns.

This is also directionally correct. The divergence is that too much recovery knowledge still lives in prompt prose and transcript-derived blockers, so compaction must preserve many special cases instead of restoring from a smaller canonical state object.

## Accretion and Overfit Signals

### Repeated compile-compcert-centered repair chain

The dossier and ledger now show a long chain of one-shape repairs around the same benchmark family:
- build-state progress
- compatibility/continuation
- wall-clock and targeted artifact behavior
- compatibility override ordering
- runtime link library proof
- prebuilt dependency override precedence
- default runtime link path proof
- runtime install target proof
- source archive identity and empty response recovery
- timed-out artifact proof calibration
- OAuth refresh
- final recovery-budget reserve
- malformed JSON plan recovery
- timeout-ceiling compact recovery
- compatibility branch budget
- source acquisition profile
- default runtime link failure recovery
- vendored dependency patch surgery
- acceptance evidence structure
- external branch help-probe width
- runtime library subdir target path

Many of these repairs are legitimate generic implementation-lane improvements. The overfit signal is the loop shape: a speed pass or partial advance repeatedly exposes another compile-compcert-specific edge, and the repair becomes another detector/prompt clause/test fixture.

### Same fact encoded across multiple surfaces

Several policies now appear in three places:
- Python blocker/detector logic in `work_session.py`
- model-facing resume text and `suggested_next`
- long dependency prompt/profile text in `work_loop.py`

This makes the behavior hard to reason about. It also means a future benchmark can fail because one surface was generalized while another still encodes a narrower assumption.

### Transcript mining instead of durable state

`build_long_dependency_build_state()` reconstructs source acquisition, build progress, runtime proof, and blocker state from prior calls. That works for the observed transcript shape, but mature coding CLIs tend to lean on persistent sessions, event logs, project instructions, command outputs, permissions, and explicit hooks/settings rather than accumulating benchmark-specific transcript heuristics.

The current mew state is more advanced than a plain prompt, but it is not yet a durable executor state model.

### Fixture vocabulary is narrow

`tests/test_work_session.py` has broad helper coverage, but the long dependency examples are mostly CompCert-shaped: Coq, Flocq, Menhir, `/tmp/CompCert`, `/tmp/CompCert/ccomp`, `libcompcert.a`, runtime Makefiles, and external dependency flags.

These tests protect the current chain. They do not yet prove transfer to other long dependency families with different toolchains, target names, artifact layouts, or source acquisition conventions.

### Prompt profile keeps absorbing recovery policy

`docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md` already flags `prompt_profile_accretion_risk`. The code confirms that risk. Prompt sections reduce opacity, but the long dependency profile is still an accumulating list of tactical rules.

Mature CLI policy surfaces usually separate:
- project instructions or memory
- permission and sandbox configuration
- hooks and lifecycle commands
- execution history and resumable sessions
- structured output contracts

Mew currently blends several of these into one implementation prompt plus Python transcript detectors.

## What Is Working And Should Be Preserved

### Deterministic acceptance evidence

The acceptance evidence layer is the most mature part of the current approach. Terminal command evidence, evidence refs, post-proof mutation guards, timeout rejection, and continuation-producing finish blockers are all useful and should remain generic.

The important line to hold: do not replace this with benchmark-specific success parsers.

### Structured resume object

`long_dependency_build_state` is useful even though it is too transcript-derived today. It gives the model a structured view of progress, missing artifacts, latest build status, and strategy blockers. The redesign should keep this shape but move toward explicit state events and task-agnostic fields.

### Wall-clock budgeting and recovery reserve

The wall timeout ceiling, compact recovery mode, and long-tool recovery reserve are solving a real execution problem. Long dependency builds need normalized time budgets and enough reserved time to inspect failures and recover.

### Prompt sections and section metrics

The prompt section registry gives mew visibility into prompt size, cacheable prefix size, section hashes, and dynamic versus static content. That is a good foundation for reducing prompt accretion.

### Resource-normalized proof discipline

The ledger's insistence on resource-normalized proof is correct. CPU-heavy benchmarks should not be compared to Codex or Claude Code without normalized wall and concurrency assumptions.

### Controller discipline

The gap loop already contains the right warning: after multiple detector plus THINK-guidance repairs without stable close-gate success, pause local repair and decide whether to consolidate the profile/contract. That condition has now been reached.

## Generic Deficiencies vs Likely Solved Enough

### Still Generic Implementation-Lane Deficiencies

These are not compile-compcert-only bugs:

- Durable execution state is missing. Mew reconstructs dependency/build status from transcripts instead of maintaining a first-class source/dependency/build/artifact/runtime state model.
- Recovery policy is distributed across detectors, prompt text, resume text, and tests.
- Prompt/profile clauses are carrying too much executor policy.
- Context compaction is useful but must preserve too many tactical rules because the canonical state is incomplete.
- Long-running tool execution is still modeled as isolated command calls, not resumable build jobs with structured lifecycle events.
- Transfer coverage is weak. The test suite protects the compile-compcert path better than it proves long-dependency generality.
- Failure classification is mostly a set of specialized blockers rather than a small taxonomy with generic state transitions.

### Likely Solved Enough For Now

These should not be the next redesign target unless fresh evidence regresses them:

- OAuth/proof-infra refresh handling.
- Malformed JSON plan recovery.
- Rejection of timed-out artifact proof.
- Rejection of masked or opaque command evidence.
- Post-proof mutation guards.
- Basic wall timeout ceiling behavior.
- Basic recovery reserve behavior for long build validation.
- Prompt section rendering, hashing, and metrics.
- Deterministic finish blocking with continuation prompts.
- Default runtime artifact proof strictness for the observed CompCert-shaped case.

## Divergence Matrix

| Area | Mature coding CLI pattern | Current mew approach | Divergence / risk | Redesign implication |
| --- | --- | --- | --- | --- |
| Executor | Direct shell/file executor with permission, sandbox, network, and lifecycle controls. Codex emphasizes approvals and sandbox/security controls; Claude Code exposes permissions, hooks, and headless execution. | Shell calls are available and wall-capped. Long dependency commands get timeout ceilings and recovery reserve. | Execution is still mostly one-shot command plus transcript mining. Long builds do not have a durable job/build lifecycle. | Introduce task-agnostic build execution state before adding more long-dep prompt rules. |
| State model | Persistent sessions, event logs/history, project instructions, resumable threads, and explicit settings or memory. | `work_session` reconstructs state from calls and emits `long_dependency_build_state`. | Useful but inferred. Source choice, dependency branch, target path, artifact proof, and runtime proof are not first-class state transitions. | Promote long dependency progress into explicit state events with stable fields. |
| Verification / done gate | Run tests/builds, require observable command results, support structured output in non-interactive mode. | Strong deterministic acceptance gate with terminal evidence refs and strict proof filtering. | This layer is healthier than the rest. Risk is only that long-dep proof logic could drift into task-specific semantics later. | Preserve generic command-evidence proof. Keep benchmark-specific meaning out of acceptance. |
| Context management | Stable project memory/instructions plus resumable sessions and compaction. Context is not the only state store. | Prompt sections, compact resume, compact recovery, prompt metrics, recent read windows. | Directionally good, but prompt carries too many accumulated tactical rules. | Use prompt sections as a delivery layer for a smaller state/profile contract, not as the policy source of truth. |
| Recovery loop | Continue from session history, inspect logs, rerun targeted commands, use hooks/settings and permission model. | Recovery is driven by specialized blockers, resume `suggested_next`, prompt clauses, and wall reserve. | Recovers current chain but can overfit to observed failure strings. | Replace many special cases with a small failure taxonomy and state transition model. |
| Policy/profile surface | Policy lives in project instructions, settings, hooks, permissions, and explicit mode/config surfaces. | Policy is split across legacy prompt slices, Python detectors, resume text, and tests. | Hard to audit and easy to accrete. Same rule can exist in several layers. | Create a profile/rule registry with ownership: detector, state transition, prompt guidance, or acceptance rule. |
| Measurement loop | Benchmarks inform design, but mature behavior is evaluated across varied tasks and stable executor contracts. | M6.24 has rigorous ledgering, but recent learning is dominated by compile-compcert. | Repeated same-shape proof can reward benchmark adaptation. | Add transfer fixtures before more proof escalation. |
| User/project instruction model | Codex uses repo instructions such as `AGENTS.md`; Claude Code uses memory such as `CLAUDE.md` and settings. | Mew has prompt profiles and active memory, but no clearly separated project instruction versus executor-policy boundary for this gap. | Project/task guidance and core executor behavior are blended. | Separate project/task instructions from mew-owned implementation-lane policy. |

## Recommended Next Step Before Designing

Freeze new long dependency prompt/detector additions and write a redesign-prep inventory before any `proof_5` or broad measurement.

The inventory should classify every current long dependency clause and blocker into one of four buckets:
- durable execution state
- generic detector/state transition
- prompt guidance/profile policy
- task-specific or obsolete compile-compcert adaptation

It should also define a small task-agnostic state schema before implementation design. Minimum fields:
- source acquisition method and authority
- dependency strategy and rejected alternatives
- selected compatibility branch/version and evidence
- build command, target, cwd, timeout, and result
- produced artifacts and freshness proof
- runtime/library link proof
- wall-budget state and reserved recovery budget
- failure class and next allowed recovery action

Finally, add transfer evidence before designing against compile-compcert again. Use at least three non-CompCert long dependency transcript fixtures or benchmark candidates with different source and artifact shapes, for example the existing related-family candidates in the dossier. The goal is not to pass them yet. The goal is to identify which current rules transfer, which are overfit, and which should become generic executor state.

Only after that inventory should mew choose the redesign shape: a rule/profile registry, a state-machine-backed recovery loop, or a smaller hybrid. The current evidence points toward a state-machine-backed recovery loop with prompt sections as presentation, not as the source of policy.
