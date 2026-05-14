# Design 2026-05-15 - M6.24 Hot-Path Observability

Status: implemented for H0 step-diff and H1/H7 provider-visible salience
snapshots.

Scope: sidecar-only measurement for comparing Codex, Claude Code, and mew
hot-path step shapes before any live behavior change. This document defines
artifact inputs, normalized step contracts, report outputs, diagnostics, close
gates, and a later implementation plan. It does not authorize runtime code,
prompt, provider request, tool schema, or live-loop policy changes.

## Problem

M6.24 needs to understand why mew `codex_hot_path` can expose a Codex-like
visible tool list and descriptions but still over-probe and delay source
mutation. The current evidence says tool naming and apply-patch transport are
not enough to explain the gap: the model often spends too many steps gathering
or rechecking facts before crossing into an edit.

The next decision must be measurement-led. If measurement and behavior changes
are mixed, the first patch can accidentally become another live steering
mechanism: a threshold, readiness hint, forced next action, task-specific guard,
or prompt change that makes one run look better while obscuring the real
divergence. That would weaken the main M6.24 objective, which is a Codex-like
native tool loop with mew's proof sidecars, not a hidden controller that pushes
the model through a benchmark.

This design therefore separates observability from behavior. The analyzer is a
sidecar reader over saved artifacts. It reports step shape differences and
diagnostic opportunities. It must not feed decisions back into a live loop.

## Measurement Inputs

The analyzer compares up to three agent families for the same task or task
class. Each input is an artifact root, not a live invocation.

### Codex Reference Trace

Required when comparing against Codex:

- normalized trace events, preferably `normalized-trace/agent_trace.jsonl` or
  `normalized-trace/agent_trace.json`;
- normalized summary, preferably `normalized-trace/summary.json`;
- optional raw agent transcript or CLI artifacts if normalized trace files are
  missing and an offline normalizer exists.

The reader must accept a root that is either the task directory itself or an
ancestor containing a single matching normalized trace. If multiple matching
traces are found, the analyzer must either require an explicit selector or emit
an ambiguous-input error. It must not silently pick an arbitrary trial in
batch-use mode.

### Claude Code Reference Trace

Required when comparing against Claude Code:

- normalized trace events when available;
- raw trajectory artifacts such as `agent/trajectory.json`, `result.json`, and
  task summary files when a normalized trace is absent;
- subagent call and result entries if represented in the raw trajectory.

Claude Code subagent activity must be normalized as ordinary observed steps
with `agent_context` set to `main` or `subagent`. A blocking read-only subagent
is not a mutation and must not be treated as equivalent to a patch opportunity.

### mew Native And Proof Artifacts

Accepted mew inputs:

- native transcript: `response_transcript.json`;
- response item stream: `response_items.jsonl`;
- call/result pairing report: `call_result_pairing.json`;
- transcript metrics: `transcript_metrics.json`;
- provider request inventory or request log: `native-provider-requests.json`
  and any inventory sidecar derived from it;
- proof manifest and typed evidence refs when present;
- normalized mew trace or `mew-report.json` as fallback;
- command transcript or tool route sidecars when present.

mew-specific sidecars are measurement sources only. The analyzer may read them
to compute prompt/input size, pairing validity, tool result refs, and mutation
evidence, but it must not infer a live next action from them.

For H1/H7 provider-visible shape questions, the analyzer may also read the
saved request body from `native-provider-requests.json` and inventory fields
from `provider-request-inventory.json` to report first input shape, top-level
section order, compact-sidecar visibility, and resident scaffolding term
counts. This is still sidecar-only measurement and must not rewrite the live
request.

## Output Contract

The analyzer produces both JSON and Markdown from the same in-memory report.
The JSON is the durable machine contract. The Markdown is a human review view
that must not contain extra findings absent from JSON.

### JSON Report Schema

Top-level shape:

```json
{
  "schema_version": 1,
  "report_kind": "m6_24_hot_path_observability",
  "sidecar_only": true,
  "generated_at": "2026-05-15T00:00:00Z",
  "inputs": {
    "codex": {"root": "...", "sources": {}, "status": "loaded"},
    "claude_code": {"root": "...", "sources": {}, "status": "missing"},
    "mew": {"root": "...", "sources": {}, "status": "loaded"}
  },
  "comparison_policy": {
    "primary_reference_agent": "codex",
    "candidate_agent": "mew",
    "selection_reason": "default_codex_reference",
    "explicit_selection": false
  },
  "agents": {
    "codex": {"steps": [], "metrics": {}, "artifact_warnings": []},
    "claude_code": {"steps": [], "metrics": {}, "artifact_warnings": []},
    "mew": {"steps": [], "metrics": {}, "artifact_warnings": []}
  },
  "pairwise_comparisons": [],
  "divergence_summary": [],
  "possible_first_patch_opportunity_diagnostics": [],
  "warnings": [],
  "close_gate_inputs": {
    "no_live_tasks_run": true,
    "existing_artifacts_only": true,
    "provider_visible_behavior_changed": false
  }
}
```

Required rules:

- `schema_version` is an integer and increments on incompatible field changes.
- `sidecar_only` must always be `true`; if the analyzer cannot prove it used
  only saved artifacts, it must fail before writing a success report.
- `inputs.<agent>.status` is one of `loaded`, `missing`, `partial`, `ambiguous`,
  or `unreadable`.
- `inputs.<agent>.sources` maps logical source names to resolved paths.
- `comparison_policy` records the deterministic reference/candidate selection
  used for divergence and diagnostic entries.
- `agents.<agent>.steps` is a list of normalized steps using the schema below.
- `agents.<agent>.metrics` must exist even for partial inputs; unavailable
  numeric metrics are `null`, not omitted.
- `warnings` are non-fatal report-level issues. Fatal issues return a non-zero
  CLI exit and should not be formatted as a successful comparison.

### Provider-Visible Salience Report

H1/H7 use a narrower report kind:

```json
{
  "schema_version": 1,
  "report_kind": "m6_24_provider_visible_salience",
  "sidecar_only": true,
  "provider_visible_behavior_changed": false,
  "inputs": {
    "mew_artifact_root": "...",
    "native_provider_requests": ".../native-provider-requests.json",
    "provider_request_inventory": ".../provider-request-inventory.json"
  },
  "request_count": 50,
  "aggregate": {
    "json_envelope_request_count": 50,
    "compact_sidecar_visible_request_count": 50,
    "max_first_input_text_chars": 9120,
    "max_compact_sidecar_chars": 5981,
    "scaffolding_occurrences_total": 2474
  },
  "first_request": {
    "leading_shape": "json_envelope",
    "top_level_section_order": [
      "compact_sidecar_digest",
      "lane",
      "task_contract",
      "task_facts",
      "workspace"
    ]
  },
  "turns": [],
  "interpretation": []
}
```

The CLI is:

```bash
uv run python scripts/analyze_provider_visible_salience.py \
  --mew-artifact-root <mew-artifact-root> \
  --out-json tmp/provider-visible-salience.json \
  --out-md tmp/provider-visible-salience.md
```

Use this report to choose H1 versus H7. It does not authorize combining both
changes in one behavior experiment.

## Reference And Candidate Selection

Default selection must be deterministic:

- If Codex is loaded, Codex is the primary reference.
- If Codex is missing and Claude Code is loaded, Claude Code is the primary
  reference.
- mew is never auto-selected as the primary reference.
- If mew is loaded, mew is the default candidate.
- If mew is missing, the caller must provide an explicit candidate selector;
  otherwise the report is not comparable.
- Non-default reference or candidate choices require explicit selectors and
  must set `comparison_policy.explicit_selection=true`.
- When Codex, Claude Code, and mew are all loaded, the default durable pairwise
  comparisons are Codex to mew and Claude Code to mew. The primary divergence
  and first-patch diagnostics use Codex to mew unless explicit selectors say
  otherwise.

The analyzer may compare Codex to Claude Code only when explicitly requested or
when no mew candidate is provided and the caller has selected one reference and
one candidate. The report must record the chosen orientation because deltas are
always candidate minus reference.

### Markdown Report Schema

Markdown must be deterministic and reviewable. Required sections:

1. `# M6.24 Hot-Path Observability`
2. `## Inputs`
3. `## Metric Summary`
4. `## Pairwise Comparisons`
5. `## Divergence Summary`
6. `## First-Patch Opportunity Diagnostics`
7. `## Repeated Probe Families`
8. `## Tool/Result Pairing`
9. `## Prompt And Input Size`
10. `## Normalized Steps`
11. `## Warnings`

The metric summary table must include one column per loaded agent and one row
per required metric. Missing metrics render as `n/a`. Diagnostic sections must
state that they are sidecar-only and not live-loop policy.

The pairwise comparisons section must render one row per comparison id with
reference agent, candidate agent, comparability, first mutation delta, probe
count delta, repeated-family delta count, pairing warning count, and warning
summary. Detailed metric objects remain in JSON.

## Normalized Step Schema

Every observed model/tool action that can affect hot-path shape is normalized to
one row:

```json
{
  "schema_version": 1,
  "agent": "codex",
  "agent_context": "main",
  "step_index": 12,
  "turn_index": 8,
  "source_event_id": "call_abc",
  "source_path": "normalized-trace/agent_trace.jsonl",
  "source_line": 42,
  "elapsed_ms": 367803,
  "duration_ms": 1200,
  "phase": "completed",
  "tool_name": "apply_patch",
  "tool_family": "mutation",
  "intent": "mutation",
  "is_probe": false,
  "is_mutation": true,
  "is_verifier": false,
  "is_finish": false,
  "call_id": "call_abc",
  "paired_result_id": "result_abc",
  "pairing_status": "paired",
  "status": "completed",
  "exit_code": 0,
  "target_paths": ["src/example.py"],
  "command": null,
  "summary": "applied patch to src/example.py",
  "input_chars": null,
  "output_chars": 512,
  "original_token_count": null,
  "truncation": {"truncated": false, "reason": null}
}
```

Field rules:

- `agent` is `codex`, `claude_code`, or `mew`.
- `agent_context` is `main`, `subagent`, `tool_runtime`, or `unknown`.
- `tool_runtime` means a tool-execution machinery event observed outside the
  model-selected tool-call stream, such as process lifecycle bookkeeping,
  artifact materialization, or a sidecar write record. Required hot-path metrics
  must exclude standalone `tool_runtime` rows unless the event can be folded
  into the underlying model/tool step through a shared call id or unambiguous
  source event id.
- `step_index` is zero-based after sorting by observed chronology.
- `turn_index` is the provider/model turn when available; otherwise `null`.
- `elapsed_ms` is milliseconds since task start when available; otherwise
  `null`.
- `phase` is `started`, `completed`, `failed`, `running`, or `observed`.
- `tool_name` is the provider or normalized tool name.
- `tool_family` is a coarse grouping used for repeated-probe metrics.
- `intent` must be one of the taxonomy values below.
- `is_probe`, `is_mutation`, `is_verifier`, and `is_finish` are derived from
  `intent`, tool name, and arguments.
- `pairing_status` is `paired`, `missing_result`, `missing_call`,
  `not_applicable`, or `unknown`.
- `target_paths` is an array of paths the step directly reads, writes, or
  verifies when statically visible. It may be empty.
- `summary` is a bounded one-line description derived from the artifact. It
  must not include large raw command output.
- `input_chars`, `output_chars`, `original_token_count`, and `truncation` are
  best-effort measurements from saved provider/tool artifacts.

## Intent Taxonomy

The taxonomy is intentionally generic. It must not contain task names, benchmark
names, domain-specific files, or commands.

Required categories:

- `source_scan`: file listing, text search, globbing, directory inspection, or
  metadata search over source/workspace files.
- `source_read`: reading source, config, documentation, generated artifacts, or
  other workspace files for content.
- `binary_probe`: inspecting compiled artifacts, file formats, symbols,
  sections, metadata, or byte-level properties.
- `disassembly_probe`: disassembly, opcode census, instruction scan, or similar
  low-level executable inspection.
- `dependency_probe`: checking installed tools, packages, runtime versions,
  environment variables, or dependency availability.
- `build_attempt`: invoking a compiler, package build, generated build script,
  or equivalent build step.
- `runtime_verifier`: running tests, executing the target command, replaying a
  verifier, checking produced outputs, or validating acceptance criteria.
- `mutation`: applying a patch, writing a file, editing a file, moving/copying
  files as part of a source change, or running a narrow mutation bridge that
  produces typed mutation evidence.
- `process_poll`: polling, reading, continuing, or canceling a previously
  started process.
- `delegated_explore`: a read-only delegated agent or subagent exploration
  step.
- `finish`: final answer, completion call, finish tool, or resolver completion.
- `other_probe`: observed tool use that gathers information but does not fit a
  narrower category.
- `unknown`: insufficient data to classify.

Classification must be conservative. If a step both probes and mutates, classify
it as `mutation` and set a secondary note in `summary`. If a shell command
contains a write-like command but no mutation evidence is available, classify it
as `other_probe` or `build_attempt` unless the artifact proves a workspace
change.

## Tool-Family Taxonomy

`tool_family` is a deterministic, agent-independent bucket used for repeated
probe metrics. It is not a raw tool name and must not include task paths,
benchmark names, command arguments, or provider-specific labels.

Allowed `tool_family` values:

- `source_listing`: listing, globbing, directory inspection, or file metadata
  enumeration.
- `text_search`: source or workspace text search.
- `file_read`: direct file-content read.
- `binary_metadata`: compiled-artifact format, section, segment, or byte-level
  metadata inspection.
- `symbol_lookup`: symbol table, exported name, address, or map lookup.
- `disassembly`: instruction disassembly or opcode scan.
- `dependency_check`: installed tool, package, runtime, path, or environment
  availability check.
- `build`: compiler, build-system, package-build, or generated build step.
- `runtime_verifier`: test, target command, replay, acceptance check, or output
  validation run.
- `mutation`: patch, edit, write, move, copy, or proven mutation bridge.
- `process_poll`: process continuation, output read, stdin write, cancel, or
  poll.
- `delegated_explore`: read-only delegated exploration.
- `finish`: final answer, finish call, or completion resolver event.
- `other_probe`: information-gathering step not covered above.
- `unknown`: insufficient data to classify.

Derivation rules:

- First classify `intent`, then derive `tool_family` from the most specific
  generic operation visible in the tool name, command, arguments, or sidecar
  evidence.
- Use `text_search` for agent-specific search tools and shell search commands;
  do not emit separate families for individual binaries.
- Use `file_read` for read tools and shell commands whose dominant operation is
  reading bounded file content.
- Use `mutation` only when mutation evidence exists under the rules in the
  metrics section.
- Use `runtime_verifier` for execution intended to validate acceptance or
  produced outputs; use `build` for execution intended to compile or assemble
  artifacts.
- If two implementations would need task knowledge to distinguish a family,
  choose the broader generic family and add detail only in `summary`.

Repeated-probe reporting counts integer occurrences per `tool_family`, not per
raw command string.

## Metrics

Each loaded agent must receive the same metric keys:

- `step_count`: number of normalized steps.
- `first_tool`: object with `step_index`, `turn_index`, `elapsed_ms`,
  `tool_name`, and `intent`.
- `first_mutation`: first step where `is_mutation=true`.
- `first_apply_patch`: first mutation step where `tool_name` is `apply_patch`
  or a provider-native apply-patch equivalent.
- `first_write`: first mutation step that creates, overwrites, edits, moves, or
  copies a workspace file, regardless of tool name.
- `first_verifier`: first step where `is_verifier=true`.
- `probe_count_before_mutation`: count of `is_probe=true` steps before
  `first_mutation`.
- `probe_count_before_write`: count of `is_probe=true` steps before
  `first_write`.
- `repeated_probe_families`: repeated `tool_family` buckets before first
  mutation and across the full trace.
- `mutation_count`: total mutation steps.
- `verifier_count`: total verifier steps.
- `build_attempt_count`: total build attempts.
- `delegated_explore_count`: total read-only delegated exploration steps.
- `process_poll_count`: total process polling or continuation steps.
- `tool_result_pairing`: counts for paired, missing-result, missing-call,
  not-applicable, and unknown pair statuses.
- `prompt_input_size`: provider-visible prompt/input size where available:
  total chars, first-request chars, max-request chars, request count, tool schema
  bytes, visible output bytes, and original token estimates.
- `termination`: final status, timeout flag, final elapsed time, and final
  reported error when available.

Metric objects must preserve both absolute step indexes and elapsed time. If
one trace has no reliable timing, comparisons must still work using step order.

`first_write` requires concrete mutation evidence. Valid evidence is one of:

- a provider-native mutation tool call with a paired successful result;
- typed mutation evidence in a mew proof or tool-result sidecar;
- a normalized trace event marked as a successful edit/write operation;
- a filesystem change list or diff artifact tied to the step;
- a command transcript side effect record that identifies changed workspace
  paths.

Shell commands that merely look write-like do not establish `first_write`
without one of these evidence forms. In that case `first_write` remains `null`.
First-write divergence entries must be emitted only when both compared agents
have comparable non-null `first_write` metrics. If either side is `null`, the
report may emit a warning or a broader no-mutation divergence, but not a
first-write delta.

`repeated_probe_families` has this exact shape:

```json
{
  "before_first_mutation": [
    {
      "family": "text_search",
      "count": 3,
      "step_indexes": [2, 5, 7],
      "first_step_index": 2,
      "last_step_index": 7
    }
  ],
  "full_trace": []
}
```

Rules:

- Include only steps where `is_probe=true`.
- Include a family only when `count >= 2`.
- `before_first_mutation` covers probe steps before the first mutation. If an
  agent has no mutation, it covers all probe steps and the agent metrics must
  set `first_mutation=null`.
- `full_trace` covers all probe steps in the loaded trace.
- Counts are integers and `step_indexes` are sorted in ascending step order.

## Pairwise Comparisons

`pairwise_comparisons` is the durable comparison table. `divergence_summary`
and first-patch diagnostics are derived from these pairwise records plus the
normalized steps.

Required item shape:

```json
{
  "comparison_id": "codex_vs_mew",
  "reference_agent": "codex",
  "candidate_agent": "mew",
  "selection": "default_primary",
  "comparable": true,
  "metrics": {
    "reference": {},
    "candidate": {}
  },
  "metric_deltas": {
    "probe_count_before_mutation": {
      "reference_value": 12,
      "candidate_value": 42,
      "delta": 30,
      "unit": "steps",
      "comparable": true
    }
  },
  "basis": [
    {"agent": "codex", "step_index": 12, "source_event_id": "call_a"},
    {"agent": "mew", "step_index": 42, "source_event_id": "call_b"}
  ],
  "warnings": []
}
```

Rules:

- `comparison_id` is `{reference_agent}_vs_{candidate_agent}` unless explicit
  selectors require a suffix to avoid collision.
- `selection` is `default_primary`, `default_secondary`, or `explicit`.
- `comparable=false` when either side lacks enough step data for metric deltas;
  metrics may still be included with `null` values.
- `metric_deltas` values are always candidate minus reference.
- Each delta object must contain `reference_value`, `candidate_value`, `delta`,
  `unit`, and `comparable`.
- `basis` contains only source refs needed to explain the comparison boundary,
  such as first mutation or first verifier steps.
- `warnings` contains comparison-specific warnings, such as missing prompt-size
  artifacts on one side.

Markdown renders this section as a compact table. It must not replace the JSON
objects or invent extra findings.

## Divergence Summary Format

`divergence_summary` is a list of structured entries, not free text only:

```json
{
  "key": "mew_probe_count_before_mutation_exceeds_codex",
  "severity": "info",
  "agents": ["codex", "mew"],
  "metric": "probe_count_before_mutation",
  "reference_value": 12,
  "candidate_value": 42,
  "delta": 30,
  "summary": "mew made 30 more probe steps than Codex before first mutation.",
  "basis": [
    {"agent": "codex", "step_index": 12, "source_event_id": "call_a"},
    {"agent": "mew", "step_index": 42, "source_event_id": "call_b"}
  ]
}
```

Required divergence entries when applicable:

- earliest tool differs by intent or family;
- candidate has no mutation while a reference mutates;
- candidate first mutation occurs later by step count or elapsed time;
- candidate has more probes before mutation than the selected reference;
- candidate repeats a probe family more often before mutation;
- candidate verifies before any mutation when the reference mutates first;
- candidate delegates exploration before direct main-thread synthesis while the
  reference does not;
- candidate has tool/result pairing gaps;
- candidate has substantially larger first-request or repeated prompt/input
  size where size artifacts are available.

The report must avoid causal claims. It can say "diverged" or "candidate
showed delayed mutation"; it must not say "therefore change the prompt" or
"therefore force a patch."

## Possible First-Patch Opportunity Diagnostics

First-patch opportunity diagnostics are diagnostic-only. They identify places
where a reference had crossed into mutation, or where the candidate repeated
information-gathering after enough generic edit prerequisites were observed.
They are not policies, gates, or live hints.

Required shape:

```json
{
  "kind": "reference_mutated_before_candidate",
  "diagnostic_only": true,
  "agent": "mew",
  "reference_agent": "codex",
  "candidate_step_index": 31,
  "reference_step_index": 14,
  "message": "Reference mutated after fewer probe steps; candidate continued probing.",
  "basis": [
    {"agent": "codex", "step_index": 14, "intent": "mutation"},
    {"agent": "mew", "step_index": 31, "intent": "source_scan"}
  ],
  "not_live_policy": "Do not use this diagnostic to force a next action."
}
```

Allowed generic diagnostic kinds:

- `reference_mutated_before_candidate`;
- `candidate_no_mutation`;
- `probe_budget_gap_before_mutation`;
- `repeated_probe_family_after_reference_mutation`;
- `verifier_before_mutation_gap`;
- `delegated_explore_delayed_mutation`;
- `prompt_size_outlier_before_mutation`;
- `pairing_gap_before_mutation`.

Disallowed diagnostics:

- task-specific file or command rules;
- benchmark-specific thresholds;
- "must patch now" instructions;
- hidden readiness scores sent to the provider;
- mutations or verifier suggestions generated from sidecar analysis.

## Missing Artifact Behavior And Robustness

The analyzer must be useful on imperfect saved runs without pretending missing
data is evidence.

Rules:

- Missing optional artifacts produce `partial` input status and warnings.
- Missing all step sources for a requested agent produces `missing` status.
- Ambiguous multiple task roots produce `ambiguous` status and a fatal CLI
  error unless the caller supplies an explicit selector.
- Malformed JSON/JSONL in a non-essential source produces a warning and records
  the skipped path.
- Malformed primary step data produces `unreadable` status for that agent and a
  fatal error if fewer than two agents remain comparable.
- Timing fields are nullable. Step-order comparisons must still be emitted.
- Pairing metrics degrade to `unknown` when call ids are unavailable.
- Provider input size metrics degrade to `null` when request artifacts are
  absent.
- Tool names must be normalized case-sensitively for display but grouped through
  lower-case family rules for metrics.
- All raw text included in reports must be bounded. Large command output,
  reasoning text, and provider input snapshots are summarized with char counts
  and source refs.
- The analyzer must never execute commands found in artifacts.
- The analyzer must never call a model, Harbor, Terminal-Bench, or a provider.

## Sidecar-Only Invariant

This observability is outside the live control loop.

Hard invariant:

- no live-loop policy changes;
- no model prompt changes;
- no provider-visible input changes;
- no tool schema or tool description changes;
- no tool runtime behavior changes;
- no WorkFrame, next-action, first-write, or readiness signal sent to the
  provider;
- no task-specific benchmark rule;
- no automatic mutation, verification, or rerun based on diagnostics.

Implementation may add or update offline analyzer code and tests only in a
later implementation phase. Any future runtime integration proposal must cite
this report as evidence but must be reviewed under a separate behavior-change
design.

## Use Before Step-Check Or Speed Proof

Before another 10 minute step-check or speed proof, the operator should run this
observability over existing artifacts only:

1. Compare saved Codex, Claude Code, and mew artifacts for the same task or
   closest available task class.
2. Inspect metric summary for first tool, first mutation, first verifier,
   probes before mutation, repeated probe families, pairing gaps, and prompt
   size outliers.
3. Read divergence entries as measurement, not repair instructions.
4. Record hypotheses and experiment choices in the separate hot-path hypothesis
   ledger, not in this design or report.
5. Decide whether a new 10 minute step-check is warranted. If the existing
   artifacts already show a clear missing measurement, implement the missing
   sidecar reader first.
6. Run speed proof only after the relevant behavior-change design has its own
   close gates and the observability report can show whether step shape moved.

This prevents repeated live runs from substituting for analysis and prevents
diagnostics from becoming hidden steering.

## Close Gates And Tests

Design close gate:

- the document defines inputs, normalized steps, taxonomy, metrics, outputs,
  diagnostics, robustness, and sidecar-only invariants;
- it does not require or authorize runtime implementation;
- it contains no task-specific rule for any benchmark.

Future implementation close gates:

- unit tests build synthetic Codex, Claude Code, and mew fixtures with known
  step order, timing, pair ids, prompt sizes, mutation counts, and verifier
  counts;
- synthetic tests cover missing optional artifacts, malformed optional JSON,
  ambiguous roots, absent timing, missing pair ids, no-mutation traces, and
  multiple loaded agents;
- output tests assert JSON schema keys and Markdown section order;
- taxonomy tests assert only generic categories are emitted;
- diagnostic tests assert every first-patch opportunity has
  `diagnostic_only=true` and a `not_live_policy` string;
- sidecar-only tests assert analyzer code does not import live harness modules,
  provider clients, Harbor runners, or Terminal-Bench runners;
- fixture tests run against existing saved artifacts only and never invoke live
  tasks;
- review checks confirm no provider-visible behavior, prompt, tool schema, or
  runtime code changed as part of observability.

Allowed verification commands for a future implementation:

```bash
uv run pytest --no-testmon -q tests/test_hot_path_observability.py
uv run ruff check <offline-analyzer-files>
uv run python <offline-analyzer-cli> --help
git diff --check
```

Allowed artifact smoke checks must point at existing artifact directories. They
must not start Harbor, Terminal-Bench, providers, or a live mew loop.

## Non-Goals

- No implementation in this design change.
- No live Harbor or Terminal-Bench run.
- No prompt redesign.
- No provider-visible request reshaping.
- No tool schema or tool description change.
- No apply-patch transport change.
- No finish resolver change.
- No WorkFrame or controller policy change.
- No task-specific readiness rule.
- No hypothesis ledger or experiment decision ledger.
- No claim that any divergence metric is causal by itself.

## Phased Implementation Plan If Needed Later

### Phase 0: Freeze Contract

- Commit this design.
- Review JSON and Markdown contracts against reviewer feedback.
- Decide analyzer file names and CLI names in a separate implementation task.

Close gate: reviewers agree the contract is measurement-only and implementable.

### Phase 1: Offline Readers

- Implement artifact readers for Codex normalized traces.
- Implement artifact readers for Claude Code normalized/raw trajectory traces.
- Implement artifact readers for mew native/proof artifacts.
- Return source maps and warnings for every loaded artifact.

Close gate: synthetic reader fixtures pass without invoking live systems.

### Phase 2: Normalization And Metrics

- Normalize all loaded agents into the step schema.
- Add generic intent classification.
- Compute required metrics and pairwise comparisons.
- Keep all missing values nullable.

Close gate: synthetic metric tests prove first tool, mutation, verifier, probe
counts, repeated families, pairing, and prompt size behavior.

### Phase 3: Reports

- Emit JSON and Markdown from the same report object.
- Add deterministic sorting and bounded summaries.
- Add divergence entries and diagnostic-only first-patch opportunities.

Close gate: golden output tests pass and diagnostics cannot be emitted without
`diagnostic_only=true`.

### Phase 4: Existing Artifact Smoke

- Run the analyzer against existing saved reference and mew artifacts only.
- Record any reader gaps as follow-up implementation issues.
- Do not run new live tasks.

Close gate: report is generated from existing artifacts, or failures identify
missing artifact support without changing live behavior.

### Phase 5: Use In Operator Loop

- Use reports to decide what measurement is missing before step-check.
- Put hypotheses, experiment choices, and behavior-change proposals in the
  separate ledger/designs.

Close gate: no report output is consumed by live provider prompts, tool policy,
or runtime control.
