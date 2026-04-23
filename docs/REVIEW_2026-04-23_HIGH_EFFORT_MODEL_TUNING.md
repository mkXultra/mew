# M6.13 High-Effort Model Tuning — Scientific Reference

Date: 2026-04-23.
Status: **reference document** (Phase 0 prerequisite; not a proposal,
not a close gate, not a commitment).
Paired with: `docs/REVIEW_2026-04-22_M6_9_EXPECTED_VALUES.md`.
Draft provenance: drafted by `codex-ultra` (OpenAI family) and reviewed on 2026-04-23 by `claude-ultra` (Anthropic) and `oc-zai-coding-plan` / `glm-5.1` (zai).

## 1. Purpose

M6.13 is the future milestone tentatively described as a "deliberation lane": a bounded path that escalates harder tasks to higher-effort reasoning models or higher
test-time-compute settings. Before mew designs that lane, it needs two kinds of grounding:

- **Literature grounding**: what 2024-2026 research and vendor documentation actually say about inference-time compute, extended thinking, reasoning effort, and
  cost-quality tradeoffs.
- **Source-code grounding**: how the current reference codebases (`codex-rs`, `claude-code`) expose and route reasoning effort in practice.

This document records that grounding.

It is intentionally **not**:

- a design proposal for M6.13,
- a default-model decision,
- a budget decision,
- a commitment to any vendor,
- a close-gate artifact,
- a ROADMAP edit,
- or an instruction to change the active M6.11 milestone.

Its job is narrower:

- name the design space honestly,
- separate published findings from local inference,
- show where current agent implementations already expose effort controls,
- identify the failure modes mew must account for if it adds a higher-effort lane,
- and preserve provisional hypotheses that M6.13 can test later.

The intended reader is a future implementer or reviewer who needs an evidence-backed answer to the question: "If mew adds a high-effort deliberation lane, what is the
landscape, what do existing agents do, and where are the likely wins and traps?"

## 2. Scope

### In scope

- Public 2024-2026 reasoning-effort / extended-thinking model surfaces from OpenAI, Anthropic, and Google
- Primary literature on inference-time compute / test-time scaling
- Exact `file:line` analysis of:
  - `references/fresh-cli/codex/`
  - `references/fresh-cli/claude-code/`
- M6.11 blocker-code mapping as an escalation-design input
- M6.9 Phase-2 deliverables most likely to benefit from a deliberation lane
- Failure modes relevant to a durable-state coding agent: schema drift, refusal behavior, latency, cost, and overthinking
- A provisional candidate matrix and adaptation rubric for future M6.13 measurement work

### Out of scope

- Any implementation of M6.13
- Any new telemetry or schema change in the mew repo
- Any ROADMAP reordering or milestone activation decision
- Any formal close gate
- Any requirement that mew must adopt a particular provider
- Any requirement that mew must adopt a particular effort level
- Fine-tuning, weight updates, or model training
- Benchmarks or numbers not supported by either:
  - a cited paper,
  - an official vendor document,
  - or an explicitly marked empirical observation

### Relationship to existing docs

- **Formatting anchor**: `docs/REVIEW_2026-04-22_M6_9_EXPECTED_VALUES.md` defines the scientific-reference shape this document follows.
- **Research-heavy milestone precedent**: `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md` shows how mew records research-motivated design surfaces before coding.
- **Current engineering milestone**: `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md` defines the M6.11 blocker taxonomy and recovery vocabulary that M6.13 may later use as
  escalation inputs.
- **Not a gate**: this document supplements future M6.13 design work; it does not replace any future design spec or any eventual close artifact.

### Relationship to active milestone timing

M6.11 Loop Stabilization remains the active milestone. This document is future-facing research preparation only. It exists now because M6.13 will likely reuse M6.11's
blocker taxonomy and because the external reasoning-effort landscape is moving quickly enough that Phase 0 research should be recorded while current sources are
inspectable.

## 3. Reasoning-effort model landscape (2024-2026)

Between 2024 and 2026, frontier vendors converged on the same broad move: preserve one model family, expose a
compute-control surface, and trade latency / token spend for better performance on harder tasks. The controls are not
isomorphic. OpenAI mixes model-family choice and `reasoning.effort`; Anthropic mixes `effort` with adaptive or manual
thinking; Google uses explicit thinking budgets on Gemini 2.5. The literature calls the general phenomenon
**test-time compute** or **inference-time compute**, which is broader than any vendor-specific `high` / `xhigh` label.

### 3.1 Vendor surfaces

Amended 2026-04-23: Anthropic model names in this subsection were re-checked against live public docs. Vendor-model rows are the most time-sensitive part of this
document and should be refreshed again before M6.13 design begins.

| Provider / family | Public control surface | Evidence relevant to M6.13 |
| --- | --- | --- |
| OpenAI `o1`, `o1-pro`, `o3`, `o3-pro` | model-family choice, with pro variants packaging more compute | Official model pages describe these as reasoning models that think harder or use more compute; `o3-pro` may take several minutes. Sources: OpenAI model pages for `o1`, `o1-pro`, `o3`, `o3-pro`. |
| OpenAI GPT-5 family | `reasoning.effort` | `GPT-5` exposes `minimal/low/medium/high`; `GPT-5.1` exposes `none/low/medium/high`; `GPT-5.2` and `GPT-5.4` expose `none/low/medium/high/xhigh`. Sources: OpenAI model pages for `gpt-5`, `gpt-5.1`, `gpt-5.2`, `gpt-5.4`. |
| OpenAI GPT-5 Codex family | `reasoning.effort` on coding-tuned models | `GPT-5.2-Codex` and `GPT-5.3-Codex` expose `low/medium/high/xhigh`. Source: OpenAI model pages for `gpt-5.2-codex`, `gpt-5.3-codex`. |
| OpenAI pro GPT-5 variants | limited but heavier effort surface | `GPT-5 pro` supports only `high`; `GPT-5.2 pro` and `GPT-5.4 pro` expose `medium/high/xhigh`; pro pages explicitly warn some requests may take several minutes. Sources: OpenAI model pages for `gpt-5-pro`, `gpt-5.2-pro`, `gpt-5.4-pro`. |
| Anthropic Claude 4 family; `Claude Mythos Preview` separate | `effort` plus `thinking` mode | As of 2026-04-23, Anthropic's live models overview lists `Claude Opus 4.7`, `Claude Sonnet 4.6`, and `Claude Haiku 4.5`, and treats `Claude Mythos Preview` as a separate research-preview model rather than a Claude 4 family label. Anthropic documents `high` as default, `effort` affecting all response tokens, and adaptive thinking as the recommended path on newer models. Sources: Anthropic models overview, effort, adaptive-thinking, and extended-thinking docs. |
| Google Gemini 2.5 | `thinkingBudget` | Gemini 2.5 Pro uses dynamic thinking by default, cannot disable thinking, and exposes a documented `thinkingBudget` range; Gemini 2.5 Flash allows `0` to disable and `-1` for dynamic thinking. Source: Gemini thinking docs. |

Three structural consequences matter for mew:

- some providers expose a **category hint**,
- some expose an explicit **budget**,
- and some still encode "harder thinking" mainly as **model-family selection**.

### 3.2 Literature consensus

The literature supports the existence of a cost-quality frontier, but not a universal rule that more compute should be
the default.

| Source | Main finding | M6.13 relevance |
| --- | --- | --- |
| Snell et al., arXiv:2408.03314 | adaptive test-time compute allocation is more than 4x as efficient as naive best-of-N on their setting; extra compute can beat a much larger model when the base model already has non-trivial success | selective escalation, not blanket escalation |
| Muennighoff et al., arXiv:2501.19393 | simple budget forcing already yields measurable reasoning gains; AIME24 example rises from 50% to 57% | extra compute can matter even with simple mechanisms |
| DeepSeek-R1, arXiv:2501.12948 | RL can induce self-reflection, verification, and stronger reasoning behaviors | model-side reasoning gains are real, but product-layer behavior still matters |
| Parashar et al., arXiv:2502.12521 | no single inference-time technique consistently performs well across all reasoning and planning tasks | trigger policy must be task-sensitive |
| Sadhukhan et al., arXiv:2506.05333 | practical test-time scaling depends on model-size thresholds plus computation and memory-access costs | "more compute on a small model" is not always the best buy |
| Lin et al., arXiv:2504.13171 | stateful or repeated-context tasks can benefit from offline or amortized compute | mew may sometimes prefer internalization over repeated high-effort calls |

Amended 2026-04-23: arXiv:2502.12521, arXiv:2506.05333, and arXiv:2504.13171 were re-checked against live arXiv abstracts and the summary claims were tightened to stay
within the published abstracts.

The transferable conclusion is narrow but strong:

- harder thinking helps some hard tasks,
- the gains are difficulty-dependent,
- and the right mew question is not "which model is smartest?" but "which task shapes justify extra inference-time
  compute?"

### 3.3 Comparison rules

For later M6.13 design work, the following comparison rules should stay explicit:

- `high` is not semantically identical across vendors;
- a pro model and an `xhigh` effort tier are not the same thing;
- adaptive-thinking systems expose a policy surface, not a fixed compute budget;
- `thinkingBudget` and `reasoning.effort` are related but non-equivalent;
- structured-output support is orthogonal to raw reasoning strength;
- and older o-series results remain historically useful even if GPT-5-era surfaces become the default implementation
  path.

These rules are simple, but they prevent a large class of category mistakes in later M6.13 discussion.

## 4. codex-cli source analysis

Inspected tree: `references/fresh-cli/codex/`.

Codex exposes reasoning effort as a typed capability surface, not a loose string.

- `references/fresh-cli/codex/codex-rs/protocol/src/openai_models.rs:43-50` defines canonical values:
  `None`, `Minimal`, `Low`, `Medium`, `High`, `XHigh`.
- `references/fresh-cli/codex/codex-rs/protocol/src/openai_models.rs:129-132` records both
  `default_reasoning_effort` and `supported_reasoning_efforts` per model preset.
- `references/fresh-cli/codex/codex-rs/protocol/src/openai_models.rs:490-524` maps a requested effort to the nearest
  supported effort.

Codex also exposes this surface directly to users and sub-agents.

- `references/fresh-cli/codex/docs/config.md:91-96` documents `plan_mode_reasoning_effort` and states that Plan mode
  defaults to `medium` when unset.
- `references/fresh-cli/codex/codex-rs/core/src/config/mod.rs:472-481` defines both
  `model_reasoning_effort` and `plan_mode_reasoning_effort`.
- `references/fresh-cli/codex/codex-rs/tools/src/agent_tool.rs:535-539` and
  `references/fresh-cli/codex/codex-rs/tools/src/agent_tool.rs:569-572` expose optional sub-agent
  `reasoning_effort` overrides.
- `references/fresh-cli/codex/codex-rs/tools/src/agent_tool.rs:683-709` renders visible models together with their
  default and supported effort lists.

The inspected code contains several narrow task-shaped defaults:

- Plan mode:
  `references/fresh-cli/codex/codex-rs/models-manager/src/collaboration_mode_presets.rs:35-42`
  hard-codes `Medium`, and
  `references/fresh-cli/codex/codex-rs/tui/src/chatwidget.rs:9586-9590`
  applies the override when Plan mode activates.
- Memory phase 1:
  `references/fresh-cli/codex/codex-rs/core/src/memories/mod.rs:35-38`
  uses `gpt-5.4-mini` at `Low`, and
  `references/fresh-cli/codex/codex-rs/core/src/memories/phase1.rs:163-174`
  threads that value into request context.
- Memory phase 2:
  `references/fresh-cli/codex/codex-rs/core/src/memories/mod.rs:67-70`
  uses `gpt-5.4` at `Medium`, and
  `references/fresh-cli/codex/codex-rs/core/src/memories/phase2.rs:316-324`
  writes that into the consolidation agent config.
- Guardian review:
  `references/fresh-cli/codex/codex-rs/core/src/guardian/review.rs:372-402`
  prefers `Low` when supported, otherwise falls back to model default or inherited effort.

What I did **not** find is a general "hard task detector" that dynamically escalates arbitrary work from medium to high
or xhigh. The implemented pattern is narrower: explicit user/config override, model capability declaration, sub-agent
override, and a few role-specific defaults. That is useful precedent, but not a complete mew escalation policy.

## 5. claude-code source analysis

Inspected tree: `references/fresh-cli/claude-code/`.

Claude Code also exposes a typed effort surface, but the routing pattern is different.

- `references/fresh-cli/claude-code/src/utils/effort.ts:13-18` defines `low`, `medium`, `high`, `max`.
- `references/fresh-cli/claude-code/src/tools/AgentTool/loadAgentsDir.ts:85-87` and
  `references/fresh-cli/claude-code/src/tools/AgentTool/loadAgentsDir.ts:115-117`
  allow agents to declare `effort`.
- `references/fresh-cli/claude-code/src/utils/effort.ts:152-166`
  resolves effort with precedence:
  env override -> app-state effort -> model default,
  and downgrades `max` to `high` on unsupported models.
- `references/fresh-cli/claude-code/src/services/api/claude.ts:1458-1569`
  injects the resolved effort into API params.

AgentTool workers mostly inherit session effort unless an agent explicitly overrides it.

- `references/fresh-cli/claude-code/src/tools/AgentTool/runAgent.ts:481-497`
  uses agent-defined effort when present, else `state.effortValue`.
- `references/fresh-cli/claude-code/src/tools/AgentTool/builtInAgents.ts:45-69`
  enables built-in Explore, Plan, and Verification roles.
- `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/exploreAgent.ts:76-79`
  routes Explore to `inherit` for Anthropic-internal users and `haiku` for external users, explicitly for speed.
- `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/planAgent.ts:87-91`
  sets Plan to `model: 'inherit'` with no explicit effort override.
- `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts:148-151`
  sets Verification to `model: 'inherit'` with no explicit effort override.

Claude Code also routes *thinking mode* itself.

- `references/fresh-cli/claude-code/src/utils/queryContext.ts:149-153`
  defaults to adaptive thinking unless disabled.
- `references/fresh-cli/claude-code/src/services/api/claude.ts:1596-1628`
  chooses adaptive thinking when the model supports it and otherwise falls back to explicit thinking budgets.

Finally, Claude Code already has a direct user-request escalation path:

- `references/fresh-cli/claude-code/src/utils/thinking.ts:19-30`
  detects `ultrathink`;
- `references/fresh-cli/claude-code/src/utils/attachments.ts:1446-1451`
  turns it into a `high`-effort attachment;
- `references/fresh-cli/claude-code/src/utils/messages.ts:4170-4176`
  converts that attachment into a meta instruction for the current turn.

The inspected source therefore supports three claims:

- effort is first-class,
- sub-agents mostly inherit unless explicitly overridden,
- and reviewer/user-command escalation is a real precedent.

What it does **not** show is a broad automatic task-type-to-effort router. Like Codex, Claude Code has useful
handholds for M6.13, but not a full answer.

## 6. Cost-quality frontier (from literature)

The literature describes a Pareto frontier, not a monotone guarantee. More compute can help, but the return depends on
task difficulty, base-model competence, and the cost of the inference method itself.

| Source | Concrete observation | M6.13 interpretation |
| --- | --- | --- |
| arXiv:2408.03314 | adaptive allocation beats naive best-of-N; extra test-time compute can outperform a much larger model when the base model already has non-trivial success | escalation should be selective and difficulty-aware |
| arXiv:2501.19393 | budget forcing raises performance, but the gain is bounded rather than endless | medium -> high -> xhigh is not a linear ladder |
| arXiv:2502.12521 | no single inference-time technique wins across all reasoning/planning tasks | one universal trigger rule is unlikely to be optimal |
| arXiv:2506.05333 | practical scaling depends on model-size thresholds and memory-access costs | spending more compute on a small or ill-suited model can be wasteful |
| arXiv:2504.13171 | repeated-context tasks may benefit from amortized offline compute | durable internalization can beat repeated hard calls |

The best literature-supported cases for higher effort are tasks with hidden multi-step structure, verification needs,
or ambiguous design/search spaces. The weakest cases are retrieval, exact formatting, symbol lookup, and mechanical edit
transforms. For mew, that suggests likely gains on abstract design/debug/postmortem work and weak gains on tiny
write-ready drafting. The literature does **not** give M6.13 a provider-independent conversion table for `medium`,
`high`, and `xhigh`; any such mapping would be translated or directional, not direct.

## 7. Failure modes at high effort

High-effort lanes increase reasoning capacity and also enlarge the failure surface. The relevant question for mew is not
"can the model think harder?" but "what breaks when a durable-state coding loop asks it to think harder?"

| Failure mode | Evidence state | Why it matters for mew |
| --- | --- | --- |
| Schema adherence drift | Mixed: provider docs + empirical observation | Longer outputs and richer reasoning create more chances to violate exact JSON / tool contracts; Google explicitly documents schema-subset limits and semantic-validation requirements for structured outputs. |
| Model-family capability mismatch | Direct vendor evidence | Not every high-end reasoning model supports the same output surfaces; `GPT-5.2 pro` explicitly lacks structured outputs, so raw "use the strongest model" can conflict with contract strictness. |
| Refusal / safe-completion inflation | Empirical observation, not strong literature | I did not find a robust cross-effort refusal curve; M6.13 should measure refusal rate rather than assume it. |
| Latency / budget blow-up | Strong vendor and literature support | OpenAI pro pages warn of multi-minute requests; Anthropic documents `high` / `max` token growth; Gemini documents large thinking budgets; test-time-scaling papers treat latency as a first-class cost. |
| Overthinking / shape drift | Empirical observation | Harder-reasoning lanes can return essays, replans, or abstract analysis when mew needs a narrow artifact. |
| Contract-limit confusion | Direct repo-local inference | Extra reasoning does not fix missing cached text, stale anchors, paired-write policy, or validator invariants. |

Local mew relevance is already visible in M6.11. `model_returned_non_schema` is a first-class blocker in
`src/mew/patch_draft.py:11-24` and in `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:487-498`, which means schema
discipline is not hypothetical future risk; it is an existing control surface. The safest M6.13 reading is therefore:

- treat refusal behavior as a telemetry question,
- treat schema behavior as both a model and contract question,
- and treat latency as a budget/governance question, not just a performance nuisance.

### 7.1 Observation surfaces implied by these risks

Example-only, non-binding observation surfaces follow; they are listed to anchor future measurement discussion, not to prescribe a final telemetry spec.

If M6.13 later lands, these failure modes suggest a minimum observation set even before any numeric targets are chosen:

- requested model / effort,
- effective model / effort after provider or wrapper adjustment,
- wall-clock latency,
- token spend or budget-spend proxy,
- schema-valid vs non-schema outcome,
- refusal vs safe-completion vs answer,
- blocker code before escalation,
- blocker code after escalation,
- reviewer acceptance of the escalated result,
- and whether anything useful was internalized into durable memory afterward.

This is still reference-only at this stage; it is listed here so later M6.13 measurement work has a clean bridge from
failure taxonomy to telemetry design.

## 8. mew-specific hypotheses (for later testing, not requirements)

The likely high-value beneficiaries are the M6.9 Phase-2 surfaces that already ask for abstraction rather than local
editing.

| Surface | Why deliberation may help | Local grounding |
| --- | --- | --- |
| D4 reasoning-trace harvester | distills `(situation, reasoning, verdict)` triples and shallow/deep abstractions; likely benefits from better synthesis | `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md:628-637`; `docs/REVIEW_2026-04-22_M6_9_EXPECTED_VALUES.md:357-380` |
| D1 link-evolving consolidation | decides whether new durable entries refine, supersede, or relate to older ones | `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md:610-614`; `docs/REVIEW_2026-04-22_M6_9_EXPECTED_VALUES.md:298-317` |
| D3 hindsight harvester | reinterprets blocked or reverted trajectories into reusable reviewer-queue candidates | `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md:619-627`; `docs/REVIEW_2026-04-22_M6_9_EXPECTED_VALUES.md:340-355` |
| `review_rejected` on conceptual findings | may indicate a genuine abstraction deficit rather than missing context | M6.11 blocker taxonomy |
| `no_material_change` on abstract tasks | may indicate weak synthesis or weak search over alternatives | M6.11 blocker taxonomy |

Any future evaluation of these hypotheses has to isolate deliberation effort itself from confounders such as fresher state, clearer reviewer criteria, or richer memory
retrieval/internalization.

The weakest candidates are tasks where exactness dominates abstraction:

- file-pair writes,
- symbol index lookups,
- old-text anchoring,
- patch translation into deterministic validators,
- paired source/test enforcement,
- and other mechanical edits where the correct answer is already tightly constrained by cached windows and policy.

That distinction matches the M6.11 tiny-lane lesson: narrow write-ready drafting benefited from tighter low-effort
contracts, not from inherited high-effort free-form turns.

## 9. Escalation trigger design principles (provisional)

The strongest Phase-0 trigger surface is still M6.11's blocker taxonomy, because it is explicit, durable-state
compatible, and already paired with recovery actions.

| Blocker code | Likely class | Provisional deliberation reading |
| --- | --- | --- |
| `missing_exact_cached_window_texts` | state-limit | refresh state first |
| `cached_window_text_truncated` | state-limit | refresh state first |
| `stale_cached_window_text` | state-limit | refresh state first |
| `old_text_not_found` | state-limit / anchoring | refresh or re-read before any escalation |
| `ambiguous_old_text_match` | contract-limit | narrow anchor, not harder thinking |
| `overlapping_hunks` | contract-limit | merge/split hunks; escalate only if repeated abstract rewrite failure remains |
| `no_material_change` | possible abstraction-limit | plausible candidate on abstract tasks |
| `unpaired_source_edit_blocked` | policy-limit | add paired test edit, not more compute |
| `write_policy_violation` | policy-limit | revise scope; no escalation benefit expected |
| `model_returned_non_schema` | contract/model mixed | tighten wrapper first; escalate cautiously |
| `model_returned_refusal` | provider/prompt mixed | inspect refusal; alternate model or reformulation may help |
| `review_rejected` | semantic/model mixed | plausible fit when findings are conceptual |

Other provisional trigger families remain useful:

- **By reviewer command**:
  Claude Code's `ultrathink` path is a clear precedent for explicit human-triggered escalation.
- **By cost budget**:
  a deliberation lane without budget caps is a leak, not a lane.
- **By task-shape tag**:
  M6.9 already distinguishes `task_shape=abstract` from more mechanical work, making abstract-task gating a plausible
  candidate trigger.

The anti-patterns are equally important:

- infinite escalation without new state,
- budget runaway,
- collapsing tiny-lane work into a huge free-form fallback,
- assuming schema problems are solved by intelligence alone,
- delegation without durable internalization afterward,
- **State-refresh-before-escalation**: do not escalate when the blocker code suggests the cached window is stale; refresh state first, attempt the tiny lane once more, and
  only then escalate.
- **Requested-vs-effective effort drift**: when a wrapper remaps an unsupported effort to the nearest supported one, log both requested and effective effort or
  escalation accounting becomes unreliable.
- **Schema-strict to schema-lax routing**: never escalate from a model known to respect the patch-draft schema to one with weaker JSON adherence; this often replaces the
  original blocker with `model_returned_non_schema`.
- **Schema regression loop**: escalation-to-solve-schema-failure can itself fail the schema and reproduce the same blocker; trigger design should detect and halt this
  loop shape, for example with bounded escalation attempts per blocker-instance-id.

## 10. Model candidate matrix

This matrix is intentionally qualitative.

- Capability / cost / latency are order-of-magnitude only.
- Values are estimated from official docs and industry reports unless otherwise stated.
- `schema_strictness` means: "how naturally compatible this candidate appears with strict JSON/typed-contract workflows," not a formal benchmark score.
- Open-weight rows are included to survey the design space honestly, not to imply that self-hosting is already the preferred M6.13 path.

| Candidate lane | Example surface | Relative capability | Relative cost | Relative latency | Schema strictness | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| OpenAI standard coding lane | GPT-5.1 at `low` / `medium` | Medium-high | Low-medium | Interactive | High | Good baseline comparison point for coding |
| OpenAI heavier coding lane | GPT-5.1 `high`, GPT-5.4 `high` | High | Medium-high | Interactive to slower interactive | High | Same family, more compute, easier A/B than model-family switches |
| OpenAI maximal coding lane | GPT-5.4 `xhigh`, GPT-5.3-Codex `xhigh` | High-very high | High | Slower interactive | Medium-high | Candidate worth testing for bounded abstract coding tasks |
| OpenAI pro lane | GPT-5 pro, GPT-5.4 pro | Very high | Very high | Can be multi-minute | Medium-high | Good for rare high-value tasks, not default loop turns |
| OpenAI legacy reasoning lane | o3, o3-pro, o1-pro | High-very high | Medium to extreme | Slow to very slow | Medium-high | Useful as conceptual reference; likely less natural as long-term default |
| Claude balanced thinking lane | Sonnet 4.6 adaptive `medium` / `high` | High | Medium-high | Interactive to slower interactive | Medium | Adaptive thinking may skip or deepen by request |
| Claude maximal thinking lane | Claude Opus 4.7 adaptive `high` / `xhigh` / `max` | Very high | High-very high | Slow | Medium | Likely fit for abstract-reasoning evaluation; effort is policy-like, not a deterministic budget |
| Gemini deep thinking lane | Gemini 2.5 Pro dynamic or large `thinkingBudget` | High | Medium-high | Slow interactive to slow | Medium | Budget surface is explicit; cannot disable thinking on 2.5 Pro |
| Gemini bounded thinking lane | Gemini 2.5 Flash with moderate budget | Medium-high | Low-medium | Interactive | Medium | Useful where bounded budget matters more than maximal depth |
| DeepSeek open reasoning lane | DeepSeek-R1 / `deepseek-reasoner` | High | Low-medium | Interactive to slower interactive | Low-medium | Open-weight reasoning lane worth surveying; cost profile looks attractive, but mew-specific tool/schema behavior would need direct evaluation |
| DeepSeek R2-class lane | unconfirmed `DeepSeek-R2` public identifier as of 2026-04-23 | Unknown | Unknown | Unknown | Unknown | Included only so the design-space survey does not hide an often-mentioned family label; do not treat this as a verified shipping surface without first-party docs |
| Meta open-weight reasoning lane | Meta Llama reasoning-tuned variants without a first-party effort knob | Medium-high | Self-hosting-dependent | Deployment-dependent | Low-medium | Useful contrast row for open-weight routing; likely less natural for schema-strict patch-draft turns without extra wrapper work |
| Memory enrichment lane | same base model plus richer M6.9 retrieval/internalization | Variable | Low-medium | Interactive | High | Some hard tasks may improve more from better recall of prior reviewer preferences and blockers than from harder model effort alone |

### Matrix reading caution

This table is not a recommendation list.

It exists so future M6.13 design work can ask concrete questions such as:

- do we want same-family effort changes first?
- do we want adaptive-thinking providers or explicit-budget providers?
- do we want coding-optimized models or general reasoning models?
- where does schema strictness matter more than raw reasoning depth?

### 10.1 Reading rules

The matrix is easiest to read in three passes:

- first by **lane fit**:
  same-family effort increases are easier to evaluate than family switches;
- then by **operational cost**:
  interactive lanes and multi-minute lanes belong in different parts of the loop;
- then by **contract fit**:
  some candidates may be excellent abstract reasoners but awkward fits for strict schema-bound turns.

That ordering matters because M6.13 is not choosing "the smartest model overall." It is choosing where a bounded
deliberation lane can add value without destabilizing mew's existing contracts.

## 11. Open questions for M6.13

The design space remains open. At minimum, M6.13 would need to answer:

1. What is the first escalation step: same model at higher effort, or a different model family?
2. What counts as "benefited from deliberation": reviewer acceptance, fewer retries, better future recall, or all three?
3. Where does useful deliberation output land: reasoning trace, task template, hindsight queue, or reviewer steering?
4. What is the budget shape: per turn, per task, per session, or per proof run?
5. What fixtures prove usefulness: abstract refactor, stubborn review rejection, repeated hindsight relabeling, or other replay shapes?
6. What precision / recall target should automatic escalation meet?
7. Can the high-effort lane be shown to remain schema-strict under the same patch-draft contract, rather than relying on a later free-form compilation step to recover
   validity?
8. Should M6.13 begin provider-agnostic, or is a single-provider first version acceptable behind a stable abstraction?
9. How visible should escalation be to the reviewer?
10. What is the escalation latency budget before a deliberation-lane attempt itself becomes a `#401`-class failure?
11. For the §8 `review_rejected` / `no_material_change` abstract-task hypothesis, what exact matched baseline cohort, same-state control, and stopping rule would let
    M6.13 conclude "escalation helped" or "escalation did not help" falsifiably rather than narratively?
12. For D1/D3/D4 abstraction surfaces, what fixed replay set, predeclared success delta, and schema-failure ceiling would be enough to reject the claim that higher effort
    improved synthesis?
13. When escalation fails, how is blame partitioned among model, trigger, budget policy, and prompt / contract?

## 12. Why not just use codex-cli as-is

This question matters because Codex already has reasoning-effort controls, model catalogs, plan-mode defaults,
sub-agent overrides, and memory subsystems with fixed effort choices. It also already has phase-specific memory and
consolidation, so the relevant distinction is **not** "Codex has no memory." mew's differentiator, if M6.13 later
lands, is a **blocker-aware, replayable, durable coding-intelligence loop**: typed blocker taxonomy, replay bundles,
and explicit internalization of reusable outcomes across sessions.

The structural difference is therefore:

- **reasoning engine with local effort and memory controls**:
  delegate hard task -> receive answer now -> optional session-local memory/consolidation
- **blocker-aware durable loop**:
  hit typed blocker -> decide whether escalation belongs -> run bounded replayable attempt -> classify the outcome ->
  internalize reusable abstraction -> recall it in later sessions

M6.11's local contracts also matter. exact cached windows, typed blocker codes, paired source/test discipline,
deterministic patch validation, and durable resume state are not replaced by "call a harder model"; they are what make
a future deliberation lane safe. That claim is orthogonal to codex-cli's own memory/consolidation features: those help
Codex operate within its product surface, while mew's prospective value is blocker-linked reuse that survives replay,
resume, and cross-session internalization. M6.13 should therefore be judged less by "did it call a powerful model?"
and more by "did the result become durable coding intelligence inside mew?"

## 13. Adaptation philosophy

This section intentionally mirrors the three-class scheme used in `docs/REVIEW_2026-04-22_M6_9_EXPECTED_VALUES.md`.
Published findings and vendor docs operate on different surfaces from any future mew telemetry, so M6.13 should use the
same three adaptation classes:

1. **Direct**:
   source maps almost one-to-one to a mew surface, such as a vendor-supported effort list or a source-code default.
2. **Translated**:
   source is quantitative but must be reshaped for mew, such as benchmark gains turned into reviewer-accepted
   abstract-task improvements.
3. **Directional**:
   source establishes direction or tradeoff but not a mew-ready magnitude, such as refusal behavior, schema fragility,
   or budget efficiency under harder reasoning.

Decision rubric:

- API or source-code behavior with a near-identical mew analog -> **Direct**.
- Benchmark result requiring surface translation -> **Translated**.
- qualitative or weakly transferable tendency -> **Directional**.

When in doubt, widen the class. This matters especially for effort comparisons because `high` in one provider is not
equivalent to `high` in another, adaptive-thinking systems may spend different actual compute at the same nominal
setting, and pro-model variants can package extra compute without exposing a wider menu. A future M6.13 metrics doc
should therefore treat vendor effort categories, actual reasoning-token usage, wall-clock latency, final-answer quality,
and schema adherence as related but **non-equivalent** variables.
Numeric tolerance windows of the kind used in `M6.9 EXPECTED_VALUES` are deferred to a future M6.13 metrics document;
this reference classifies adaptation distance only.

## 14. Amendment policy

This is a reference document. It should evolve by dated in-place amendment, not by formal proposal every time a vendor page or source tree changes.

Rules:

1. **Revise in place** with a dated amendment note under the affected subsection when a source changes materially.
2. **Source refreshes are expected**. Vendor docs, model menus, and reference codebases are moving targets.
3. **Do not silently delete superseded claims**. Mark them as amended and preserve the old statement in the amendment log when practical.
4. **Structural scope changes** such as adding a new provider family, changing the M6.13 problem statement, or converting a hypothesis into a requirement should wait for
   a separate design document.
5. **No close-gate authority** is created by amendment. This document remains reference-only after amendment.

Example amendment shape:

```
Amended 2026-05-12: OpenAI model page updated to show GPT-5.5 exposing
`reasoning.effort: xhigh`. Matrix row updated accordingly. Reason:
official model surface changed after initial draft.
```

## 15. Amendment log

```
2026-04-23: initial document.
2026-04-23: polish pass after three reviewer audits. Anthropic model names re-verified against live docs; Mythos
Preview separated from the Claude 4 family row. arXiv:2502.12521, arXiv:2506.05333, and arXiv:2504.13171 re-checked
against live arXiv abstracts and summary claims tightened. Added missing escalation anti-patterns, top-of-doc author /
reviewer provenance disclosure, open-question falsifiability framing, matrix design-space additions, and the M6.13
adaptation-distance disclaimer. DeepSeek `R2` remains unconfirmed in first-party public docs as of 2026-04-23 and is
marked as such in §10.
(future amendments land here with dated entries)
```

## 16. Related documents

- `docs/REVIEW_2026-04-22_M6_9_EXPECTED_VALUES.md` — formatting and adaptation-rubric anchor for scientific reference docs in mew.
- `docs/REVIEW_2026-04-21_DURABLE_CODING_INTELLIGENCE.md` — authoritative M6.9 design context, especially Phase 2 D1/D3/D4 surfaces that may later benefit from
  deliberation.
- `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md` — authoritative M6.11 blocker taxonomy and recovery vocabulary used here as possible escalation inputs.
- `src/mew/patch_draft.py` — current executable blocker-code map for the drafting lane.
- `docs/REVIEW_2026-04-22_M6_11_TINY_REASONING_LOW_CODEX_REVIEW.md` and `docs/REVIEW_2026-04-22_M6_11_TINY_REASONING_LOW_CLAUDE_FINAL.md` — local empirical context
  showing that narrow write-ready drafting benefited from a smaller effort policy, which is a useful counterpoint to future M6.13 escalation work.
- `references/fresh-cli/codex/` — source basis for Codex effort-routing analysis.
- `references/fresh-cli/claude-code/` — source basis for Claude Code effort-routing analysis.
