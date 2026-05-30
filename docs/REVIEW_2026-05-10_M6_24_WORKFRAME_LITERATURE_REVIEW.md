# M6.24 WorkFrame Literature Review

Date: 2026-05-10
Scope: paper-grounded validation of collapsing `implement_v2` model-visible
state into one compact WorkFrame reducer, while retaining typed evidence,
sidecars, replay, and deterministic finish gates.

## Verdict

The WorkFrame direction is scientifically defensible as an engineering
hypothesis, not as a theorem already proven for resident coding agents.

The strongest literature-supported form is:

```text
full-fidelity event/evidence log
  -> deterministic, versioned reducer
  -> compact model-visible WorkFrame
  -> model acts through tools
  -> observations/evidence append to log
  -> reducer recomputes next WorkFrame
```

This matches established patterns in tool-using agents, feedback-driven program
repair, working-memory/cognitive architectures, long-context mitigation, and
observability/provenance work. It is especially well supported if the WorkFrame
is treated as working memory or a belief-state summary, not as the source of
truth.

The redesign becomes weak if "single WorkFrame" means hiding unresolved facts
without retrieval, persisting stale `required_next` state, letting the model or
ad hoc controller patches author hidden truth, or accepting finishes from
summaries rather than typed evidence.

## Local Design Fit

The current design doc already points at the supported shape:

- normal turns should be transcript/tool-result driven;
- `frontier_state_update`, full proof objects, expanded todo, and detailed
  execution contracts should leave the default model contract;
- sidecars should retain full typed evidence, proof, replay, finish gates, and
  recovery data;
- `required_next_action` should be re-derived each turn from latest tool result,
  failure family, and write/verifier provenance.

The proposed WorkFrame is therefore a natural consolidation of the doc's
`hot_path_card`, latest failure projection, compact evidence digest, finish
readiness, and recovery card into one model-visible active-state contract.

## Literature Support

### 1. Interleaved Reasoning And Acting

ReAct supports an agent loop where reasoning traces update action plans and
handle exceptions, while actions gather external observations that ground later
reasoning. This supports a compact loop around latest transcript/tool result,
next action, and observation feedback rather than a model-authored persistent
frontier object.

Source: Yao et al., "ReAct: Synergizing Reasoning and Acting in Language
Models" (2022/ICLR 2023), https://arxiv.org/abs/2210.03629

Implication for WorkFrame: the model should see enough state to choose the next
tool action and interpret the latest observation. Full historical proof state is
not required in every turn if it can be retrieved or cited.

### 2. Feedback-Driven Repair And Bounded Memory

Reflexion uses external or internal feedback, stores verbal reflections in an
episodic memory buffer, and improves later decisions without model weight
updates. Conversational APR alternates patch generation and validation feedback,
explicitly addressing repeated wrong patches and missing testcase information.
Voyager similarly combines execution errors and self-verification in iterative
prompting.

Sources:

- Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning"
  (2023), https://arxiv.org/abs/2303.11366
- Xia and Zhang, "Conversational Automated Program Repair" (2023),
  https://arxiv.org/abs/2301.13246
- Wang et al., "Voyager: An Open-Ended Embodied Agent with Large Language
  Models" (2023), https://arxiv.org/abs/2305.16291
- Bouzenia, Devanbu, and Pradel, "RepairAgent: An Autonomous, LLM-Based Agent
  for Program Repair" (2024), https://arxiv.org/abs/2403.17134

Implication for WorkFrame: the "latest actionable failure" and verifier state
are central. The reducer must preserve enough failure identity to prevent repeat
repairs and enough validation feedback to support semantic debugging.

### 3. Deliberate Search Is Useful, But Should Be Escalated

Tree of Thoughts, Graph of Thoughts, and Language Agent Tree Search show value
from exploring multiple reasoning/action branches, self-evaluation, and
backtracking. They do not imply that every ordinary coding turn should expose a
large thought graph. They support a separate debug/search mode when the compact
state is ambiguous or repeatedly failing.

Sources:

- Yao et al., "Tree of Thoughts: Deliberate Problem Solving with Large Language
  Models" (2023), https://arxiv.org/abs/2305.10601
- Besta et al., "Graph of Thoughts: Solving Elaborate Problems with Large
  Language Models" (2023/AAAI 2024), https://arxiv.org/abs/2308.09687
- Zhou et al., "Language Agent Tree Search Unifies Reasoning Acting and Planning
  in Language Models" (2023/ICML 2024), https://arxiv.org/abs/2310.04406

Implication for WorkFrame: one WorkFrame is sound for the default hot path only
if there is an explicit escalation condition for branch-heavy debugging,
ambiguous causal attribution, or repeated same-family failures.

### 4. Tool Interfaces And State Projection Matter

Toolformer shows that models benefit from deciding when and how to call tools
and incorporate results. SWE-agent shows that the agent-computer interface
itself materially affects automated software engineering performance. CodeAct
shows that executable actions plus observations support dynamic revision.
ReWOO and LLMCompiler support decoupling reasoning, observation, planning, and
execution to improve efficiency.

Sources:

- Schick et al., "Toolformer: Language Models Can Teach Themselves to Use
  Tools" (2023), https://arxiv.org/abs/2302.04761
- Yang et al., "SWE-agent: Agent-Computer Interfaces Enable Automated Software
  Engineering" (2024), https://arxiv.org/abs/2405.15793
- Wang et al., "Executable Code Actions Elicit Better LLM Agents" (2024),
  https://arxiv.org/abs/2402.01030
- Xu et al., "ReWOO: Decoupling Reasoning from Observations for Efficient
  Augmented Language Models" (2023), https://arxiv.org/abs/2305.18323
- Kim et al., "An LLM Compiler for Parallel Function Calling" (2023/ICML 2024),
  https://arxiv.org/abs/2312.04511

Implication for WorkFrame: a small, stable action interface plus compact,
semantically typed observations is more defensible than a broad model-visible
ontology. However, the action/result interface must preserve enough information
for the model to diagnose, not just obey a controller.

### 5. External Verifiers Beat Trusting Natural-Language Plans

Planning-critical papers caution that LLMs are unreliable autonomous planners
unless external verifiers/planners check their outputs. Agentless shows that
simple staged software-engineering procedures can compete with complex
autonomous agents by using localization, repair, and patch selection.

Sources:

- Valmeekam et al., "On the Planning Abilities of Large Language Models: A
  Critical Investigation" (2023), https://arxiv.org/abs/2305.15771
- Kambhampati et al., "LLMs Can't Plan, But Can Help Planning in LLM-Modulo
  Frameworks" (2024), https://arxiv.org/abs/2402.01817
- Xia et al., "Agentless: Demystifying LLM-based Software Engineering Agents"
  (2024), https://arxiv.org/abs/2407.01489

Implication for WorkFrame: the reducer and finish gate should remain
deterministic and evidence-based. WorkFrame can guide the LLM, but it should not
turn LLM-authored plan text into authority.

### 6. Working Memory, Blackboard, And Cognitive Architecture Analogues

Blackboard systems separate a shared problem-solving state from knowledge
sources and control. Soar and ACT-R-style cognitive architectures distinguish
limited active working state from longer-term procedural/declarative/episodic
memory. Human working-memory literature also supports active-state limits and
chunking.

Sources:

- Hayes-Roth, "A Blackboard Architecture for Control" (1985),
  https://doi.org/10.1016/0004-3702(85)90063-3
- Nii, "Blackboard Systems, Part One: The Blackboard Model of Problem Solving
  and the Evolution of Blackboard Architectures" (1986),
  https://dblp.org/rec/journals/aim/Nii86
- Laird, Newell, and Rosenbloom, "SOAR: An Architecture for General
  Intelligence" (1987), https://doi.org/10.1016/0004-3702(87)90050-6
- Miller, "The Magical Number Seven, Plus or Minus Two" (1956),
  https://psychclassics.yorku.ca/Miller/
- Cowan, "The Magical Number 4 in Short-Term Memory" (2001),
  https://doi.org/10.1017/S0140525X01003922

Implication for WorkFrame: one compact active frame is reasonable if full
resident state remains queryable and if control does not depend on stale or
uninspectable summaries. WorkFrame is closest to a blackboard control focus or
working-memory chunk, not a complete memory.

### 7. Long-Context Results Support Compression With References

Long-context studies show that simply placing more text in context does not
guarantee reliable use; relevant information can be missed, especially when
buried among distractors. This supports reducing ordinary prompt surface area
and keeping current failure, current goal, and current evidence refs prominent.

Sources:

- Liu et al., "Lost in the Middle: How Language Models Use Long Contexts"
  (2023/TACL 2024), https://arxiv.org/abs/2307.03172
- Li et al., "LongBench: A Bilingual, Multitask Benchmark for Long Context
  Understanding" (2023), https://arxiv.org/abs/2308.14508

Implication for WorkFrame: prompt shrinkage is not merely cost optimization; it
can improve reliability by removing distractors. The caveat is that compression
must be loss-aware and backed by expansion refs.

### 8. Observability, Replay, And Provenance

AgentOps work frames observability as a safety requirement for autonomous,
non-deterministic agents and identifies lifecycle artifacts that should be
traced. Recent system-level observability work argues for correlating high-level
intent with low-level effects. This aligns with mew's sidecar/replay design.

Sources:

- Dong, Lu, and Zhu, "AgentOps: Enabling Observability of LLM Agents" (2024),
  https://arxiv.org/abs/2411.05285
- Zheng et al., "AgentSight: System-Level Observability for AI Agents Using
  eBPF" (2025), https://arxiv.org/abs/2508.02736
- W3C PROV overview/specification family for provenance modeling,
  https://www.w3.org/TR/prov-overview/

Implication for WorkFrame: hiding detail from the model is acceptable only if
the system has stronger machine-readable traces, causal links, and replay than
the prompt previously provided.

## Theoretical Assessment

### Why The Direction Is Sound

1. A coding agent operates in a partially observed, changing environment. A
   reducer-derived WorkFrame is analogous to a belief-state or working-memory
   summary over the full event log.
2. The literature favors observe-act-feedback loops with compact relevant
   observations, not unbounded prompt history.
3. Program repair literature supports carrying validation feedback forward, but
   it does not require every full execution artifact in the model prompt.
4. Tool-use and ACI papers support investing in the interface shape. WorkFrame
   is exactly that interface.
5. Planning-limitations work supports deterministic verifiers and reducer-owned
   state over LLM-authored plan authority.
6. Long-context work supports removing distracting state, provided refs allow
   recovery of hidden details.

### What Is Not Proven

No surveyed paper proves that this exact WorkFrame schema is optimal for a
resident coding agent with finish gates, replay artifacts, and context
compression. The literature supports the architectural principle:

- compact active state;
- full external evidence;
- deterministic control/gating;
- feedback-driven repair;
- auditable traces;
- escalation when compact state is insufficient.

The design should therefore present WorkFrame as a falsifiable architecture
choice with replay and ablation evidence, not as settled science.

## Risks

1. Over-compression. A single frame can hide a stale assumption, a second
   unresolved blocker, or the cause of a verifier failure. Mitigation: one
   latest failure per active family when needed, expansion refs, recovery cards,
   and repeat-loop metrics.
2. Stale state. `required_next` can become a hidden plan if copied across turns.
   Mitigation: recompute it from versioned reducer inputs every turn; omit it
   when no safe next action is derivable.
3. Loss of model autonomy. If the reducer over-prescribes, the model becomes a
   script follower and may miss better probes. Mitigation: `required_next` is
   advisory/guarded except for safety-critical `forbidden_next`; allow inspect,
   probe, patch, verify, and finish choices when ambiguity remains.
4. Reducer bugs. A bad reducer can hide real evidence while appearing compact.
   Mitigation: pure deterministic reducer, golden replay fixtures, property
   tests, derivation logs, and WorkFrame diffs per turn.
5. Hidden evidence. The model may be asked to cite or debug evidence it cannot
   inspect. Mitigation: compact evidence digest plus explicit `read_evidence` or
   existing output-ref expansion path.
6. Poor credit assignment. Latest failure alone may not say which edit caused
   it. Mitigation: include `changed_sources`, last successful mutation,
   last verifier, failure family, and causal refs.
7. False finish safety. Summary-based finish readiness can bypass old gates.
   Mitigation: finish only accepts typed evidence/oracle refs; legacy safety
   asserts remain until replay proves equivalence.
8. Sidecar bloat. Prompt shrinkage can move complexity into unbounded resident
   JSON. Mitigation: sidecar byte budgets, per-family growth metrics, and red
   gates.
9. Branch-heavy tasks. A single WorkFrame may be too narrow for tasks requiring
   alternative hypotheses. Mitigation: explicit debug/search escalation based on
   repeated same-family failures, ambiguous failure classification, or unknown
   causal ownership.

## Design Constraints To Add To The Mew Doc

### WorkFrame Contract

Define `WorkFrame` as the only default model-visible active-state object:

- `goal`: immutable task objective or current scoped objective, with source ref.
- `phase`: enum such as `inspect`, `patch`, `verify`, `finish`, `blocked`,
  `recover`; transitions are reducer-owned.
- `latest_actionable_failure`: failure family, short detail, recency/version,
  and causal refs.
- `required_next`: present only when deterministically derivable from latest
  failure/provenance; otherwise absent.
- `forbidden_next`: safety or known-bad actions only, with reason/ref.
- `changed_sources`: paths changed since last accepted verifier, with write refs.
- `verifier_state`: latest verifier class, pass/fail/unknown, artifact refs, and
  stale/valid marker.
- `finish_readiness`: `not_ready`, `ready_with_refs`, or `blocked`, with missing
  obligations.
- `evidence_refs`: compact ids for command runs, outputs, write records,
  verifier evidence, typed evidence, and oracle refs.
- `reducer_meta`: reducer version, input event-log hash/range, repo diff hash
  when applicable, generated timestamp, and field derivation reasons.

### Reducer Rules

- WorkFrame is deterministic from event log, typed evidence, sidecar state,
  config, and current repo/write provenance.
- WorkFrame is not model-authored. Model-emitted state updates are ignored or
  stored as advisory notes outside the source of truth.
- `required_next` is never persisted as planner truth; it is recomputed.
- If evidence is ambiguous, the reducer must expose ambiguity or omit the
  prescriptive field.
- Every non-obvious field carries a reason code and evidence refs.
- Reducer output is bounded, but not by silently dropping active blockers.
- Schema is versioned; replay can regenerate historical WorkFrames or identify
  intentional migration behavior.

### Evidence And Replay Rules

- Event log, tool calls/results, write provenance, typed evidence, oracle bundle,
  and finish gate remain the source of truth.
- Finish readiness is computed from typed evidence and legacy safety gates, not
  from model prose.
- Hidden evidence must be retrievable by refs; the model should never be asked
  to cite an opaque id without a digest or expansion path.
- Replay must validate call/result pairing, write safety, reducer output,
  finish decisions, and WorkFrame size/field invariants.

### Compression And Recovery Rules

- Context compression stores enough to rebuild one WorkFrame plus refs to the
  full event log.
- Recovery mode may include a capped `frontier_summary`, but default mode should
  not expose full frontier/proof/todo objects.
- Repeated same-family failures trigger either expansion or search/debug mode,
  not another tighter summary.
- Prompt bytes and sidecar bytes are both gated; prompt savings do not justify
  unbounded sidecar growth.

### Evaluation Rules

Validate with:

- unit/property tests for reducer determinism, idempotence, stale-input
  invalidation, and field ownership;
- golden replay fixtures for current failure families;
- adversarial fixtures where a hidden stale verifier, shell mutation, or invalid
  evidence ref must block finish;
- micro next-action checks comparing current prompt versus WorkFrame prompt;
- ablation against the current prompt on first edit turn, first verifier turn,
  repeated same-family loops, prompt bytes, sidecar growth, false finish blocks,
  and total turns/tool calls;
- WorkFrame diff artifacts per turn for human debugging.

## Recommended Design Wording

Add a section close to the "Three Surfaces" split:

```text
The WorkFrame is the only ordinary model-visible active-state object. It is a
bounded reducer output over the resident event/evidence log, not a durable source
of truth and not a model-authored plan. Full fidelity remains in sidecars and
replay artifacts. Each WorkFrame field is versioned, evidence-referenced, and
recomputable. If the reducer cannot justify a prescriptive next action, the field
is omitted and the model retains ordinary inspect/probe/patch/verify autonomy.
```

And add this close condition:

```text
Do not close HOT_PATH_COLLAPSE unless replay can regenerate the WorkFrame for
each saved artifact and explain every prescriptive field by citing reducer input
events, typed evidence, write provenance, or finish-gate obligations.
```

## Bottom Line

The WorkFrame reducer is a sound direction if it collapses model-visible working
state while strengthening the evidence/replay substrate. It is not sound if it
collapses the actual state of record. The defensible scientific claim is:

> A resident coding agent should expose a compact, current, evidence-referenced
> working frame to the model, while storing full-fidelity traces and typed
> evidence outside the prompt and using deterministic reducers/verifiers to
> decide recovery and finish safety.

That claim is well aligned with the literature. The remaining burden is
engineering validation: reducer correctness, recovery fidelity, prompt/sidecar
budgets, and replay-based proof that hidden state did not become hidden failure.
