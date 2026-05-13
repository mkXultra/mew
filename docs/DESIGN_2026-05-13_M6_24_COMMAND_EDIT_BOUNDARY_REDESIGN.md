# Design 2026-05-13 - M6.24 Command/Edit Boundary Redesign

Status: implementation in progress. Phase 0-2 are implemented and reviewed;
Phase 3-7 remain open.

Scope: `implement_v2` native tool loop command/edit boundary. This document
does not authorize code changes by itself. It intentionally does not preserve
backward compatibility with old `implement_v2` shell-edit behavior, model-JSON
tool contracts, or artifact shapes.

## Context

Recent local reference investigation changed the direction for M6.24:

- Codex CLI and Claude Code do not rely on a huge shell mutation classifier.
- Shell is primarily a process runner with safety, permission, lifecycle,
  summary, and read/search metadata support.
- Source edits are routed through typed edit/write/patch tools.
- Shell parsing is conservative. Simple commands can produce metadata;
  complex or unavailable parse states fail closed for policy shortcuts.
- Compatibility bridges exist only for narrow exact cases, such as Codex
  intercepting shell-invoked `apply_patch` and routing it to the apply-patch
  tool.

Local reference files used for this design:

- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/shell.rs`
- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs`
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx`
- `references/fresh-cli/claude-code/src/utils/bash/ast.ts`
- `references/fresh-cli/claude-code/src/tools/FileEditTool/FileEditTool.ts`
- `docs/REVIEW_2026-05-03_COMMAND_CLASSIFICATION_REFERENCES_CODEX.md`
- `docs/REVIEW_2026-05-10_APPLY_PATCH_INTERFACE_CODEX_COMPARISON.md`
- `docs/DESIGN_2026-05-11_M6_24_IMPLEMENT_V2_NATIVE_TRANSCRIPT_REBUILD.md`
- `docs/DESIGN_2026-05-12_M6_24_NATIVE_TOOL_LOOP_RESPONSIBILITY_BOUNDARY.md`

## Problem

The current tempting path is to keep polishing regex or `shlex` command
mutation detection until `run_command` can infer whether a command mutates
source. That is the wrong abstraction.

The product problem is not "classify all shell mutation." The product problem
is to make `implement_v2` choose a reliable route for each tool intent:

- process execution and probes use execute-route tools such as `run_command`
  and `run_tests`;
- source mutation uses a typed mutation tool;
- shell parser output helps summarize, permission, and debug simple commands;
- complex shell remains observable but does not gain source-edit semantics;
- post-exec source diffs catch accidental or legacy shell side effects without
  making shell the source mutation API.

Without this boundary, mew keeps spending design effort on a classifier that
will always be either unsound or incomplete, and the native transcript work
will inherit the same wrong responsibility split.

## Decision

Redesign the command/edit boundary around five hard invariants.

1. Execute-route tools are process runners, not source mutation APIs.
   This includes `run_command`, `run_tests`, and equivalent future process
   tools. Lifecycle tools such as `poll_command`, `cancel_command`, and
   `read_command_output` only observe or control an existing process.
2. Source changes requested by the model go through `write_file`, `edit_file`,
   `apply_patch`, or an equivalent typed mutation tool.
3. Shell parsing returns conservative metadata only:
   `simple`, `too_complex`, or `unavailable`.
4. Legacy shell-edit compatibility is narrow and allowed only when an exact
   diff can be computed safely before the source mutation is applied.
5. Every terminal execute-route result has source snapshot/diff observation as
   a safety net, with native transcript and typed evidence refs preserved.

The implementation should prefer deletion or quarantine of old live behavior
over compatibility shims. This is before release; drastic changes are allowed.

## Target Architecture

```text
provider-native transcript
  -> model emits native tool call
  -> tool router builds ToolRouteDecision
  -> one of:
       read route
       process runner route
       process lifecycle route
       typed source mutation route
       exact legacy shell-edit bridge
       finish route
       invalid tool contract route
  -> tool runtime executes
  -> sidecar artifacts record route, snapshots, diff, evidence refs
  -> exactly one paired native tool output is appended for the provider call id
  -> WorkFrame/evidence/metrics are projections over transcript plus sidecars
```

Canonical `tool_route` enum:

- `read`
- `process_runner`
- `process_lifecycle`
- `typed_source_mutation`
- `legacy_shell_edit_bridge`
- `finish`
- `invalid_tool_contract`

No route enum may encode inferred shell mutation. In particular,
`shell_source_mutation`, `inferred_shell_edit`, `safe_shell_edit`, and similar
routes are explicitly forbidden.

Proposed module homes:

- Source root derivation: `src/mew/tool_kernel.py`, via
  `ToolKernelConfig.source_mutation_roots` and normalized workspace defaults.
- Snapshot root and ignore policy: `src/mew/implement_lane/exec_runtime.py` at
  first, then a small extracted helper if the code grows. This policy owns
  source-root caps, path ignore rules, file caps, hash caps, and fallback
  statuses.
- Write-root policy: `src/mew/implement_lane/write_runtime.py` and the existing
  `allowed_write_roots` path checks. Snapshot roots never widen write roots.
- Bridge registry: new `src/mew/implement_lane/legacy_shell_edit_bridge.py` or
  equivalent. It owns the bridge manifest and is the only place a shell-edit
  compatibility entry can be registered.
- Route and sidecar schema: new `src/mew/implement_lane/tool_routes.py` or
  equivalent shared by native harness, exec runtime, write runtime, WorkFrame,
  and fastcheck.

The model-visible surface should make the boundary explicit:

- use `run_command` or `run_tests` for bounded commands, shell probes, builds,
  tests, diagnostics, and process execution;
- use `poll_command`, `cancel_command`, and `read_command_output` only for
  command lifecycle and output observation;
- use source mutation tools for repository edits;
- do not create or patch source-like files through `run_command` when typed
  mutation tools are available;
- failed named bridge attempts should return a typed recovery hint naming the
  source mutation tool route.

## Route Semantics

### Execute-route tools: process runner family

`run_command`, `run_tests`, and equivalent future execute-route tools own
process execution:

- command, `argv`, shell invocation, `cwd`, environment, timeout, foreground
  budget, yielding, polling, cancellation, and output spooling;
- approval and sandbox checks for process execution;
- bounded stdout/stderr summaries and output refs;
- command metadata artifacts;
- pre-exec and post-exec source snapshots;
- observed source diff artifacts after execution.

`run_tests` remains verifier-shaped process execution. It is not a source
mutation API, and it must not smuggle source writes into a verifier command.

`poll_command`, `cancel_command`, and `read_command_output` are
`process_lifecycle` routes. They may carry command metadata, snapshot ids,
terminal diff refs, and output refs from the original command run, but they do
not start a new source mutation route and cannot become typed source mutation
evidence.

Execute-route tools do not own source mutation semantics:

- they do not accept `content`, `patch`, `edits`, `old_string`, `new_string`,
  or source-mutation intent fields;
- they do not return source mutation evidence merely because a shell command
  changed files;
- they do not mark a model-requested edit as accepted unless the edit went
  through a typed mutation route or an exact bridge;
- they do not classify arbitrary shell as "source edit", "safe edit",
  "mutation edit", or similar semantic categories.

A command may still modify files at runtime. The distinction is that this is
an observed process side effect, not the approved source mutation API.

### Typed source mutation route

Typed source mutation tools own model-requested source changes:

- `write_file`: exact full-content write or create, with path, content hash,
  diff, and write approval.
- `edit_file`: exact old/new replacement or structured hunks, with anchor
  validation and ambiguity recovery.
- `apply_patch`: grammar-backed patch, preferably provider-native/freeform
  where supported; `patch_lines` or other structured fallback is acceptable
  where freeform is unavailable.

Equivalent future tools are allowed only if they preserve the same properties:

- explicit target paths;
- exact desired content or exact patch;
- deterministic pre-apply validation;
- source-root/write-root policy checks before mutation;
- computed diff artifact before or during apply;
- typed evidence refs after successful apply;
- one paired native tool output for the original provider call id.

Typed mutation output should include:

```json
{
  "tool_route": "typed_source_mutation",
  "source_mutation_kind": "write_file|edit_file|apply_patch",
  "changed_paths": ["src/example.py"],
  "pre_snapshot_id": "snapshot:...",
  "post_snapshot_id": "snapshot:...",
  "source_diff_ref": "artifact://.../source-diffs/diff-001.patch",
  "typed_evidence_refs": ["implement-v2-evidence://.../source_tree_mutation/..."],
  "native_transcript_refs": ["native-transcript://.../item/42"]
}
```

### Parser-backed shell metadata

Shell parsing is a helper surface. It should produce a tri-state
`command_classification_result`:

```json
{
  "schema_version": 1,
  "result": "simple|too_complex|unavailable",
  "parser": "tree_sitter_bash|shell_words|none",
  "reason": "parsed_plain_command_sequence|control_flow|parser_not_installed",
  "features": {
    "base_commands": ["git", "make"],
    "connectors": ["&&"],
    "has_redirection": false,
    "has_shell_expansion": false,
    "explicit_shell_interpreter": false,
    "read_search_list_hint": "search|read|list|unknown",
    "process_lifecycle_hint": "foreground|background|yieldable|unknown"
  }
}
```

Allowed consumers:

- command summary;
- read/search/list display hints;
- background/yield defaults;
- exact bridge eligibility checks;
- metrics and debug artifacts.

Approval and sandbox policy may record parser metadata, but
`read_search_list_hint` and `process_lifecycle_hint` may not skip approval,
may not skip sandbox checks, and may not auto-allow execution. The execution
permission path remains authoritative.

Forbidden consumers:

- broad source mutation classification;
- acceptance evidence;
- edit authorization;
- WorkFrame "required next" commands that depend on inferred shell mutation;
- speed credit for command/edit boundary work.

Fail-closed meaning:

- `too_complex` and `unavailable` cannot enable bridge routing;
- they cannot label a command as read-only or source-mutating;
- they can still be run as ordinary process commands if the existing execution
  permission policy allows it;
- they must emit metadata explaining why no shortcut was taken.

### `invalid_tool_contract` route

`invalid_tool_contract` is a first-class route for rejected tool use. It should
be emitted instead of silently reinterpreting a command.

It is not a shell mutation classifier. The route must not be emitted by
pre-exec scanning of arbitrary shell text for possible source writes. If a
shell command is not an explicit edit-shaped execute call, does not declare
source mutation intent, does not violate a verifier/source-write contract, and
does not match a named bridge registry case, it remains a `process_runner`
command. Any unrecognized source write is observed after execution through
terminal snapshot/diff refs.

Emission cases:

- execute-route tool includes explicit edit-shaped arguments such as
  `content`, `content_lines`, `patch`, `patch_lines`, `input` when declared as
  patch input, `edits`, `old_string`, or `new_string`;
- execute-route tool declares source mutation intent through structured fields
  such as `source_mutation`, `source_mutation_intent`,
  `tool_route=typed_source_mutation`, `writes_source=true`, or an equivalent
  provider-neutral intent flag;
- `run_tests` or another verifier-shaped execute tool combines a verifier
  contract with declared source-write intent in the same call;
- `run_command` or an equivalent process runner supplies an execution contract
  that declares source-write work rather than process execution;
- typed mutation tools receive malformed payloads, such as missing target path,
  malformed patch grammar, ambiguous edit hunk, stale precondition, or a
  payload shape that belongs to another typed mutation tool;
- a legacy shell-edit bridge is requested but the bridge registry has no entry;
- a command appears eligible for a named bridge registry entry but fails that
  entry's declared preconditions;
- bridge parser state is `too_complex` or `unavailable`;
- bridge exact-diff computation fails, targets ambiguous paths, or fails
  write-root policy;
- lifecycle tools reference an unknown `command_run_id`;
- `read_command_output` or `poll_command` is used as if it were a source
  mutation route.

Canonical payload shape:

```json
{
  "tool_route": "invalid_tool_contract",
  "declared_tool": "run_command",
  "effective_tool": "none",
  "failure_class": "tool_contract_misuse",
  "failure_subclass": "explicit_edit_shaped_execute_args",
  "reason": "source edits must use typed mutation tools",
  "suggested_tool": "apply_patch|edit_file|write_file|run_command",
  "suggested_use_shell": false,
  "preserved_command_hash": "sha256:...",
  "target_paths": [],
  "bridge_registry_id": "",
  "native_transcript_refs": ["native-transcript://attempt/item/37"]
}
```

The route output must be paired to the original provider call id so the native
transcript remains complete even when execution is rejected.

### Narrow legacy shell-edit bridge

The legacy bridge exists to reduce immediate breakage, not to preserve shell as
an edit API. A bridge is allowed only when the runtime can compute the exact
source diff safely and route it through the typed mutation machinery.

Allowed bridge cases:

- shell-invoked `apply_patch` where the patch body parses and validates against
  the current workspace;

Bootstrap bridge list:

- `shell_invoked_apply_patch`

There are no other initial bridge entries. Additional entries require all of:

- an update to this design document or a successor design document;
- a named trace showing the compatibility need;
- a bridge-registry manifest update with owner, exact parser preconditions,
  exact-diff algorithm, target path constraints, and removal criteria;
- reviewer acceptance that the entry is not rebuilding a broad shell classifier.

The registry manifest should live beside the implementation, for example:

```json
{
  "schema_version": 1,
  "bridges": [
    {
      "id": "shell_invoked_apply_patch",
      "declared_tool": "run_command",
      "effective_tool": "apply_patch",
      "parser_required": "simple",
      "exact_diff_required": true,
      "status": "bootstrap_only"
    }
  ]
}
```

Bridge gate for each command:

- `command_classification_result.result == "simple"`;
- no command substitution, glob-dependent target expansion, unbounded variable
  expansion, shell functions, aliases, heredocs with executable interpolation,
  control flow, pipelines that transform unknown input, or multi-command edits;
- exactly one source mutation plan is produced before mutation;
- all target paths are explicit after workspace-root normalization;
- the planned diff validates against the current pre-snapshot;
- the typed mutation runtime applies the diff, not the shell command;
- the provider-visible result remains paired to the original tool call id and
  records both `declared_tool=run_command` and
  `effective_tool=apply_patch|edit_file|write_file`;
- failure to meet any condition returns a tool result that says to use the
  typed mutation tool. It does not fall back to an inferred shell edit.

Bridge success payload example:

```json
{
  "tool_route": "legacy_shell_edit_bridge",
  "bridge_registry_id": "shell_invoked_apply_patch",
  "declared_tool": "run_command",
  "effective_tool": "apply_patch",
  "changed_paths": ["src/example.py"],
  "source_diff_ref": "artifact://.../source-diffs/turn-4-call-1.patch",
  "pre_snapshot_id": "snapshot:source:turn-4-call-1:pre",
  "post_snapshot_id": "snapshot:source:turn-4-call-1:post",
  "typed_evidence_refs": ["implement-v2-evidence://.../source_tree_mutation/..."],
  "native_transcript_refs": ["native-transcript://attempt/item/37"]
}
```

The bridge may be deleted once prompt/tool behavior no longer depends on it.
It is not a compatibility promise.

### Post-exec source snapshot/diff observer

Every execute-route command should be observable for source side effects.

Before process execution:

- create `pre_snapshot_id` for configured source roots;
- record root set, ignore policy, path count, hash algorithm, and snapshot
  artifact ref;
- if snapshot is too large or unavailable, emit `snapshot_status` with reason
  and continue under the existing process policy.

Source root derivation:

- start with explicit `ToolKernelConfig.source_mutation_roots` when present;
- otherwise use the current workspace root;
- normalize every root with `expanduser` and `resolve(strict=False)`;
- discard roots outside the workspace unless a lane configuration explicitly
  opted them in for source observation;
- snapshot roots never expand `allowed_write_roots`;
- record the final root set in the snapshot artifact.

Ignore and cap policy:

- ignore VCS directories, dependency caches, virtualenvs, package caches,
  common build output directories, and configured artifact roots;
- track source-like suffixes and configured source names, not arbitrary binary
  build outputs;
- cap file count, per-file hash bytes, total path count, diff path count, and
  embedded patch bytes;
- when a cap is hit, preserve `snapshot_status="truncated"` or
  `diff_status="truncated"` with counts and root refs;
- when a root cannot be read, preserve `snapshot_status="partial"` with error
  refs;
- when snapshot support is unavailable, preserve
  `snapshot_status="unavailable"` and do not fabricate source-diff evidence.

After process execution:

- create `post_snapshot_id`;
- compute a bounded source diff against the pre-snapshot;
- record changed paths, added/deleted paths, binary/large-file markers,
  diffstat, and optional bounded patch text;
- attach `source_diff_ref` to the `run_command` tool output;
- if source roots changed through process execution, mark
  `observed_source_side_effect=true`.

Yielded command lifecycle:

- the pre snapshot is taken exactly once, at command start;
- yielded initial results carry `command_run_id`, `pre_snapshot_id`, command
  classification ref, route ref, output ref, and native transcript refs;
- `poll_command` carries the same metadata forward and computes
  `post_snapshot_id` plus source diff only when it observes a terminal command
  state;
- `cancel_command` is terminal for the process lifecycle and must also compute
  post snapshot and source diff when the cancelled process may have run;
- `read_command_output` reads output only. It may echo lifecycle refs but does
  not compute a new snapshot, does not alter source side-effect state, and does
  not create mutation evidence;
- final closeout of still-active commands follows the same terminal observer
  rule as `poll_command`;
- WorkFrame, compact digest, and fastcheck consume only terminal observed
  source side effects for finish blocking and step-shape metrics.

Observer constraints:

- It is a safety net, not a permission system.
- It does not turn execute-route tools into source mutation evidence.
- It can force verifier freshness and WorkFrame attention hints.
- It can block finish if unverified source changes are observed after the last
  typed mutation or verifier.
- It must handle generated build artifacts through root and ignore policy, so
  build outputs do not drown source diffs.

Build-artifact exclusion testing must include at least one command that writes
large build output under ignored artifact roots and one command that writes a
source-like file under a tracked source root. The former must not flood source
diff artifacts; the latter must produce an observed source side effect.

### Native transcript/tool observation preservation

The native transcript remains the source of truth for what the provider emitted
and what the runtime returned.

Rules:

- append exactly one paired output item for each native tool call id;
- never create a second provider-visible call when an effective route differs
  from the declared tool;
- record route, snapshot, diff, command metadata, and typed evidence as sidecar
  refs from the paired output;
- keep `response_transcript.json` and `response_items.jsonl` reproducible;
- make WorkFrame, compact digest, proof manifest, trace summary, and fastcheck
  consume transcript plus sidecars, not independent prompt projections.

Example paired output payload shape:

```json
{
  "tool_name": "run_command",
  "declared_tool": "run_command",
  "effective_tool": "run_command",
  "tool_route": "process_runner",
  "command_classification_ref": "artifact://.../command-classification/turn-4-call-1.json",
  "pre_snapshot_id": "snapshot:source:turn-4-call-1:pre",
  "post_snapshot_id": "snapshot:source:turn-4-call-1:post",
  "source_diff_ref": "artifact://.../source-diffs/turn-4-call-1.patch",
  "native_transcript_refs": ["native-transcript://attempt/item/37"],
  "typed_evidence_refs": []
}
```

## Required Artifacts and Metrics

The implementation should emit these artifacts or equivalent fields in the
existing native artifact tree.

| Artifact or metric | Required fields | Purpose |
| --- | --- | --- |
| `tool_routes.jsonl` | call id, turn id, declared tool, effective tool, route kind, route reason, native transcript refs | Debug route decisions and bridge behavior. |
| `command_classification/*.json` | result `simple|too_complex|unavailable`, parser, reason, features, command hash | Preserve shell metadata without broad mutation classification. |
| `source_snapshots/*.json` | snapshot id, root set, path hashes, ignore policy, status, native transcript refs | Reconstruct pre/post source state for process commands and typed edits. |
| `source_diffs/*.patch` plus `.json` | pre/post snapshot ids, changed paths, diffstat, bounded patch or truncation reason | Observe process side effects and typed mutation exactness. |
| `typed_evidence.jsonl` | source mutation refs, verifier refs, command refs, snapshot ids, diff refs | Feed WorkFrame, resolver, replay, and acceptance gates. |
| `native_observation_index.json` | transcript hash, response item refs, tool result refs, sidecar hashes | Preserve native transcript/tool observation authority. |
| `command_lifecycle.jsonl` | command run id, start call id, poll/cancel/read refs, terminal result ref, snapshot ids | Carry yielded command observer state across lifecycle tools. |
| `legacy_shell_edit_bridges.json` | bridge id, declared tool, effective tool, parser preconditions, exact-diff rule, trace refs | Keep compatibility bridge scope explicit and reviewable. |
| proof manifest fields | command classification count, too-complex count, unavailable count, process side-effect count, typed mutation count, bridge count | Make regressions visible in fastcheck and reviews. |

Minimum per tool result metrics:

- `command_classification_result`
- `tool_route`
- `declared_tool`
- `effective_tool`
- `bridge_registry_id` when `tool_route=legacy_shell_edit_bridge`
- `pre_snapshot_id`
- `post_snapshot_id`
- `snapshot_status`
- `diff_status`
- `source_diff_ref`
- `native_transcript_refs`
- `typed_evidence_refs`

## Phase Plan

Phase dependency ordering:

- Phase 0 is required. No later implementation phase may start until its
  anti-drift outputs exist.
- Phase 1 depends on Phase 0 because route metadata must name the old paths it
  is replacing.
- Phase 2 can land before Phase 4, but until Phase 4 lands, observed shell
  side effects are warnings only. Production safety for shell side effects
  requires Phase 4.
- Phase 3 depends on Phase 1 because parser metadata must be attached to route
  artifacts.
- Phase 4 depends on Phase 1 and should run after or alongside Phase 3.
- Phase 5 depends on Phase 1, Phase 2, and Phase 3. A bridge cannot exist
  without route metadata, typed mutation runtime, and parser tri-state.
- Phase 6 depends on Phases 1-5 and removes or quarantines replaced live paths.
- Phase 7 depends on all earlier phases and blocks speed proof until the
  pre-speed validation order is green.

Implementation ownership and review plan:

- Phase 0-1 are single-owner and must be implemented serially by the main
  Codex session. They freeze the interface:
  - old classifier deletion map;
  - canonical `tool_route`;
  - `process_lifecycle`;
  - route decision artifact;
  - narrow `invalid_tool_contract` definition.
- Phase 2-4 are partially parallelizable only after Phase 1 closes:
  - Phase 2 owns the typed mutation route;
  - Phase 3 owns parser metadata and tri-state shell metadata;
  - Phase 4 owns snapshot/diff observer and yielded command lifecycle.
  These phases may use separate `orchestrate-build-review` workflows if their
  write sets are kept disjoint and each builder receives the Phase 1 enum and
  schema as fixed input.
- Phase 5 is serial or high-review only. The legacy shell-edit bridge is the
  highest-risk classifier regrowth point, so either the main Codex session owns
  it directly or any builder output receives codex-ultra review plus
  claude-ultra review before merge.
- Phase 6-7 are serial integration/validation phases:
  - Phase 6 deletes or quarantines old classifier paths;
  - Phase 7 runs replay, dogfood/emulator, fastcheck, 10 minute step-shape, and
    speed proof only after the preceding artifacts are green.

Review rule:

- When the main Codex session implements a phase directly, run codex-ultra code
  review before commit.
- For difficult or boundary-sensitive phases, especially Phase 4 and Phase 5,
  add claude-ultra review before commit.
- Do not start broad measurement, speed proof, or new command-classifier polish
  while a phase close gate is still open.

### Phase 0: Required Anti-Drift Baseline and Deletion Map

Intent: stop investing in broad regex/shlex mutation-classifier polish, capture
the current boundary failures as baseline evidence, and produce the concrete
deletion/quarantine map required by Phase 6. This phase is a required
anti-drift checkpoint. It has no runtime behavior change.

Implementation slice:

- Mark current broad shell mutation classifier paths as deprecated in
  diagnostic metadata or a design-owned deletion map.
- Add a tiny diagnostic baseline that records how many decisions depend on old
  mutation-classifier logic.
- Identify the current prompt/tool specs that imply shell may create or patch
  source.
- Create `command_edit_boundary_deletion_map.md` or equivalent artifact naming
  each entry point, action, owner phase, replacement, and test gate.
- Do not change runtime behavior yet.

Minimum deletion/quarantine map:

| Current entry point | Action | Replacement |
| --- | --- | --- |
| `src/mew/implement_lane/exec_runtime.py::_run_tests_source_mutation_misuse` | quarantine/delete from live native route after typed route and observer gates | `invalid_tool_contract` route plus typed mutation tools |
| `src/mew/implement_lane/exec_runtime.py::_run_command_source_mutation_verifier_compound_misuse` | quarantine/delete from live native route | execute-route process runner plus observer finish block |
| `src/mew/implement_lane/exec_runtime.py::_run_command_source_patch_misuse` | replace | bridge registry miss or `shell_invoked_apply_patch` exact bridge |
| `src/mew/implement_lane/exec_runtime.py::_run_command_source_creation_shell_surface_misuse` | quarantine/delete from live native route | `invalid_tool_contract` route for edit-shaped execute attempts |
| `src/mew/implement_lane/exec_runtime.py::_run_command_source_exploration_shell_surface_misuse` | narrow to read/search/list display metadata only or delete | parser metadata and read/search/list tools |
| `src/mew/implement_lane/exec_runtime.py::_source_like_mutation_paths` and shell write-path helpers | quarantine/delete from live native route except bridge exact-diff internals | source snapshot/diff observer and bridge registry |
| `src/mew/implement_lane/v2_runtime.py::_is_deep_runtime_prewrite_source_mutation_attempt` | delete/quarantine from live native route | typed mutation route metrics |
| `src/mew/implement_lane/v2_runtime.py::_shell_command_may_mutate_source_tree` and shell write-path helpers | delete/quarantine from live native route | parser metadata plus observer |
| `src/mew/implement_lane/v2_runtime.py::_source_patch_shell_repair_from_result` | replace | `invalid_tool_contract` recovery hint or bridge registry result |
| `src/mew/implement_lane/v2_runtime.py::_unaccounted_source_tree_mutation_block` | keep only as observer consumer | terminal source side-effect refs from Phase 4 |

Close gate:

- A reviewer can point to the exact old classifier entry points to delete or
  quarantine later.
- Baseline metrics include at least: shell mutation classifier hit count,
  `run_command` source side-effect count if detectable, typed mutation count,
  and existing artifact refs.
- The deletion map includes explicit tests proving live native routes no longer
  call deleted/quarantined classifier entry points after Phase 6.
- No `src/` behavior change occurs in this phase beyond diagnostic-only
  metadata, if implemented.

### Phase 1: Route Decision and Artifact Schema

Intent: introduce a provider-neutral route vocabulary before changing behavior.

Implementation slice:

- Add `ToolRouteDecision` or equivalent using the canonical `tool_route` enum
  defined in Target Architecture. Do not duplicate or locally subset the enum.
- Add `CommandClassificationResult` with exactly:
  `simple`, `too_complex`, `unavailable`.
- Define sidecar writers for route decisions, command classification,
  snapshots, diffs, native transcript refs, and typed evidence refs.
- Thread route refs through tool output payloads without changing execution.

Close gate:

- Unit tests prove every native tool call emits one route decision.
- Unit tests cover route decisions for `poll_command`, `cancel_command`, and
  `read_command_output`, and assert they use `process_lifecycle`.
- The canonical route enum is exactly the design list unless a successor design
  changes it.
- Route artifacts contain declared/effective tool names and native transcript
  refs.
- There is no route kind named `shell_source_mutation`,
  `inferred_shell_edit`, or equivalent.
- Native transcript pairing still validates after route metadata is added.

### Phase 2: Typed Source Mutation as the Only Edit Route

Intent: make source mutation tools produce exact diffs and typed evidence.

Implementation slice:

- Ensure `write_file`, `edit_file`, and `apply_patch` all build pre/post
  source snapshots and exact diff refs.
- Move `apply_patch` toward provider-native/freeform where supported, with
  `patch_lines` or similar structured fallback for JSON-only providers.
- Return structured recovery payloads for parse failure, anchor miss,
  ambiguous edit, path policy failure, and stale snapshot.
- Update prompt/tool descriptions to say source-like writes belong to typed
  mutation tools, not `run_command`.

Close gate:

- Focused unit tests cover successful write, edit, patch, parse failure,
  anchor miss, stale precondition, and path policy rejection.
- Each successful source mutation has a typed evidence ref and source diff ref.
- `apply_patch` parse errors are paired tool outputs, not model-response parse
  failures.
- No live source mutation acceptance depends on shell command text.
- Before Phase 4 lands, shell side effects discovered by old mechanisms are
  logged as warnings only and must not be treated as production-safe observer
  blocking. Production safety for process side effects requires Phase 4.

### Phase 3: Parser-Backed Shell Metadata Only

Intent: replace broad mutation inference with conservative shell metadata.

Implementation slice:

- Add or adapt parser-backed shell metadata with results:
  `simple`, `too_complex`, `unavailable`.
- For `simple`, extract only bounded metadata such as base commands,
  connectors, shell interpreter, redirection, read/search/list hints, and
  lifecycle hints.
- For `too_complex` and `unavailable`, emit reason and deny all shortcut
  consumers.
- Wire metadata to summary, approval, sandbox, background/yield hints, and
  bridge eligibility only.

Close gate:

- Tests prove complex shell never enables bridge or typed mutation evidence.
- Tests prove parser unavailable does not default to read-only or edit-safe.
- Command metadata can summarize simple read/search/list commands.
- Tests prove read/search/list and lifecycle hints affect only summary,
  display, and background/yield defaults, not approval or sandbox bypass.
- Review confirms no large command mutation allowlist was introduced.

### Phase 4: Execute-Route Process Runner Boundary and Diff Observer

Intent: make execute-route tools observable while keeping them semantically
process-only.

Implementation slice:

- Strip or reject source mutation arguments from `run_command`, `run_tests`,
  and equivalent execute-route tools.
- Add pre/post source snapshot capture around process execution.
- Add command lifecycle metadata so yielded commands carry pre snapshot refs
  until a terminal poll/cancel/closeout computes post snapshot and diff refs.
- Add bounded source diff artifacts for changed source roots.
- Attach observer refs to execute-route paired outputs.
- Define root derivation, ignore policy, caps, and fallback statuses in the
  snapshot policy module home.
- Teach WorkFrame/compact digest to surface observed source side effects as
  attention hints and verifier freshness blockers, not accepted edits.

Close gate:

- Unit tests prove `run_command` and `run_tests` reject edit-shaped args.
- A command that modifies a tracked source file records source side-effect
  metadata and diff refs.
- The same command does not produce typed source mutation evidence.
- A yielded command preserves pre snapshot metadata across `poll_command`,
  `cancel_command`, `read_command_output`, and final closeout.
- Terminal `poll_command`, `cancel_command`, or closeout computes post snapshot
  and source diff refs.
- `read_command_output` does not compute a new snapshot and cannot create
  source mutation evidence.
- Finish/resolver tests block completion when an unverified observed source
  side effect occurs after the latest verifier.
- Snapshot failure is visible in artifacts and does not silently disable
  process execution policy.
- Build-artifact exclusion tests prove ignored output roots do not flood source
  diffs while tracked source-like files still produce observer records.
- Fastcheck consumes terminal observed source side effects from native
  transcript plus sidecars.

### Phase 5: Narrow Legacy Shell-Edit Bridge

Intent: support only exact, safe shell-edit compatibility paths.

Implementation slice:

- Implement the bridge registry with exactly one bootstrap entry:
  `shell_invoked_apply_patch`.
- Do not add any other bridge in the same commit.
- Any later bridge entry must cite trace evidence, update the registry
  manifest, update this design or a successor design, and include removal
  criteria.
- Route bridge results through typed mutation runtime and typed evidence.
- Return `invalid_tool_contract` for bridge misses with recovery hints:
  `use apply_patch`, `use edit_file`, or `use write_file`.

Close gate:

- Bridge tests cover success, invalid patch, ambiguous path, complex command,
  parser unavailable, and policy rejection.
- The bridge manifest contains only `shell_invoked_apply_patch` at bootstrap.
- Bridge success records `declared_tool=run_command`,
  `effective_tool=apply_patch|edit_file|write_file`, `tool_route` bridge,
  `bridge_registry_id`, source diff ref, and typed evidence refs.
- Bridge failure never executes the original shell edit as an inferred source
  mutation.
- Reviewer confirms the bridge registry did not grow beyond the documented
  bootstrap entry without trace evidence and design approval.

### Phase 6: Migration and Deletion

Intent: remove old live contracts without preserving backward compatibility.

Implementation slice:

- Delete or quarantine old shell mutation classifier paths from live
  `implement_v2`.
- Apply the Phase 0 deletion map and record which entries were deleted,
  quarantined for historical replay, or retained only as observer consumers.
- Update native prompt/tool specs and replay fixtures to the new boundary.
- Update dogfood/emulator expectations for route, snapshot, diff, and evidence
  artifacts.
- Keep old artifact readers only where needed for explicit historical replay.

Close gate:

- No production native path calls the old mutation classifier.
- Tests fail if live native routes call the deleted/quarantined
  `exec_runtime.py` or `v2_runtime.py` classifier entry points named in the
  Phase 0 map.
- Retained observer consumers accept only terminal source side-effect refs from
  Phase 4 artifacts, not shell text inference.
- Existing new fixtures pass without compatibility flags.
- Old model-visible instructions that suggested shell edits are absent.
- Historical replay compatibility, if retained, is explicitly named and cannot
  be selected by live native runs.

### Phase 7: Validation Before Speed

Intent: prove the boundary locally before spending time on broad speed proofs.

Validation order:

1. Focused unit tests for route decisions, typed mutations, parser metadata,
   bridge conditions, snapshots, diffs, and transcript pairing.
2. Replay checks against existing native transcript artifacts and saved Codex /
   Claude reference traces where normalizers exist.
3. Dogfood or emulator runs that exercise process-only commands, typed edits,
   yielded command lifecycle, observed shell side effects, and bridge
   success/failure.
4. Micro next-action or HOT_PATH fastcheck proving compact digest and WorkFrame
   consume route/diff/evidence refs correctly.
5. Exactly one 10 minute step-shape diagnostic once the fast path is green.
6. Speed proof only after the diagnostic shows the expected step shape.

Close gate:

- Unit tests are green.
- Replay proves route, snapshot, diff, evidence, and transcript artifacts are
  deterministic.
- Emulator/dogfood demonstrates at least one typed edit, one pure process
  command, one observed source side effect, and one bridge rejection or bridge
  success.
- Fastcheck reports native transcript pairing, route metadata, source diff
  observation, command lifecycle observer state, and typed evidence observation
  as green.
- Fastcheck or replay proves terminal observed source side effects are consumed
  by WorkFrame/compact digest and nonterminal yielded state is not treated as a
  completed source side effect.
- 10 minute step-shape shows fewer noisy verifier/repair loops or an explained
  non-regression before any speed proof begins.

## Migration Approach

No backward compatibility is required.

Allowed breaking changes:

- `run_command` no longer accepts or honors edit-shaped source mutation args.
- `run_tests` and equivalent execute-route tools no longer accept source
  mutation mixed into verifier commands.
- Shell commands that previously mutated source may now return a recovery hint
  asking for `write_file`, `edit_file`, or `apply_patch`.
- Bridge compatibility starts and may remain limited to shell-invoked
  `apply_patch`.
- Old live model-JSON source mutation routes may be deleted or quarantined.
- Artifact schemas may change as long as native transcript authority,
  sidecar refs, and fastcheck/replay are updated in the same phase.
- Old replay fixtures may be migrated, regenerated, or explicitly marked
  historical.

Temporary feature flags are allowed for rollout mechanics, but not as a
compatibility contract. A flag must have an owner phase and deletion gate.

## Acceptance Signals

The redesign is working when:

- the model uses `run_command` and `run_tests` for process probes/builds/tests
  and typed tools for edits;
- execute-route results preserve source side-effect diffs without claiming
  typed mutation evidence;
- yielded commands carry pre snapshot refs through lifecycle tools and produce
  post snapshot/diff refs only on terminal state;
- complex shell commands are still runnable under execution policy but never
  gain inferred edit semantics;
- bridge events are rare, exact, and visible;
- native transcript artifacts remain the authority for every call/output pair;
- WorkFrame and compact digest cite route, diff, snapshot, and typed evidence
  refs instead of re-describing shell text;
- pre-speed checks catch boundary drift before 10 minute diagnostics.

## Risks

- Generated source from build scripts may appear as source side effects. Mitigate
  with explicit source roots, ignore policy, and artifact classification.
- Source root defaults may be too broad or too narrow. Mitigate with explicit
  `source_mutation_roots`, recorded root manifests, and root/ignore replay
  tests.
- Yielded command closeout can lose observer state if lifecycle metadata is not
  carried across polls or cleanup. Mitigate with command lifecycle artifacts and
  fastcheck coverage.
- Snapshot/diff cost may be high on large trees. Mitigate with bounded roots,
  hash manifests, path caps, truncation metadata, and opt-in deeper diffs.
- Diff artifacts may leak large generated files into model context. Mitigate by
  storing full refs sidecar-only and projecting bounded summaries.
- Bridge scope may expand under pressure. Mitigate with per-bridge close gates
  and a manifest that reviewers can diff.
- Parser-backed metadata can become a classifier by another name. Mitigate by
  limiting result values and forbidding mutation route consumers.
- Observed shell side effects might be useful enough that users expect them to
  count as edits. Mitigate by exposing the diff clearly while requiring typed
  repair or fresh verification before finish.
- No backward compatibility can break historical tests. Mitigate by splitting
  live native tests from historical replay tests.

## Non-Goals

- No huge shell mutation classifier.
- No attempt to emulate full Bash semantics.
- No source edit API through `run_command`.
- No source edit API through `run_tests`, `poll_command`,
  `read_command_output`, `cancel_command`, or equivalent execute lifecycle
  tools.
- No broad conversion of arbitrary shell commands into patches.
- No task-specific MIPS, VM, Terminal-Bench, or benchmark-solver heuristic.
- No weakening of approval, sandbox, write-root policy, verifier freshness, or
  deterministic finish resolution.
- No replacement of native transcript authority with WorkFrame, prompt text, or
  model-authored summaries.

## Reviewer Checklist

- [ ] The design keeps `run_command` as process runner only.
- [ ] The same process-runner boundary applies to `run_tests` and equivalent
      execute-route tools.
- [ ] `poll_command`, `cancel_command`, and `read_command_output` are lifecycle
      routes only.
- [ ] All model-requested source mutation goes through typed mutation tools or
      an exact bridge routed through typed mutation runtime.
- [ ] Shell parser output is limited to `simple`, `too_complex`, and
      `unavailable`.
- [ ] `too_complex` and `unavailable` fail closed for bridge and mutation
      shortcuts.
- [ ] Legacy bridge conditions require exact diff computation before mutation.
- [ ] The initial bridge registry contains only shell-invoked `apply_patch`.
- [ ] Post-exec source snapshot/diff observation is present for terminal
      execute-route results.
- [ ] Yielded command lifecycle carries pre snapshot metadata and computes post
      snapshot/diff refs only on terminal state.
- [ ] Source root derivation, ignore policy, caps, and fallback statuses are
      specified and testable.
- [ ] Observed shell side effects do not become typed mutation evidence.
- [ ] Native transcript call/output pairing is preserved.
- [ ] Metrics include command classification result, tool route, source diff,
      snapshot ids, native transcript refs, and typed evidence refs.
- [ ] Validation runs UT, replay, dogfood/emulator, micro next-action or
      fastcheck before the 10 minute step-shape diagnostic.
- [ ] Speed proof is blocked until the step-shape diagnostic passes or has an
      explicit non-regression rationale.
- [ ] Migration plan does not promise backward compatibility.
- [ ] Phase 0 is required and includes a deletion/quarantine map for current
      classifier entry points.
- [ ] Phase 6 tests prove live native routes no longer call deleted or
      quarantined classifier entry points.
- [ ] The design does not introduce a new huge shell classifier under another
      name.
