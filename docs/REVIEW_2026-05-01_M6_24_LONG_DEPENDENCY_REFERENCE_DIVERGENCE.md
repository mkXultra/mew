# REVIEW 2026-05-01 - M6.24 Long Dependency Reference Divergence

Status: step-3 synthesis only. This is not yet a redesign document.

Purpose: decide whether mew should keep patching the current
`compile-compcert` long-dependency chain, or pause and design a deeper generic
long-build substrate.

## Inputs

Reference audits:

- `docs/REVIEW_2026-05-01_M6_24_CODEX_LONG_DEPENDENCY_AUDIT.md`
- `docs/REVIEW_2026-05-01_M6_24_CLAUDE_CODE_LONG_DEPENDENCY_AUDIT.md`
- `docs/REVIEW_2026-05-01_M6_24_MEW_LONG_DEPENDENCY_DIVERGENCE.md`

Additional cross-check reports observed in the worktree:

- `docs/REVIEW_2026-05-01_M6_24_CODEX_LONG_DEP_AUDIT.md`
- `docs/REVIEW_2026-05-01_M6_24_CLAUDE_CODE_LONG_DEP_AUDIT.md`
- `docs/REVIEW_2026-05-01_M6_24_MEW_LONG_DEP_DIVERGENCE.md`

Current M6.24 context:

- `docs/M6_24_DECISION_LEDGER.md`
- `docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md`
- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`
- `proof-artifacts/m6_24_gap_ledger.jsonl`

## Executive Verdict

Redesign is warranted before another `compile-compcert` `proof_5`.

The latest `runtime_library_subdir_target_path_invalid` fix may justify one
bounded `speed_1` confirmation if the controller needs to record that specific
repair outcome. It should not justify another proof escalation or another
nearby detector/prompt patch chain.

The divergence is not that Codex or Claude Code has a hidden
`compile-compcert` strategy. They do not. Their advantage is lower in the stack:
durable command execution, typed tool events, bounded output retention,
background/pollable process state, prompt/cache boundary discipline, tool
policy, and evidence-preserving recovery.

Mew has some strong pieces already, especially deterministic acceptance
evidence, prompt section metrics, wall-clock budgeting, compact recovery, and
structured resume blockers. The problem is that long-dependency behavior is now
split across prompt prose, transcript-derived detectors, resume `suggested_next`
text, tests, and external decision ledgers. That shape is increasingly
CompCert-shaped and hard to transfer.

## Shared Reference Pattern

Codex and Claude Code differ in implementation details, but they agree on the
important architecture shape:

- long commands are represented as runtime objects or task/process sessions,
  not only as one-shot shell output;
- command output is typed, bounded, and durable enough to survive context
  pressure;
- failures become structured tool results or events visible to the model;
- patch/write operations have a lifecycle and evidence trail;
- prompt text steers behavior, but executor/tool state owns the operational
  facts;
- compaction/resume reconstructs from durable state and history, not from a
  growing prompt memory;
- verification is separate from implementation behavior and should cite concrete
  command/file evidence;
- static policy and dynamic evidence are separated to reduce prompt churn and
  cache breakage.

For M6.24, the most transferable reference concepts are:

1. Pollable or background long-running command state.
2. Typed command evidence: command, cwd, start/end, exit status, timeout,
   duration, output id/path, head/tail output, and truncation metadata.
3. Event-backed acceptance evidence and resume reconstruction.
4. Controller-owned recovery budget and allowed recovery actions.
5. Prompt sections as presentation/cache units, not the source of recovery
   truth.

## Mew Current Strengths

The current mew implementation is not just prompt hacking. These parts should
be preserved:

- `acceptance_evidence.py` and `acceptance_done_gate_decision()` are generic
  and stricter than typical CLI final-message discipline.
- Terminal success evidence, invalid-evidence rejection, timeout rejection,
  masked/opaque command rejection, and post-proof mutation guards are the right
  direction.
- `long_dependency_build_state` gives a useful resume summary with progress,
  missing artifacts, latest build command, blockers, and suggested next action.
- Wall timeout ceilings, compact recovery, and recovery reserve solve real
  long-running task failures.
- Prompt section ids, hashes, stability, and metrics make profile accretion
  visible.
- The M6.24 gap ledger and decision ledger already encode the right process
  warning: when repeated detector plus THINK-guidance repairs do not stabilize
  the gate, pause and consolidate.

## Mew Current Divergence

Severity: high for the long-dependency/toolchain substrate.

Main divergence:

- There is no first-class long-build contract or state machine. Mew reconstructs
  source acquisition, dependency strategy, build target, runtime proof, and
  recovery state from transcript patterns.
- `LongDependencyProfile`, `RuntimeLinkProof`, and `RecoveryBudget` are still
  partly natural-language policy. They are sectioned and measured, but not yet
  backed by a compact typed runtime contract.
- The same fact often appears in three places: Python detector logic,
  model-facing resume text, and prompt profile prose.
- Resume blockers are useful, but many have become strategy carriers rather
  than simple summaries of typed execution state.
- Recent repairs are dominated by one benchmark family: source archive identity,
  compatibility branch budget, vendored dependency patching, external branch
  probes, default runtime path, runtime install target, runtime library subdir
  targets, and similar compile-compcert-adjacent failures.
- The long-dependency test vocabulary is still mostly CompCert-shaped, even
  when individual repairs are partly generic.

This does not mean the recent fixes were wrong. Many improved generic
infrastructure. It means the current learning loop has reached diminishing
returns: the next proof would mostly measure adaptation to one task, not
general implementation-lane reliability.

## What Not To Do

Do not add a Terminal-Bench or `compile-compcert` solver.

Do not add another long prompt paragraph unless the failure is proven to be a
new domain strategy rather than missing substrate.

Do not copy Codex or Claude Code wholesale. Their full permission, UI, sandbox,
transport, agent, and telemetry stacks are larger than what M6.24 needs.

Do not weaken mew's deterministic acceptance gate to match Codex/Claude Code
final-message discipline. Mew's strict proof gate is a product advantage.

Do not introduce a second authoritative planner/agent for this gap. Explorer or
verifier roles may be useful later, but the immediate issue is the
implementation lane's substrate.

## Redesign Target

The likely redesign should be a mew-sized long-build substrate, not a full CLI
rewrite.

Minimum concept:

- `LongBuildContract`: requested artifacts, source/dependency constraints,
  runtime/default-link proof requirement, wall budget, and final proof criteria.
- `BuildAttempt`: command, cwd, env summary, selected target, timeout, start/end
  time, exit status, timeout flag, output ref, artifact refs, and mutation refs.
- `LongBuildState`: source acquired, dependency strategy chosen/rejected,
  configured, dependencies generated, target built, runtime library built or
  installed, default smoke proof done, final artifact proof done.
- `RecoveryDecision`: failure class, prerequisites, clear condition, allowed
  next action, remaining budget, and final-proof reserve.
- `CommandEvidence`: durable event ids that acceptance and resume can both cite.

The prompt should then render a compact state-backed policy:

- current state;
- current blocker;
- next allowed recovery action;
- prohibited repeated action;
- final proof requirement.

It should not carry all operational memory as prose.

## Immediate Recommendation

Pause new `compile-compcert` detector/profile work.

Create a design document for a bounded long-build substrate and have
`codex-ultra` and `claude-ultra` review it before implementation.

The design should answer these concrete questions:

1. What command/process evidence schema can replace most transcript regex
   interpretation?
2. Which current blockers collapse into generic failure classes?
3. How does `RecoveryBudget` become controller state instead of prompt text?
4. How does acceptance evidence cite durable command event ids while preserving
   backward compatibility with current tool evidence?
5. What transfer fixtures prove the redesign is not CompCert-specific?
6. What anti-accretion gate blocks new profile clauses unless the failure is
   truly domain strategy?

If the redesign is accepted, M6.24 should switch from same-shape proof chasing
to substrate consolidation, then rerun same-shape and transfer checks.
