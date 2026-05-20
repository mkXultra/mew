# Future 2026-05-20 - M6.25 Resident Memory Campaign

Status: future campaign planning only. This document is intentionally not an
implementation-authorizing design for the current Harbor fixture task.

Scope: preserve the broader resident-memory campaign, reference comparison,
ledger, and M6.25 evidence plan that was split out of the narrower Harbor task
fixture design.

The current implementation design is:

- `docs/DESIGN_2026-05-20_M6_25_HARBOR_RESIDENT_MEMORY_TASK.md`

That design authorizes only Phase 0-1 fixture work. Do not use this future
document to authorize runner, campaign, memory, or reference-agent changes until
a new implementation design is written.

## Decision

Create a small new Harbor multi-step fixture family named
`resident-golden-convention-recall`.

Do not copy an existing Terminal-Bench task. Terminal-Bench tasks are useful as
M6.24 parity checks, but their normal shape is one-shot task completion. Copying
one would either leave resident memory unmeasured or turn a prior M6.24 task
into a confusing M6.25 signal.

Do use Harbor's multi-step task skeleton and conventions as the implementation
starting point: task root `task.toml`, root `environment/`, root shared
`tests/`, and ordered `steps/`. If an upstream or generated Harbor
multi-step skeleton is available, copy only the skeleton structure and metadata
style. The fixture content should be new and tiny.

This creates the smallest benchmark that is:

- Harbor-compatible;
- local-first and deterministic;
- solvable by ordinary coding agents without hidden mew commands;
- able to compare cold, warm/resident, and stale-memory behavior;
- appropriate as M6.25 resident-advantage evidence, not M6.24
  Terminal-Bench parity evidence.

The evidence unit is not a single Harbor trial. It is a Harbor task plus a
conditioned campaign. Harbor supplies ordered steps, shared container execution,
per-step verifiers, and artifacts. The campaign layer controls whether resident
memory is cleared, preserved, or seeded with stale facts.

## Non-Goals

- Do not implement fixtures, source code, verifier scripts, runner changes, or
  campaign code in this design step.
- Do not edit `ROADMAP.md` or `ROADMAP_STATUS.md`.
- Do not use this custom task as M6.24 Terminal-Bench parity evidence.
- Do not require `mew memory`, mew internals, or any mew-only command for
  correctness.
- Do not prove provider-cache transport, prompt tuning, or broad memory
  improvements with this task alone.
- Do not score memory behavior from model self-report.

## Why A New Small Fixture

The existing side-project proposal already names the right shape: seed, recall,
and stale memory. The 2026-05-20 benchmark reviews found no existing
Terminal-Bench task that directly measures resident persistence or cross-session
memory reuse. Harbor multi-step tasks are the right substrate because they can
run ordered steps with per-step instructions, tests, setup hooks, verifier
results, and artifacts against one environment.

A small new fixture is better than adapting a large task because the first
question is benchmark validity, not mew implementation strength. The task must
make memory useful but not mandatory. A cold agent should be able to solve it by
exploration. A warm resident agent should solve the recall step with less
repeated search, faster first edit or verifier use, or fewer repeated mistakes.
A stale-memory condition should fail blind reuse and reward verification against
the current workspace.

## Harbor Task Directory Shape

Target directory, subject to the later implementation location decision:

```text
benchmarks/harbor/resident-golden-convention-recall/
  task.toml
  environment/
    Dockerfile
    fixture-src/
      base-project/
      phase-a-seed/
      phase-b-recall/
      phase-c-stale/
  tests/
    check_common.py
    test.sh
  steps/
    seed-convention/
      instruction.md
      workdir/
        setup.sh
      tests/
        test.sh
        check_seed.py
      solution/
        solve.sh
    recall-convention/
      instruction.md
      workdir/
        setup.sh
      tests/
        test.sh
        check_recall.py
      solution/
        solve.sh
    stale-memory/
      instruction.md
      workdir/
        setup.sh
      tests/
        test.sh
        check_stale.py
      solution/
        solve.sh
```

Use Harbor `schema_version = "1.1"` and declare ordered `[[steps]]` entries.
Use `multi_step_reward_strategy = "mean"` for the Harbor trial-level reward,
but treat per-step rewards and campaign metrics as the authority for M6.25
evidence. Any `min_reward` early-stop behavior is only for full-task sanity
runs; the resident-memory campaign must still produce all required condition
rows, even if that means running steps as explicit slices instead of relying on
one Harbor aggregate run.

Recommended `task.toml` intent:

- `[environment] workdir = "/app"`;
- runtime network disabled or absent from the task environment;
- small CPU/memory limits;
- no runtime `apt`, `pip`, or network setup;
- task-level artifacts include agent trajectory and memory snapshots when the
  runner can provide them;
- step-level artifacts collect the relevant changed source files and any
  published memory/metrics files;
- `min_reward = 1.0` on seed and recall steps during normal full-task sanity
  runs only;
- no accepted M6.25 campaign row may be missing because Harbor early-stopped a
  later step.

Keep the fixture stdlib-first. If `pytest` is used, bake it into the local image
or vendor the dependency. The verifier should never install packages at runtime.

## Fixture Concept

The workspace is a tiny Python package with a project-local convention that is
discoverable by ordinary file inspection:

- implementation lives in a non-obvious but stable source registry;
- expected behavior is validated through golden cases, not through the first
  obvious unit-test file;
- editing generated golden outputs is a tempting but wrong shortcut;
- the correct verifier command is present in local scripts or tests, but not
  spelled out in the task instruction.

The concrete feature names can be arbitrary. The important convention is:

- source rule registry: a stable source file or package area;
- golden verifier path: a stable verifier/golden-case layout for Step A and
  Step B;
- known bad approach: changing expected outputs or visible tests instead of
  source behavior;
- stale change: Step C moves or renames the verifier/golden path while the
  injected memory still points at the old path.

The public task instructions must ask for user-facing behavior, not for memory
behavior. They should not say "use memory", "call mew memory", or reveal the
source/test path.

## Step Sequence

### Step A - Seed

Purpose: create a useful resident memory item through normal exploration.

The agent receives a small feature request. To pass, it must discover the local
convention: the real implementation location, the golden verifier pattern, and
the wrongness of editing expected outputs. The verifier checks the requested
feature and protected-file integrity.

Expected durable fact, expressed by the campaign as a compact memory card after
a passing seed step:

```json
{
  "category": "workflow_and_gotcha",
  "task_family": "resident-golden-convention-recall",
  "fact": "This project's behavior is changed in the source rule registry and verified through golden-case checks; do not fix failures by editing generated expected outputs.",
  "evidence_refs": ["step-a verifier result", "step-a source diff", "step-a command trace"]
}
```

The memory card must not include Step B's answer or feature-specific constants.

Memory card bounds for the first task:

- maximum 600 UTF-8 bytes after whitespace normalization;
- one card per injected step;
- workflow-level fact only;
- no feature constants, expected outputs, hidden test values, or Step B/Step C
  answer fragments;
- no exact source paths or verifier commands in the resident Step B card unless
  a later experiment explicitly changes `memory_surface` to test retrieval of
  concrete paths;
- evidence refs are allowed, but must be artifact ids or hashes, not raw prior
  transcript text.

The stale Step C card is the only exception: it may include one obsolete path or
command because that is the premise-checking target. It must be labeled as the
stale card in metrics, and it must not coexist with the genuine Step A card.

### Step B - Recall

Purpose: measure useful warm memory against a cold baseline.

The workspace is reset to a fresh Step B variant before the agent starts. Step A
source edits are not left in `/app` as a shortcut. The instruction asks for a
similar but non-identical feature in the same family.

Cold behavior:

- no Step A memory card;
- no host resident state from Step A;
- agent can still pass by inspecting the workspace.

Warm/resident behavior:

- same Step B workspace and same instruction;
- Step A memory card is available through the resident memory/reentry surface;
- success should require current workspace work, not blind replay.

Measured advantage can be correctness, but does not have to be. A valid M6.25
signal can be equal correctness plus lower first-edit latency, lower
first-verifier latency, fewer reads/searches, or avoiding the known bad
expected-output edit.

### Step C - Stale

Purpose: distinguish useful resident memory from blind memory obedience.

The workspace is reset to a Step C variant where the general convention still
applies, but one concrete memory detail is obsolete. For example, the old golden
path or verifier command from Step A/B has moved.

The campaign injects a stale memory card such as:

```json
{
  "category": "workflow_and_gotcha",
  "task_family": "resident-golden-convention-recall",
  "fact": "Use the old golden path and old verifier command from the prior project layout.",
  "staleness": "intentional"
}
```

Correct behavior:

- inspect the current workspace before relying on the memory;
- use the current source and verifier locations;
- avoid writing to obsolete paths;
- pass the current verifier;
- produce trace evidence that stale memory was rejected or superseded by a
  current observation.

The stale step should not be scored from prose claims. `stale_memory_rejected`
must be inferred from deterministic verifier checks and normalized trajectory
events.

Mechanical stale predicate:

`stale_memory_rejected = true` only if all of these are true:

- `current_verifier_passed`: Step C verifier reward is `1.0`;
- `current_workspace_observed`: normalized trajectory contains a read, list, or
  search event for the current Step C source or verifier location after reset
  and before the final relevant edit or finish;
- `current_verifier_run_by_agent`: normalized trajectory contains an agent-run
  verifier command that targets the current Step C verifier path or command;
- `obsolete_path_not_written`: filesystem diff contains no writes, moves, or
  deletes under the obsolete path named by the stale card;
- `obsolete_verifier_not_used_as_final_proof`: the final successful verifier
  evidence is not the obsolete command or obsolete path;
- `self_claim_ignored`: no model prose claim is used as an input.

Inputs come from normalized trajectory events, command transcript records,
filesystem diffs, and verifier reward JSON. If any required input is unavailable,
the predicate is `null` or `false`, never inferred as `true`.

## Verifier Shape

Use deterministic local scripts only. No LLM judge and no network.

Each step verifier should:

- run from `/app`;
- call a step-local `/tests/test.sh`;
- execute a small Python checker that imports or invokes the package;
- verify the requested behavior against hidden expected cases in `/tests`;
- verify protected files were not changed when they should not be;
- verify no stale/obsolete path was edited in Step C;
- write `/logs/verifier/reward.json`;
- optionally write `/logs/verifier/resident-memory-metrics.json` with
  verifier-side facts.

Recommended reward keys:

```json
{
  "reward": 1.0,
  "correctness": 1.0,
  "protected_files": 1.0,
  "current_workspace_verified": 1.0,
  "stale_rejection": 1.0
}
```

For Step A and Step B, `stale_rejection` can be omitted or set to `1.0` as not
applicable. Harbor aggregate reward is useful for sanity, but M6.25 reporting
must read the per-step reward JSON and campaign metrics.

The verifier should not require the agent to write memory notes. A later runner
may collect optional memory snapshots, but benchmark correctness must come from
the workspace result and deterministic checks.

## Artifacts

Required per trial:

- Harbor root `result.json`;
- per-step verifier stdout/stderr and reward JSON;
- per-step copied artifacts under Harbor `steps/<step-name>/artifacts/`;
- normalized agent trajectory;
- source diff or final source snapshot;
- command transcript;
- memory snapshot before and after each step when memory mode is not `off`;
- campaign metrics JSON or JSONL row;
- campaign summary markdown for accepted M6.25 evidence.

Required per step metrics row:

```json
{
  "schema_version": "resident-memory-bench-v0",
  "task_family": "resident-golden-convention-recall",
  "step": "recall-convention",
  "condition": "resident",
  "reference_condition": "mew_resident",
  "memory_mode": "on",
  "memory_surface": "prompt_section",
  "memory_card_chars": 0,
  "memory_card_sha256": null,
  "agent_process_fresh": true,
  "conversation_continuation": false,
  "session_resume_id": null,
  "prior_transcript_visible": false,
  "prior_artifacts_visible": false,
  "success": true,
  "reward": 1.0,
  "wall_seconds": 0,
  "first_edit_latency_seconds": null,
  "first_verifier_latency_seconds": null,
  "read_count": 0,
  "search_count": 0,
  "tool_count": 0,
  "verifier_count": 0,
  "repeated_failure_count": 0,
  "memory_items_returned": 0,
  "memory_items_injected": 0,
  "memory_items_claimed_used": 0,
  "memory_evidence_refs": [],
  "stale_memory_rejected": null,
  "reviewer_rescue_required": false,
  "prompt_chars": null,
  "model_elapsed_seconds": null
}
```

The runner may fill unavailable fields as `null`, but it must not invent
positive evidence. The campaign summary should keep quality, resident
advantage, and cost/latency separate, matching the M6.25 plan.

## Campaign Requirements

The campaign layer is responsible for cold/warm/stale conditions. The Harbor
task alone cannot prove resident advantage.

Minimum campaign matrix:

| condition | Step A memory | Step B memory | Step C memory |
|---|---|---|---|
| cold | off/reset | off/reset | off/reset |
| resident | on/capture | on/reuse A seed | on/current plus A seed |
| stale | off or capture | off or suppressed | stale card only |

The campaign runner must execute Step A, Step B, and Step C for every condition
or explicitly run equivalent step slices that produce all nine condition/step
rows. Cold Step C is required as a memory-disabled baseline. Stale Step C
suppresses the genuine Step A card and exposes only the stale card, so the row
isolates current-workspace verification against misleading memory.

`min_reward` may be useful for fixture sanity checks, but it must not remove
campaign rows. If Harbor early-stop would skip a later step, the campaign runner
must override that behavior or run the later step as an independent slice with
the same reset contract and condition metadata.

## Trial Topology And Agent Isolation

Each condition/step measurement is an independent campaign slice with explicit
identity:

```text
trial_id = resident-golden-convention-recall/<reference_condition>/<condition>/<attempt>/<step>
```

For M6.25 evidence, Step B and Step C condition slices start from a fresh agent
process and fresh model conversation. They must not inherit prior chat history,
in-process Python object state, cached agent fields, previous `/logs` files, or
prior Harbor artifact directories. Same-process Harbor multi-step continuation
may be used for local task wiring smoke only; it is not accepted as
cold-vs-resident evidence.

The only Step A-derived input allowed in resident or stale evidence rows is the
bounded memory card or stale card recorded in the metrics row. Prior source
diffs, prior transcripts, prior `/logs/agent`, prior `/logs/verifier`, and prior
artifact directories must be hidden from the agent or mounted read-inaccessible.

Cold slices use `memory_mode = "off"`, `memory_surface = "none"`, no memory
card, and a fresh agent process/conversation for every step. Resident Step B
uses a fresh agent process/conversation plus the approved Step A memory card.
Stale Step C uses a fresh agent process/conversation plus only the stale card.

If Harbor invokes a long-lived custom-agent object across steps, the wrapper
must clear any in-memory fields before starting the next evidence slice. The
metrics row records `agent_process_fresh = true` only when this isolation is
actually enforced.

## Per-Step Reset Contract

Every step begins from a known fixture variant. Step setup must:

- restore the relevant fixture into `/app` from a read-only fixture source;
- remove prior step source edits, generated caches, temporary outputs, and
  writable test/golden mutations from `/app`;
- clear or rotate `/logs/agent`, `/logs/verifier`, and `/logs/artifacts` before
  the next agent-visible instruction;
- preserve only host-side campaign memory surfaces explicitly selected by
  condition;
- write a reset manifest before the agent receives the instruction.

Required reset manifest fields:

```json
{
  "schema_version": "resident-reset-v0",
  "task_family": "resident-golden-convention-recall",
  "reference_condition": "mew_resident",
  "condition": "resident",
  "attempt": 1,
  "step": "recall-convention",
  "fixture_variant": "phase-b-recall",
  "app_baseline_sha256": "sha256:...",
  "removed_prior_paths": [],
  "preserved_surfaces": ["prompt_section:resident-memory-card-v0"],
  "prior_logs_visible_to_agent": false
}
```

The verifier or campaign summary must check the reset manifest before accepting
a row. A missing reset manifest, mismatched fixture hash, visible prior logs, or
unexpected preserved path invalidates that row as resident-memory evidence.

## Memory Surface Contract

The first task's default resident memory surface is a single bounded prompt
section named `resident-memory-card-v0`, injected before the agent's first model
turn for the step. It is not part of the user-facing task instruction.

Allowed `memory_surface` values:

- `none`: no memory card and no host resident memory;
- `prompt_section`: the default V0 surface;
- `read_only_file`: future variant, where the card is placed in a declared
  read-only file path and the path is recorded in metrics;
- `retrieval_tool`: future variant, where a read-only retrieval tool returns
  the bounded card.

Do not combine surfaces in the first benchmark. A row has exactly one
`memory_surface` value. Full prior transcripts, prior source diffs, and
unbounded summaries are forbidden surfaces.

Metrics must record:

- `memory_surface`;
- `memory_mode`;
- `memory_card_chars`;
- `memory_card_sha256`;
- `memory_items_injected`;
- `memory_items_returned`;
- `prior_artifacts_visible`;
- `memory_evidence_refs`.

For the stale condition, Step C exposes only the stale card. The genuine Step A
resident card is suppressed even if it exists in the campaign store.

For the first accepted baseline:

- run at least one oracle sanity pass for every step;
- run at least three paired cold/resident/stale attempts before tuning;
- raise to five paired attempts per condition before using the result as
  reportable M6.25 product evidence;
- record every attempt in `proof-artifacts/m6_25_resident_advantage_ledger.jsonl`
  or a campaign-specific JSONL linked from that ledger;
- keep provider cache transport default-off unless the specific experiment is
  cache transport;
- record cache state, prompt-section hashes, model, timeout, and runner version.

The Step B comparison must use the same workspace variant and instruction for
cold and resident runs. The only intended difference is memory/reentry state.

The Step C stale comparison must make the stale memory plausible. It should be
wrong in a way that a careless resident agent could follow, but easy to reject
by inspecting current files.

## Reference Agent Comparison Protocol

Codex comparisons are useful baselines, but they are not the same evidence type
as mew resident memory. The campaign report must distinguish bounded resident
memory from conversation continuation.

Reference condition definitions:

- `codex_cold`: each step is a fresh Codex run and fresh model conversation. It
  receives the step prompt only, no prior transcript, no session resume, no
  memory card, and `memory_surface = "none"`. This is the closest Codex
  reference for cold one-shot task ability.
- `codex_resume`: Step A starts a Codex session. Step B and Step C use Codex
  resume/session continuation with the next step prompts. This is a
  conversation-continuation baseline, not resident-memory evidence, because it
  carries prior chat, reasoning, tool observations, and possible mistakes rather
  than only a bounded memory card.
- `mew_resident`: each evidence slice starts a fresh model conversation and no
  prior transcript is visible. The only prior Step A-derived input is the
  bounded memory card or stale card recorded in the metrics row. This is the
  resident-memory evidence condition.

`codex_resume` must be reported separately from cold/warm/stale resident
evidence. It may answer a useful product question, "How much does ordinary
conversation continuation help?", but it must not be merged into the
resident-memory delta because its information channel is much wider than
`resident-memory-card-v0`.

Reference metrics:

- `reference_condition`: one of `mew_resident`, `codex_cold`, or
  `codex_resume`;
- `conversation_continuation`: `true` only when the model sees prior chat or a
  resumed provider/CLI session;
- `session_resume_id`: null for fresh runs, otherwise the Codex session id or
  resume handle used for that step;
- `prior_transcript_visible`: whether prior conversation text or tool output is
  visible to the model;
- `memory_surface`: still records the resident memory surface. For
  `codex_resume`, keep `memory_surface = "none"` unless a later experiment
  deliberately adds an explicit memory card; the continuation itself is tracked
  by `conversation_continuation`, not by pretending it is a bounded resident
  memory surface.

Runner implications:

- The current `src/mew/reference_trace_runner.py` can run one-shot reference
  traces with `harbor run --agent codex` and normalize the resulting Harbor
  logs. It is a reusable invocation/normalization primitive, not a complete
  resident-campaign runner. `codex_cold` rows for this custom task still need a
  reference campaign wrapper or runner extension that can target the custom
  fixture/step slice, force a fresh Codex run, set
  `reference_condition = "codex_cold"`, choose a per-condition/attempt/step
  `jobs_dir`, and write the required campaign row plus artifact index.
- A future reference campaign runner is needed for `codex_resume`. It must
  start Step A, capture the Codex session id or resume handle, pass that handle
  into Step B and Step C with the next step prompts, and record the prompt ids,
  session ids, resume handles, model, reasoning effort, and auth/runtime config
  in the campaign row.
- Reference artifacts must be namespaced by `reference_condition` as well as
  condition, attempt, and step. `codex_cold` and `codex_resume` artifacts must
  never overwrite or share artifact roots with `mew_resident` evidence rows.
- The reference runner must record whether prior transcript was visible and
  whether conversation continuation was used. Missing session/resume metadata
  invalidates a `codex_resume` row as a resume baseline.

Codex references are comparison baselines. They are not required to establish
the first utility of the benchmark task itself, and they are not M6.24
Terminal-Bench parity evidence.

## Runner Requirements

Current mew Harbor support is proven for one instruction-consuming task run.
Before this benchmark can be used as M6.25 evidence, the runner must be checked
or extended for multi-step identity.

Required runner behavior:

- preserve Harbor step name in artifact paths and summaries;
- avoid overwriting the current `unknown-task` artifact directory across steps;
- expose memory mode in the command/report artifacts;
- clear resident memory for cold steps;
- import or preserve Step A memory for resident Step B;
- inject stale memory for Step C without editing the task prompt;
- enforce fresh agent process/conversation semantics for evidence slices;
- emit reset manifests and reject rows with visible prior logs;
- for reference campaigns, record `reference_condition`,
  `conversation_continuation`, `session_resume_id`,
  `prior_transcript_visible`, and `memory_surface`;
- keep task environment network-independent;
- collect normalized trace events for reads, searches, edits, verifier runs,
  and first-edit/first-verifier latency;
- summarize per-step Harbor rewards, not only root aggregate reward;
- record whether observer detail and provider request inventory are present
  when available.

If the checked-in runner cannot receive step metadata from Harbor, implement the
first campaign as a thin wrapper around the same fixture variants with explicit
step ids. The fixture should still follow Harbor multi-step layout so it can
move back to native multi-step execution once step-aware artifacts are stable.

## Artifact Namespace Contract

Every evidence row must have a unique host-visible namespace. Preferred shape:

```text
<jobs_dir>/
  resident-golden-convention-recall/
    reference_condition=<reference-condition>/
      condition=<condition>/
        attempt=<attempt>/
          step=<step-id>/
            agent/
              instruction.json
              command-transcript.json
              mew-report.json
              trajectory.json
            verifier/
              reward.json
              resident-memory-metrics.json
            metrics/
              campaign-row.json
              reset-manifest.json
            artifacts/
              source-diff.patch
              memory-before.json
              memory-after.json
```

If Harbor writes a different native layout, the runner must write a
result-adjacent index file, for example `resident-step-index.json`, that maps
each condition/attempt/step to its actual paths.

Required index fields per row:

```json
{
  "task_family": "resident-golden-convention-recall",
  "condition": "resident",
  "reference_condition": "mew_resident",
  "attempt": 1,
  "step": "recall-convention",
  "trial_id": "resident-golden-convention-recall/mew_resident/resident/1/recall-convention",
  "memory_mode": "on",
  "memory_surface": "prompt_section",
  "conversation_continuation": false,
  "session_resume_id": null,
  "prior_transcript_visible": false,
  "artifact_root": "...",
  "reward_json_path": "...",
  "campaign_row_path": "...",
  "reset_manifest_path": "...",
  "trajectory_path": "..."
}
```

Acceptance check: before a row can enter the M6.25 ledger, the campaign summary
must prove that all required per-step reward JSON files and campaign rows are
host-visible, have unique `trial_id` values, and point to distinguishable
artifact roots. This check should be mechanical, not manual inspection.

## M6.25 Evidence Boundary

This benchmark is not M6.24 parity evidence.

Use it for M6.25 only when the report explicitly answers:

- quality: did the task pass under each condition;
- resident advantage: what persisted or was reused;
- cost/latency: what repeated work was reduced;
- stale safety: whether obsolete memory was rejected with current evidence.

Do not compare its raw reward to Terminal-Bench 2.0 leaderboard rows. Do not use
it to reopen M6.24 proof collection. Codex CLI can be run as an optional cold
or resume reference, but a Codex result is not required to establish the
benchmark's first M6.25 utility. `codex_resume` is specifically a
conversation-continuation baseline, not resident-memory evidence.

## Anti-Cheat And Anti-Overfitting

- Task prompts must not reveal exact source paths, verifier commands, or memory
  cards.
- The task family name can be descriptive, but the in-container instruction
  should be ordinary product behavior.
- Hidden verifier logic lives in `/tests`, not in writable workspace files.
- Protected expected-output files and visible tests should have checksums or be
  validated from the hidden verifier.
- Do not reward self-reported memory use.
- Infer stale rejection from trace and filesystem facts: current-path reads,
  current verifier execution, no obsolete-path writes, and passing current
  checks.
- The Step A memory card should contain workflow knowledge, not feature-specific
  expected outputs.
- Stale memory should be plausible, not absurd, so the task measures premise
  checking instead of ignoring irrelevant text.
- Keep network disabled in the task environment and do not mount benchmark docs
  into an agent-readable task workspace.
- If the agent can read the mew checkout for installation, the work-session
  read gate must still prevent it from reading this design or benchmark source
  as task evidence.
- Rotate feature names or constants after initial calibration if repeated local
  runs start to overfit.

## Risks

- Shared Harbor environment can leak Step A solution files into Step B. The
  design requires per-step workspace reset to prevent that shortcut.
- A memory card that is too explicit will measure prompt injection, not resident
  memory. Keep it compact and generic.
- A memory card that is too vague may not produce measurable differences. Tune
  only after cold/resident baseline rows exist.
- Step B may be too similar to Step A and become a duplicate-task shortcut, or
  too different and make memory irrelevant.
- Stale-memory success can be gamed if it is based on prose claims. It must be
  artifact and trajectory based.
- Current mew Harbor artifacts are one-task oriented. Multi-step artifact
  namespacing is a known runner review focus.
- Provider cache, prompt changes, or model changes can masquerade as memory
  advantage. Record them and keep cache default-off.
- A single pass is not enough evidence because model behavior is stochastic.
  Use paired attempts and keep failures.

## Implementation Phases

Phase 0 - Skeleton and spec check:

- choose final fixture directory;
- create Harbor multi-step skeleton only;
- confirm `task.toml` validates locally;
- no mew runner changes yet.

Phase 1 - Deterministic fixture and oracle:

- add the tiny Python package variants;
- add step verifiers and oracle solutions;
- prove pass/fail determinism with oracle and a deliberately bad solution.

Phase 2 - Step-aware artifact runner:

- verify Harbor passes step identity to the custom agent or add a wrapper
  workaround;
- enforce fresh agent process/conversation isolation for evidence slices;
- emit and validate reset manifests;
- record per-step reports without overwrites;
- emit the campaign metrics schema and artifact index.

Phase 3 - Cold/resident/stale campaign:

- run all nine condition/step rows or equivalent slices;
- run cold Step B and cold Step C baselines with memory disabled;
- run resident Step B with the bounded Step A memory seed;
- run stale Step C with only the obsolete memory card;
- optionally run `codex_cold` reference rows with the existing one-shot
  reference runner;
- run `codex_resume` only after a future reference campaign runner can preserve
  and report Codex session resume handles;
- record all rows in the M6.25 ledger.

Phase 4 - M6.25 evidence report:

- summarize quality, resident advantage, cost/latency, and stale rejection;
- decide whether the task is sharp enough before changing mew memory behavior;
- keep M6.24 baseline untouched.

## Close Gate

The benchmark task family is ready to use for M6.25 evidence only when:

- Harbor task validation passes;
- oracle passes all three steps;
- a known bad solution fails for the expected reason;
- task runtime and verifier need no network access;
- each accepted row has a fresh-agent isolation record;
- each accepted row has a valid reset manifest proving no prior step workspace
  or log leakage;
- memory surface, memory card hash, and prior-artifact visibility are recorded;
- reference condition, conversation-continuation state, session resume id, and
  prior-transcript visibility are recorded for comparison rows;
- per-step artifacts are namespaced and host-visible;
- per-step rewards and campaign rows are mechanically indexed by unique
  `trial_id`;
- cold/resident/stale campaign rows exist with the same schema;
- cold Step C exists as a memory-disabled baseline;
- Step B resident is compared against an equivalent cold Step B workspace and
  instruction;
- Step C stale condition passes only when the mechanical
  `stale_memory_rejected` predicate is true;
- no success condition depends on calling `mew memory` or any mew-only command;
- Codex reference rows, when present, are reported separately from
  cold/warm/stale resident-memory evidence;
- the report explicitly says this is M6.25 resident-advantage evidence and not
  M6.24 Terminal-Bench parity evidence.

The stronger M6.25 product signal requires one more condition: resident mode
must improve at least one of success, first-edit latency, first-verifier
latency, repeated-failure count, read/search count, or reviewer-rescue rate
without regressing stale-memory rejection.

## References

- `ROADMAP.md`
- `ROADMAP_STATUS.md`
- `docs/M6_25_RESIDENT_ADVANTAGE_PLAN_2026-05-20.md`
- `docs/SIDE_PROJECT_HARBOR_RESIDENT_MEMORY_BENCH.md`
- `docs/REVIEW_2026-05-20_TERMINAL_BENCH_RESIDENT_TASK_SEARCH.md`
- `docs/REVIEW_2026-05-20_RESIDENT_AGENT_BENCHMARK_FRAMEWORKS.md`
- `docs/terminal-bench-harbor-smoke.md`
- Harbor task structure: https://www.harborframework.com/docs/tasks
- Harbor multi-step tasks: https://www.harborframework.com/docs/tasks/multi-step
