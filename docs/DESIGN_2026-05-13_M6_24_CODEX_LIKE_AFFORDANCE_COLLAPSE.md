# Design 2026-05-13 - M6.24 Codex-Like Affordance Collapse

Status: design only.

Scope: the next `implement_v2` M6.24 repair after native transcript and
`previous_response_id` support. This design changes only the provider-visible
affordance shape: prompt sections, tool descriptions, tool ordering/salience,
and compact tool-result text. It does not implement source code and does not
authorize a broad rewrite.

This design follows:

- `docs/DESIGN_2026-05-13_M6_24_CODEX_LIKE_NATIVE_HOT_PATH.md`
- `docs/REVIEW_2026-05-13_CODEX_TASK_PRESSURE.md`
- `docs/DESIGN_2026-05-13_M6_24_COMMAND_EDIT_BOUNDARY_REDESIGN.md`
- `docs/DESIGN_2026-05-12_M6_24_NATIVE_TOOL_LOOP_RESPONSIBILITY_BOUNDARY.md`
- `docs/DESIGN_2026-05-11_M6_24_IMPLEMENT_V2_NATIVE_TRANSCRIPT_REBUILD.md`

## Problem Statement

`implement_v2` now has the important substrate: provider-native transcript
items, paired native tool outputs, sidecar proof, and `previous_response_id`
transport continuity. But live step-shape still does not behave like Codex. It
keeps reading, searching, and probing long after enough context exists for a
first coherent mutation, and it does not naturally fall into the
edit-verify-repair rhythm.

The current best diagnosis is provider-visible affordance, not missing
reasoning chain and not missing explicit task pressure.

The runtime already exposes `apply_patch`, and the latest steering fields are
mostly diagnostic-only. The remaining failure is that the model-facing
environment still makes probe/read/search behavior too salient, makes the
source mutation path feel less direct than Codex, and often returns tool output
as evidence/proof structure instead of compact text that makes the next edit
obvious.

This repair must not add a controller deadline, threshold, or action card. The
model should choose the next action from the transcript and the tool output it
just saw.

## Evidence

- The Codex reference review found no source-level first-write deadline, probe
  budget, forced patch transition, or task-pressure controller in Codex. Codex
  appears to rely on a simple model-turn loop, an action-oriented prompt,
  first-class `apply_patch`, and terminal-shaped output.
- The Codex reference trace edited with `apply_patch`, then immediately ran the
  runtime, observed a concrete unsupported-instruction failure, patched again,
  and reran. That shape is the target, not the exact task or exact step count.
- The latest mew smoke artifact recorded 40 tool calls and 40 paired outputs
  with zero writes before timeout. It also recorded that first-write pressure
  fields were diagnostic-only and provider-hidden, so the absence of writes was
  not caused by a missing visible pressure flag.
- Mew already exposes custom/freeform `apply_patch` in native provider
  requests. The gap is not merely tool availability.
- Current prompt code still has a long visible active-coding rhythm that names
  cheap probes, fallback probes, read/search/inspect/run_command, frontier
  incompleteness, and first-write concepts repeatedly. The same prompt path can
  still include a prompt-visible WorkFrame rule telling the model to follow
  `required_next`.
- Current native sidecar code has an explicit forbidden steering key list, but
  legacy fields such as `required_next_kind` still appear in derived WorkFrame
  and todo projections. This is acceptable internally only if the provider
  inventory proves those fields do not leak into live input.

## Durable Decision

The next repair is a provider-visible affordance collapse:

```text
short static implement_v2 instructions
  + provider-native transcript / previous_response_id continuation
  + compact factual tool outputs
  + first-class apply_patch/edit mutation surface
  + sidecar-only observability
```

The live hot path remains:

```text
model emits provider-native tool_call
  -> runtime executes the tool
  -> runtime appends exactly one paired function_call_output/custom_tool_call_output
  -> next provider call receives the native conversation continuation
  -> model decides the next action
```

`previous_response_id` may be used as transport continuity, but it is not the
source of truth. `response_transcript.json`, `response_items.jsonl`, request
descriptors, provider request inventory, and sidecar hashes remain the local
proof authority. Replay must be able to explain what the provider saw even when
the provider request used server-side continuation.

When `previous_response_id` is active, refreshed compact sidecar context remains
wire-visible for the current M6.24 implementation. Two live diagnostics showed
that suppressing the refreshed context, even with a minimal task-context
refresh, drove the run back to zero writes. Until native transcript
server-continuation parity is proven, the safe Codex-like shape is:

```text
previous_response_id
  + refreshed compact factual task/sidecar context
  + newly paired tool/function outputs
```

The compact sidecar must stay bounded and factual: no WorkFrame, frontier,
proof, todo, `next_action`, `required_next`, first-write pressure, probe
thresholds, or controller fields. Request descriptors still record logical
input hashes and any future suppressed refresh counts for audit.

The provider-visible repair is generic. It must work for ordinary coding tasks,
hard-runtime artifact tasks, and future implementation tasks without
MIPS-specific, VM-specific, or Terminal-Bench-specific heuristics.

## Non-Goals

- No source implementation in this document.
- No provider-visible `next_action`, `required_next`, `first_write_due`,
  `prewrite_probe_plateau`, max probe count, threshold hint, WorkFrame action
  card, or renamed equivalent.
- No model-visible WorkFrame planner or frontier/todo/proof state object.
- No removal of read/search/probe tools.
- No weakening of write safety, command lifecycle safety, finish acceptance,
  sidecar proof, replay, typed evidence, observer detail, or metrics.
- No broad shell mutation classifier revival.
- No broad speed proof until fastcheck, one pre-speed 10 minute step-shape
  diagnostic, and reference-step comparison are green or explicitly yellow for
  a non-hot-path reason.
- No backward compatibility promise before release, but also no needless large
  rewrite when prompt/tool/output shape can reach the gate.

## Proposed Provider-Visible Contract

Production `implement_v2` provider input is limited to:

1. short stable implementation instructions;
2. the provider-native transcript continuation, either explicit transcript
   window or `previous_response_id` plus paired output items;
3. compact factual tool-result text;
4. a bounded factual sidecar digest only when needed for refs, verifier
   freshness facts, and finish blockers.

The model must not see:

- full `WorkFrame`;
- prompt-visible `required_next`;
- old active todo/frontier/proof objects;
- full `persisted_lane_state`;
- diagnostic loop signals such as `first_write_due`;
- probe thresholds or max probe counts;
- instruction text that says a controller has decided the next tool or next
  phase.

Allowed provider-visible facts:

- tool names, status, exit code, command id, cwd, and bounded stdout/stderr;
- changed paths, diffstat, source diff refs, typed evidence refs;
- path:line anchors and bounded code excerpts from read/search;
- verifier freshness stated as a fact, for example "no verifier result after
  this source change";
- finish blockers and missing evidence refs;
- artifact refs and sidecar refs.

Forbidden provider-visible pressure:

- "must patch now";
- "first write is due";
- "only one more probe";
- "required next is apply_patch";
- "controller selected edit";
- "prewrite probe plateau";
- any JSON field whose purpose is to prescribe the next ordinary repair action.

### Canonical forbidden provider-visible fields

All provider-visible leak gates must use one canonical list. The list is not a
documentation example; it is the test fixture source for prompt scans, compact
digest scans, tool-output scans, provider request inventory scans, and assembled
task-contract scans.

Canonical forbidden field names and markers:

- `next_action`
- `next_action_policy`
- `next_action_contract`
- `required_next`
- `required_next_kind`
- `required_next_action`
- `required_next_evidence_refs`
- `required_next_probe`
- `suggested_next_action`
- `recommended_next_action`
- `first_write_due`
- `first_write_due_entry_turn`
- `first_write_due_overrun`
- `first_write_grace_probe_calls`
- `first_write_probe_threshold`
- `first_write_turn_threshold`
- `max_additional_probe_turns`
- `prewrite_probe_plateau`
- `WorkFrame`
- `workframe`
- `workframe_projection`
- `prompt_visible_workframe`
- `persisted_lane_state`
- `lane_local_state`
- `active_work_todo`
- `hard_runtime_frontier`
- `frontier`
- `frontier_state`
- `frontier_state_update`
- `model_authored_frontier`
- `model_authored_proof`
- `model_authored_todo`
- `proof`
- `proof_state`
- `repair_history`
- `todo`
- `history_json`
- model-JSON response-contract fields when presented as instructions:
  `tool_calls`, `frontier_state_update`, `history_json`

The scan is structural when the provider-visible surface is JSON-like. For
plain prompt or tool-output text, short generic words such as `proof`, `todo`,
and `frontier` are checked only as unmistakable rendered keys or headers, for
example `"proof":`, `proof=`, `<proof>`, or `## WorkFrame`, not as ordinary
prose. A string match in literal source code, a user-supplied code excerpt, or
a quoted error message may be marked `user_literal` only if the inventory
records the containing section, offset, and reason. The default is fail-closed.

Each canonical field must have at least one fixture that injects that exact
field into assembled provider-visible input and verifies rejection. Additional
fixtures must cover the four surfaces where old steering is most likely to
return:

- lane prompt sections;
- assembled task contract;
- compact digest;
- visible tool-output cards.

Sidecar-only fixtures must prove the same names are allowed only in internal
artifacts when the inventory records `provider_visible=false`.

## Prompt Collapse

The visible prompt should be short enough that the dominant message is the
normal coding loop, not a policy apparatus.

Replace the current long active-coding rhythm, prompt-visible WorkFrame rule,
hard-runtime first-write prose, and fallback-probe paragraphs with a compact
static contract:

```text
You are implementing in a repository through native tool calls.
Inspect enough context to understand the smallest coherent change.
Make source changes with apply_patch for multi-line edits, or edit_file for
precise replacements.
Use run_command/run_tests to build, run, and verify.
If the task or verifier names a missing source/artifact path, treat it as the
target path and create the smallest runnable file before extended reverse
engineering.
Repair from the latest concrete failure shown in the transcript.
Finish only with fresh evidence from the tools.
```

This is action-oriented but not controller pressure. It names the ordinary
workflow without deadlines, counters, or a prescribed next turn.

Provider-visible prompt sections should collapse to:

- `implement_v2_lane_base`: native loop and finish-through-evidence rule;
- `implement_v2_tool_contract`: every call receives exactly one paired output;
- `implement_v2_coding_contract`: the short text above;
- `implement_v2_task_contract`: the user task contract;
- optional bounded `compact_sidecar_digest`: refs and factual blockers only.

Remove from the default provider-visible path:

- `implement_v2_workframe`;
- prompt-visible WorkFrame JSON;
- "Follow required_next";
- `implement_v2_hard_runtime_profile` as task-specific first-write prose;
- repeated cheap-probe and fallback-probe paragraphs;
- full `implement_v2_lane_state` if it exposes old local state instead of
  stable identifiers and capability facts.

Default provider-visible input should remove `implement_v2_lane_state`. If a
compatibility path keeps it temporarily, it must be an allowlisted scalar-only
card with no nested local state. Allowed keys are:

- `work_session_id`
- `task_id`
- `lane`
- `model_backend`
- `model`
- `effort`
- `permission_mode`
- `workspace_ref` or `workspace_hash`
- `artifact_root_ref` or `artifact_root_hash`
- `tool_capability_hash`

Forbidden in any compatibility lane-state card:

- `lane_local_state`
- `persisted_lane_state`
- `active_work_todo`
- `hard_runtime_frontier`
- `repair_history`
- any canonical forbidden provider-visible field.

Hard-runtime tasks may still receive generic runtime facts from the task
contract and tool outputs. They must not receive a separate prompt profile that
reintroduces first-write or probe pressure.

## Tool Description Changes

The tool surface remains broad, but the provider-visible descriptions should
make mutation direct and make read/search supporting tools feel lightweight.

### Ordering and grouping

When provider tooling preserves order, place tools in a workflow order that
does not lead with the probe vocabulary:

1. `apply_patch`
2. `edit_file`
3. `write_file` when available
4. `run_command`
5. `run_tests`
6. command lifecycle tools
7. `read_file`
8. `search_text`
9. `glob`
10. `inspect_dir`
11. `git_status`
12. `git_diff`
13. `finish`

If provider ordering is not stable, request descriptors still record the
intended order and tool spec hash so drift is reviewable. Descriptions and
output shape are the primary salience levers; ordering is helpful but not
load-bearing when a provider shuffles tool specs.

### Mutation tools

`apply_patch`:

- primary source mutation tool for multi-line source edits, file creation,
  deletions, and renames;
- custom/freeform grammar tool when provider capability allows;
- JSON fallback only when custom/freeform is unavailable, recorded as a
  capability fallback in the request descriptor;
- provider-visible description should be short and direct:
  "Apply a raw patch to source files. Use this for multi-line edits, new files,
  deletions, and renames. Do not wrap custom/freeform patch input in JSON."

`edit_file`:

- precise exact replacement or structured hunk edits;
- provider-visible description should emphasize anchors and ambiguity failure;
- output should show changed path, hunk count, and diff refs.

`write_file`:

- small complete file creation or non-source generated file writes;
- not the natural route for large source rewrites;
- may remain hidden for task shapes where existing policy already removes it,
  but this design does not depend on task-specific removal.

### Execute tools

`run_command` and `run_tests` are process runners. Their descriptions should
not mention broad source exploration first. They should say:

- run bounded commands, builds, runtimes, diagnostics, and verifiers;
- source edits belong to `apply_patch`, `edit_file`, or `write_file`;
- command output is compact by default, but the model may request a bounded
  per-command output budget when terminal text is needed to edit.

Lifecycle tools keep short descriptions. They should not introduce mutation
or repair policy. `read_command_output` is hidden until there is an active
command or a completed command with an output ref; `poll_command` and
`cancel_command` remain active-command-only.

### Read/search tools

Keep `read_file`, `search_text`, `glob`, `inspect_dir`, `git_status`, and
`git_diff`.

Lower their salience by:

- shortening descriptions;
- removing "cheap probe", "frontier", and fallback-probe phrasing from the
  visible tool descriptions;
- returning compact path/line anchors and excerpts so one search result can
  support an edit;
- not advertising broad recursive probing as the main behavior.

## Tool Output Shaping Rules

Tool outputs should look like concise editable transcript entries, not hidden
evidence objects. Full detail stays in sidecars.

General output rules:

- start with one plain status line;
- include only bounded fields useful for the next model turn;
- include refs for full stdout/stderr, diffs, evidence, and sidecars;
- include path:line anchors whenever the output points at source;
- include the newest failure before older or generic context;
- keep JSON-like payloads out of the visible output unless the called tool is
  explicitly a structured query;
- do not include `next_action`, `required_next`, `suggested_next_action`,
  `first_write_due`, probe thresholds, or controller phase instructions.

Preferred visible result card shape:

```text
<tool> result: <status>; <key facts>
paths: <path anchors or changed paths>
latest_failure: <bounded newest concrete failure, if any>
output_tail: <bounded stdout/stderr tail, if useful>
refs: <artifact refs, evidence refs, diff refs>
```

Concrete caps are part of the contract. Implementations may define these in a
single config object such as `NativeVisibleAffordanceCaps`, but the tests must
also include an explicit fixture named
`tests/fixtures/implement_v2_affordance_visibility_caps.json` or an equivalent
checked-in fixture with the same fields. If a live config object exists,
fastcheck must load the fixture and assert that the live config matches the
fixture values before checking artifacts.

Required caps:

| Surface | Target cap | Hard red gate | Additional caps |
| --- | ---: | ---: | --- |
| `compact_sidecar_digest` serialized JSON | 4096 bytes | 6144 bytes | top-level keys <= 16; latest tool cards <= 6; latest evidence refs <= 12 |
| `compact_sidecar_digest.latest_tool_results[*].summary` | 160 chars | 240 chars | refs <= 2 output refs and <= 2 evidence refs per card |
| provider-visible tool-output card | 4096 bytes | 6144 bytes | status line <= 240 chars; refs block <= 12 refs |
| `search_text` visible card | 4096 bytes | 6144 bytes | matches <= 8; excerpt <= 180 chars per match |
| `read_file` visible card | 4096 bytes | 6144 bytes | excerpt <= 160 lines; line text clipped to 220 chars |
| `run_command` / `run_tests` visible card | 4096 bytes default | 6144 bytes default; 60000 bytes with explicit per-call output budget | latest_failure <= 1200 chars; stdout/stderr default tail <= 1200 chars; requested output budget is clamped to 50000 chars |
| mutation visible card | 2048 bytes | 4096 bytes | changed paths <= 12; hunk/diffstat summary <= 1000 chars |

Any truncation must include a ref to the full sidecar content. A cap failure is
a fastcheck failure unless the artifact explicitly records a fixture-approved
tool-specific override.

### Read/search output

`search_text` should return:

- match count and truncation state;
- top matches as `path:line: excerpt`;
- enough surrounding text to choose a narrow `read_file` or `apply_patch`;
- refs for the full search result.

`read_file` should return:

- path, line range, truncation state;
- line-numbered excerpt;
- optional symbol/header context when cheap and already known;
- no "read more before editing" instruction.

### Command/verifier output

`run_command` and `run_tests` should return:

- command id, status, exit code, elapsed time, cwd;
- newest concrete failure first;
- file/test/path anchors extracted from stderr/stdout when available;
- bounded stdout/stderr tail;
- artifact refs and full output refs;
- observed source side-effect refs, if any;
- verifier freshness facts, not a command to run next.

For a failed runtime or test, the visible output should make the failure
readable without opening a sidecar first. Sidecars still carry the full output.

### Mutation output

`apply_patch`, `edit_file`, and `write_file` should return:

- changed paths;
- added/modified/deleted counts;
- hunk count or diffstat;
- source diff ref;
- typed mutation evidence refs;
- verification freshness as a fact when applicable.

They should not say "run verifier next" as a provider-visible instruction.
The model can infer that from the changed source and the static coding
contract.

### Invalid contract output

When a process tool is rejected because it was used as an edit API, return a
paired tool output that states the contract:

```text
run_command result: rejected; source edits are handled by apply_patch/edit_file/write_file.
preserved_command_ref: artifact://...
```

This recovery text is allowed only for rejected edit-via-command calls or a
failed named shell-`apply_patch` bridge. It must not appear on successful
process commands, ordinary command failures, read/search results, mutation
results, or verifier failures. It must not become a general next-action policy
or probe threshold.

## Sidecar, Observer, and Metrics Preservation

No observability may be removed to make the prompt shorter.

Keep or strengthen:

- `response_transcript.json`;
- `response_items.jsonl`;
- `call_result_pairing.json`;
- `transcript_metrics.json`;
- `proof-manifest.json`;
- request descriptor and provider request inventory;
- provider-visible forbidden-field report;
- tool route decisions;
- command lifecycle records;
- stdout/stderr refs;
- source snapshot and source diff refs;
- typed evidence refs;
- resolver decisions;
- WorkFrame/debug bundles as sidecar-only artifacts;
- terminal-bench normalized trace;
- fastcheck and replay artifacts.

CompletionResolver consumes the authoritative transcript, typed evidence,
resolver-side sidecars, and sidecar-only WorkFrame/debug projections directly.
The compact digest is only a bounded provider-visible mirror of selected facts.
It must never become the resolver input authority.

Diagnostic loop metrics remain sidecar-only:

- first-write latency;
- first-write turn index;
- probe/read/search count before first write;
- verifier count and first verifier latency;
- same-family repeat count;
- provider-visible prompt bytes and tool-output bytes;
- apply_patch availability and provider tool kind;
- custom/freeform fallback reason, if any.
- prompt cache/cost metrics:
  - static prompt bytes;
  - dynamic prompt bytes;
  - tool schema bytes;
  - compact digest bytes;
  - visible tool-output bytes;
  - prompt cache key/hash;
  - cache hit/miss or provider cache eligibility when available.

The provider inventory must report:

- dynamic sections included in each request;
- whether `previous_response_id` was used;
- whether a refreshed compact sidecar context item was sent, or suppressed by
  a future optimization, while `previous_response_id` carried the prior
  transcript;
- transcript/window hash or equivalent local continuation hash;
- compact digest hash and byte size;
- compact digest top-level key count;
- tool spec hash and ordered tool names;
- forbidden provider-visible field scan result;
- diagnostic-only field scan result.

## Phase Plan

### Phase 0: Baseline and Static Leak Gates

Intent: freeze the current failure shape and prevent old steering from leaking
back while later phases shorten the surface. Phase 0 adds scan/gate
infrastructure and baseline artifacts only. It must not change live prompt,
tool description, tool ordering, or tool-output behavior.

Implementation slice:

- capture current prompt section inventory, tool spec inventory, provider
  request inventory, and one saved native artifact baseline;
- add or update static gates from the canonical forbidden provider-visible
  field list;
- add prompt-text gates for old WorkFrame and probe-pressure language;
- add output-card gates for forbidden next-action fields;
- add assembled-task-contract scanning, not only lane prompt section scanning;
- add one failing fixture per canonical forbidden field;
- record sidecar-only diagnostic fields in observer artifacts.

Close gate:

- focused provider input inventory tests pass;
- every canonical forbidden field has a fixture that fails when the field is
  sent provider-visible, including legacy derived names such as
  `required_next_kind`, `required_next_action`, and `required_next_probe`;
- fixture coverage includes prompt sections, assembled task contract, compact
  digest, and visible tool-output cards;
- the same diagnostic names are allowed in sidecar-only artifacts with explicit
  `provider_visible=false`;
- baseline records zero-write/probe-loop evidence without treating that metric
  as live steering;
- no prompt/tool/output behavior changes are included in Phase 0.

### Phase 1: Prompt Collapse

Intent: replace verbose repair/probe/WorkFrame prompt prose with a short
Codex-like coding contract.

Implementation slice:

- remove default provider-visible WorkFrame prompt JSON;
- remove "Follow required_next";
- replace long active-coding and hard-runtime probe prose with the compact
  coding contract;
- keep task contract and native tool pairing rules;
- keep sidecar/debug WorkFrame artifacts out of provider input.

Close gate:

- default provider-visible prompt sections are limited to lane base, tool
  contract, coding contract, task contract, and optional compact factual
  digest;
- `implement_v2_lane_state` is removed from the default provider-visible path,
  or compatibility output matches the scalar-only allowlist in this design;
- provider-visible prompt contains no `required_next`, `first_write_due`,
  `prewrite_probe_plateau`, "probe threshold", "before first write", or
  WorkFrame action-card language;
- provider-visible non-tool, non-task prompt bytes drop at least 40% from the
  Phase 0 baseline and are <= 2500 bytes unless a reviewer approves a
  documented safety exception;
- prompt cache/cost metrics are recorded, and static prompt bytes must not grow
  more than 10% after Phase 1 without a review note;
- native transcript pairing and finish resolver tests still pass;
- sidecar WorkFrame/debug bundles still exist.

### Phase 2: Tool Salience Collapse

Intent: keep the tools but change the provider-visible tool surface so read,
search, and probe tools are supporting context tools rather than the apparent
main workflow.

Implementation slice:

- shorten read/search/glob/inspect descriptions;
- remove visible "cheap probe", "frontier", and fallback-probe prose from tool
  descriptions;
- reorder or group tool specs so mutation and execution routes are prominent;
- keep all read/search tools available unless an existing permission mode
  already hides them;
- update request descriptor and tests for ordered tool names and tool spec
  hash.

Close gate:

- `apply_patch` is provider-visible as a custom/freeform tool when provider
  capability allows;
- read/search/probe tools remain present but have compact descriptions;
- tool descriptions do not contain controller-style repair instructions;
- request inventory records ordered tool names, provider tool kinds, and
  fallback reasons;
- no shell mutation classifier reappears.

### Phase 3: Apply Patch and Edit as Primary Mutation Affordance

Intent: make the first source mutation path feel like Codex: direct patch/edit,
not JSON-heavy generated source or shell editing.

Implementation slice:

- protect freeform `apply_patch` as the default provider-native lowering;
- keep JSON fallback explicit and auditable;
- make `apply_patch` description shorter and stronger;
- keep `edit_file` as precise replacement;
- keep `write_file` as small complete file creation or non-source write;
- preserve narrow shell-invoked `apply_patch` bridge behavior if implemented,
  with typed mutation evidence.

Close gate:

- provider request fixture proves `apply_patch` is custom/freeform under normal
  capability;
- fallback fixture proves JSON `apply_patch` appears only when custom/freeform
  is unavailable and records the reason;
- mutation tool outputs carry changed paths, diff refs, and typed evidence
  refs;
- execute-route tools reject edit-shaped arguments with paired contract output;
- no source mutation acceptance depends on arbitrary shell command text.

### Phase 4: Compact Editable Tool Outputs

Intent: make the transcript itself carry the next-edit signal without a
provider-visible action card.

Implementation slice:

- introduce or normalize concise visible result cards for read/search,
  command/verifier, and mutation tools;
- ensure command/test failures put the newest concrete failure first;
- add path:line anchors and bounded excerpts where possible;
- keep full output, diffs, and evidence in refs;
- update fastcheck/replay to validate output shape and byte caps.

Close gate:

- read/search fixtures include path:line anchors and bounded excerpts;
- command/test failure fixtures show latest failure before generic output tail;
- mutation fixtures include changed paths, diffstat/hunk count, diff refs, and
  typed evidence refs;
- visible tool outputs contain no `next_action`, `required_next`,
  `first_write_due`, threshold, or controller phase field;
- output cards satisfy the concrete caps in
  `tests/fixtures/implement_v2_affordance_visibility_caps.json` or the
  equivalent checked-in cap fixture;
- compact digest fixtures satisfy serialized JSON <= 4096 target bytes, <= 6144
  hard gate bytes, top-level keys <= 16, latest tool cards <= 6, and latest
  evidence refs <= 12;
- invalid-tool-contract recovery text appears only on rejected edit-via-command
  calls or failed named shell-`apply_patch` bridge calls;
- sidecar refs allow replay to recover the full detail omitted from the
  compact output.

### Phase 5: Fastcheck and 10 Minute Step-Shape Validation

Intent: prove the collapse improved live shape before broad speed proof.

Implementation slice:

- run focused unit tests for prompt inventory, tool schema, tool output cards,
  native transcript pairing, replay, and fastcheck;
- run native fastcheck on a saved artifact and on the new artifact;
- run exactly one pre-speed 10 minute step-shape diagnostic;
- compare the result to the Codex reference step shape at the behavior level.

Close gate:

- focused tests pass;
- `scripts/check_implement_v2_hot_path.py` or successor native fastcheck passes
  for the artifact under test;
- provider inventory proves forbidden steering fields are absent;
- command schema exposes only bounded output-budget affordances
  (`max_output_chars` / `max_output_tokens`) and no command self-labeling fields;
- a fresh fake-native run proves either a requested command output budget returns
  more than the default 1200 visible chars or completed command output is
  reread through `read_command_output`;
- sidecar artifacts prove diagnostic loop metrics still exist internally;
- the 10 minute diagnostic reaches a natural source mutation or fails with a
  classified yellow/non-hot-path reason;
- reference-step comparison shows the intended rhythm is available:
  inspect/probe enough context, mutate with patch/edit, run verifier/runtime,
  repair from latest concrete failure;
- broad speed/proof measurement remains blocked if the run still has zero
  writes because read/search/probe behavior dominated the transcript.

## Validation Plan

Validation order:

1. `git diff --check` and changed-file scope check.
2. Focused unit tests for provider inventory, prompt section inventory,
   assembled task-contract scanning, tool schema lowering, tool output card
   formatting, sidecar preservation, and native transcript pairing.
3. Native fastcheck against saved native transcript artifacts.
4. Replay/dogfood/emulator checks where relevant.
5. One pre-speed 10 minute step-shape diagnostic.
6. Reference-step comparison against Codex behavior from
   `docs/REVIEW_2026-05-13_CODEX_TASK_PRESSURE.md`.

Fastcheck must verify:

- transcript is the provider input authority;
- every call has exactly one paired output;
- `previous_response_id` use is recorded and explainable from local transcript
  artifacts;
- forbidden provider-visible fields are absent;
- compact digest size and keys are bounded;
- tool output cards meet byte caps and include refs;
- diagnostic fields remain sidecar-only;
- prompt cache/cost metrics are recorded and compared to the Phase 0 baseline.

The 10 minute step-shape diagnostic is not a speed proof. It answers one
question: does the live transcript now make mutation and verifier repair a
natural path without provider-visible controller pressure?

Allowed yellow/non-hot-path failure classes for the 10 minute diagnostic:

- provider outage, provider read timeout, or rate-limit failure before enough
  turns execute to evaluate affordance;
- permission/sandbox denial unrelated to prompt or tool salience;
- missing external dependency or unavailable executable required by the task;
- benchmark harness setup failure;
- artifact root or filesystem setup failure;
- verifier infrastructure bug where the transcript already reached mutation;
- provider/tool capability limitation, such as no custom/freeform tool support,
  when fallback behavior is separately proven.

Not yellow:

- zero writes after a normal-length transcript dominated by read/search/probe;
- repeated broad probing after tool output already contains editable anchors;
- hidden provider-visible pressure needed to leave the probe loop;
- task-specific repair that only works for MIPS, VM, or Terminal-Bench.

Reference-step comparison is qualitative but bounded:

- compare first mutation route, not exact turn count;
- compare whether latest tool output is directly editable;
- compare whether the model repairs after a concrete runtime/verifier failure;
- compare whether any controller-visible action field was needed;
- reject task-specific explanations that only fit MIPS, VM, or
  Terminal-Bench.

## Anti-Drift Checks

Provider-visible input scan fails on any default live request containing any
field from the canonical forbidden provider-visible list. This scan applies to
the complete assembled provider input, including lane prompt sections, task
contract, compact digest, tool-output cards carried into the next turn, and any
compatibility lane-state card.

Prompt scan fails on:

- "Follow required_next";
- "before first write";
- "at most one focused diagnostic/read turn";
- "probe threshold";
- "frontier as incomplete" in default provider-visible prompt prose;
- task-specific hard-runtime prompt profiles that prescribe first-write shape.

The default coding contract is also positive-shape checked: it must be built
from the approved compact sentence set or stay within the Phase 1
non-tool/non-task byte and sentence caps. Adding new first-write/probe-pressure
prose requires an explicit design update.

Tool description scan fails on:

- read/search descriptions that describe broad recursive source exploration as
  the main route;
- mutation descriptions that prefer JSON `write_file` for large source
  rewrites;
- execute-tool descriptions that imply shell is a source mutation API.

Tool output scan fails on:

- next-action fields;
- threshold fields;
- controller phase fields used as instructions;
- missing refs for truncated output;
- visible output or compact digest cap violations;
- invalid-tool-contract recovery text outside rejected edit-via-command or
  failed named shell-`apply_patch` bridge outputs;
- command/test failures that hide the latest concrete failure behind generic
  artifact prose.

Observer preservation scan fails if:

- diagnostic loop metrics disappear from sidecars;
- WorkFrame/debug bundles are deleted instead of moved sidecar-only;
- provider request inventory no longer records dynamic sections, tool spec
  hash, prompt bytes, compact digest hash, or `previous_response_id` use;
- replay cannot reconstruct the visible compact output from transcript plus
  sidecars.

## Risks

- The prompt may become too short and omit safety or finish details. Mitigation:
  keep the paired-output contract, finish-through-evidence rule, write safety,
  and CompletionResolver outside the collapsed prose.
- Lower read/search salience may cause premature edits on some tasks.
  Mitigation: read/search tools remain available, and verifier failure repairs
  should expose missing context as concrete output.
- Compact tool output may hide useful detail. Mitigation: every truncation
  carries refs, and sidecars keep full output.
- `apply_patch` custom/freeform support may vary by provider. Mitigation:
  fallback is explicit, audited, and tested; it is not the default design.
- Tool ordering may not affect every provider. Mitigation: descriptions and
  output shape are the primary change; ordering is recorded but not trusted as
  the only lever.
- Invalid contract recovery text can drift into action policy. Mitigation:
  contract errors may name allowed mutation tools, but must not contain
  thresholds or ordinary next-action fields.
- Metrics could become de facto live pressure again. Mitigation: all loop
  metrics are sidecar-only and provider inventory gates enforce that boundary.

## Rollback Criteria

Rollback or stop the phase sequence if any of these occur:

- native call/output pairing breaks;
- provider request inventory cannot prove what was visible;
- forbidden steering fields appear in provider input;
- sidecar proof, replay, typed evidence, or resolver decisions are lost;
- `apply_patch` disappears from the normal provider-native tool surface;
- execute-route tools regain broad shell mutation semantics;
- compact output removes enough detail that fastcheck/replay cannot reconstruct
  the omitted evidence;
- the pre-speed 10 minute diagnostic still shows zero writes and the failure is
  attributable to prompt/tool/output affordance rather than provider outage,
  permission, or unrelated task setup.

Rollback should be narrow:

- Phase 1 rollback restores only prompt text;
- Phase 2 rollback restores only tool descriptions/order;
- Phase 3 rollback restores only tool lowering or mutation descriptions;
- Phase 4 rollback restores only visible output formatting;
- sidecar/proof preservation changes should not be rolled back unless they are
  the cause of failure.

If the design fails after two focused affordance iterations, the next design
should reduce provider-visible sidecar projection further. It should not add
first-write deadlines, probe thresholds, or WorkFrame steering.
