# Design 2026-05-05 - M6.24 Active Compatibility Frontier v0

Status: design proposal for review.

Scope: add a generic active repair-frontier state for implementation-lane
compatibility and repository-test-tail failures. This is a design-only note and
does not authorize source edits by itself.

## Inputs Reviewed

- `ROADMAP_STATUS.md`
- `docs/M6_24_DOSSIER_BUILD_CYTHON_EXT_2026-05-03.md`
- `docs/M6_24_REFERENCE_TRACE_BUILD_CYTHON_EXT_2026-05-05.md`
- `docs/REVIEW_2026-05-05_CODEX_FRONTIER_LOOP_PATTERNS.md`
- `docs/REVIEW_2026-05-05_CLAUDE_CODE_FRONTIER_LOOP_PATTERNS.md`
- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`
- `docs/DESIGN_2026-05-03_M6_24_EXECUTION_CONTRACT.md`
- `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`
- `src/mew/work_session.py`
- `src/mew/work_loop.py`
- `src/mew/commands.py`
- `src/mew/dogfood.py`
- `src/mew/terminal_bench_replay.py`
- `src/mew/agent_trace.py`

## Problem

M6.24 is currently in `improvement_phase` for the scoped
`software-engineering,coding` Terminal-Bench cohort. The active gap is
`verified_sibling_repair_frontier_not_exhausted`, with the current subtype
`repository_test_tail_frontier_not_exhausted_before_wall_timeout`.

The latest active evidence shows that mew can reach real build, install,
import/load, and partial behavior proof. It can also observe the bottom failure
family: verifier output, stack traces, search anchors, failing test names, and
source locations become visible in the work session. The miss is what happens
next. Mew spends expensive time rediscovering setup facts, repeating broad
build/test loops, or accepting finish evidence that proves only import/path
loadability. It does not reliably close the visible sibling repair frontier
before wall timeout or finish.

This is a speed and scoring problem, not just a prompt wording problem:

- Current-head scoped evidence remains `0/1` even after earlier plumbing
  repairs moved the task past broad setup blockers.
- Reference agents passed the same active gap in about five minutes. The
  normalized traces record Codex at `326.275s` total with first edit at
  `16.631s` and first verifier at `26.773s`; Claude Code at `309.230s` total
  with first edit at `128.681s` and one late verifier at `291.216s`.
- Both reference traces use the same conceptual move: observe a same-family
  verifier/runtime failure, search sibling anchors across the repository, apply
  a compact related edit slice, then run targeted and broader proof.
- Mew already sees much of that evidence, but loses leverage because the
  evidence is not promoted into explicit state with deterministic action
  obligations.

The target repair is therefore:

```text
M6.24 -> selected gap class -> implementation/tiny profile/state guard ->
UT/replay/dogfood/emulator -> exactly one same-shape speed_1
```

## Architecture Fit

This stays inside the existing implementation/tiny lane. It does not introduce
a new authoritative lane, a benchmark specialist, a write-capable helper, or a
second planner. The production path remains:

```text
model action -> work_loop normalization/guards -> commands/tool execution ->
work_session evidence/resume -> acceptance/done gate -> report/replay/dogfood
```

The change is a small typed state and policy layer inside that path. Existing
surfaces already point in this direction:

- `build_verifier_failure_repair_agenda()` extracts verifier error lines,
  source locations, symbols, sibling search queries, runtime contract gaps, and
  a suggested next action.
- `build_search_anchor_observations()` records successful search anchors that
  have not yet been converted to narrow reads.
- `active_work_todo` records a scoped edit frontier with cached windows.
- `active_rejection_frontier` records reviewer rejection state and prevents
  reusing the wrong patch family.
- `compact_resume_for_prompt()` already preserves several failure/reentry
  objects through prompt compaction.
- `run_m6_24_repository_test_tail_emulator_scenario()` already detects
  repository-test-tail failures and finish false positives from saved Harbor
  artifacts.

The missing piece is that these are separate hints. v0 should consolidate them
into one explicit compatibility frontier that is the source of truth for
action-selection and finish gates.

## Definition

`ActiveCompatibilityFrontier` is session-local, typed repair state for a
currently open same-family verifier/runtime/repository-test-tail failure.

It is not:

- a prompt-only instruction;
- a task-specific recipe;
- a list of known compatibility symbols;
- a replacement for `active_work_todo`, `active_rejection_frontier`,
  `ExecutionContract`, `CommandEvidence`, or the acceptance done gate.

It is the bridge between observed failure evidence and the next few actions:
search, read, edit, cheap verifier, broad verifier, or finish.

Recommended ownership:

- Store the canonical current frontier on the work session, for example
  `session["active_compatibility_frontier"]`.
- Project the same object, compacted, through `work_session.resume`.
- Render only a compact line in `format_work_session_resume()`.
- Keep raw logs and large outputs behind evidence refs, not copied into the
  frontier.

## Data Model

The v0 model can start as dictionaries with normalizers. A later patch may move
it into a dedicated module or dataclass once tests pin the contract.

```json
{
  "schema_version": 1,
  "id": "compat-frontier-<session>-<ordinal>",
  "status": "open",
  "created_at": "iso8601-or-null",
  "updated_at": "iso8601-or-null",
  "failure_signature": {},
  "evidence_refs": [],
  "anchors": [],
  "sibling_candidates": [],
  "hypotheses": [],
  "patch_batch": {},
  "verifier_history": [],
  "closure_state": {},
  "compact_summary": {}
}
```

### `failure_signature`

Purpose: identify whether a later failure is the same family, a narrower
version, a moved family, or a new frontier.

Minimum fields:

```json
{
  "schema_version": 1,
  "fingerprint_version": "active_compatibility_frontier_failure_signature_v1",
  "kind": "verifier_failure|runtime_failure|repository_test_tail|finish_false_positive",
  "fingerprint": "stable-hash",
  "family_key": "less-strict-stable-hash",
  "source_tool_call_id": 12,
  "command_evidence_ref": {"kind": "command_evidence", "id": 7},
  "tool": "run_tests",
  "command_shape": "normalized command without volatile paths",
  "cwd_shape": "normalized cwd or repository root marker",
  "exit_class": "nonzero|timeout|tool_failed|finish_with_external_failure",
  "error_fingerprint": "normalized top error/test/stack facts",
  "failing_tests": ["test_or_verifier_names_without_task_recipes"],
  "runtime_component_kind": "native_module|shared_library|plugin|executable|interpreter|simulator|custom_runtime|unknown",
  "platform_facts": ["python-major-minor", "runtime-name", "os-family"]
}
```

The fingerprint must be generic. It may include normalized missing-symbol,
import, attribute, path, stack frame, failing test, or command facts. It must
not encode benchmark names, package names, or a fixed compatibility table as
special cases.

### Fingerprint and Family Transition Contract

v0 should compute two hashes from deterministic canonical JSON:

- `fingerprint`: strict enough to distinguish a concrete observed failure.
- `family_key`: looser, used to decide whether a later failure belongs to the
  same repair frontier.

Both use:

```text
canonical_json = json.dumps(core, sort_keys=True, separators=(",", ":"))
hash = sha256((fingerprint_version + "\n" + canonical_json).encode()).hexdigest()
```

The implementation may store full hashes and render a short prefix. The hash
contract must be versioned. Any change in included fields increments
`fingerprint_version`.

Strict `fingerprint` inputs:

- `schema_version` and `fingerprint_version`;
- `kind`;
- normalized `tool`;
- normalized `command_shape`;
- normalized execution-contract fields when present:
  `purpose`, `stage`, `proof_role`, `acceptance_kind`, and `risk_class`;
- `exit_class`;
- normalized top exception/error class names;
- normalized missing import/attribute/symbol tokens;
- sorted normalized failing test names;
- sorted normalized top stack frame identities;
- `runtime_component_kind`;
- sorted `platform_facts` that materially affect compatibility, such as
  runtime major/minor or operating-system family.

Loose `family_key` inputs:

- `kind`, except that `finish_false_positive` MUST use the family key computed
  from the external verifier or Harbor failure evidence it exposes. If that
  evidence ref is absent, v0 must not create a blocking finish-false-positive
  frontier; it should record a weak recovery warning instead.
- normalized execution stage/proof role, when present;
- normalized top exception/error class names;
- normalized missing import/attribute/symbol tokens;
- sorted failing test names with volatile parametrization removed;
- `runtime_component_kind`;
- the first stable repository-relative source/test frame, if one exists.

Excluded from both hashes:

- tool call ids, command evidence ids, model turn ids, session ids, trial ids,
  timestamps, durations, token counts, and wall-clock budgets;
- absolute temp paths, sandbox roots, Harbor job ids, random suffixes, cache
  directories, and usernames;
- full stdout/stderr text, output order, and clipped-output boundaries;
- line numbers unless the only stable failure fact is a line-addressed syntax or
  parse error;
- package, benchmark, or task names unless they appear as ordinary observed
  file/module/test evidence in the current transcript. They must never be
  hard-coded into extraction rules.

Normalization rules:

- Replace absolute working directories with `<repo>` when the path is under the
  current repository or allowed work root.
- Replace external temp/sandbox paths with `<tmp>`.
- Normalize path separators to `/`.
- Lowercase error class labels and tool names, but preserve case-sensitive
  symbols in a separate normalized token list.
- Strip common pytest/unittest parametrization ids and volatile counters from
  test names while keeping the test function or case identity.
- Collapse whitespace and quote variants in error lines before extracting
  tokens.
- Sort token lists and remove duplicates.
- Keep at most the top stable stack frames needed for matching. Prefer
  repository-relative or artifact-relative frames over installed-path frames.

Family transition algorithm:

```text
if no previous active frontier:
  transition = "new"
elif new.family_key == previous.failure_signature.family_key:
  transition = "same"
elif category_overlap(new, previous).narrower:
  transition = "narrower"
elif category_overlap(new, previous).moved:
  transition = "moved"
else:
  transition = "new"
```

`category_overlap()` is not a union-level token subset. It compares token
categories independently:

- `error_tokens`: exception/error classes and normalized assertion/error
  labels;
- `missing_symbol_tokens`: missing import, missing attribute, unresolved symbol,
  undefined symbol, and equivalent absent-entrypoint tokens;
- `failing_test_tokens`: normalized failing test or verifier case identities;
- `stack_anchor_tokens`: repository-relative source/test frames or
  generated-to-source mapped frames;
- `component_tokens`: runtime component kind plus artifact identity when
  positively detected;
- `platform_tokens`: runtime major/minor and OS family facts.

Primary overlap categories are `error_tokens`, `missing_symbol_tokens`,
`failing_test_tokens`, and `stack_anchor_tokens`. `component_tokens` and
`platform_tokens` are secondary. Platform facts and `runtime_component_kind`
alone do not prove same-family or moved-family overlap.

`category_overlap().narrower` is true when at least one primary category
overlaps, no primary category contradicts, and one or more primary categories
have fewer current failing tokens than the previous signature. Missing
categories are ignored when they were not observed in one side. For example,
one remaining failing test from the same error category can be narrower even if
the union of all tokens is not a strict subset.

`category_overlap().moved` is true when at least one primary category overlaps
and either the primary stack/source anchor, command stage, proof role, or
behavior surface moved. Moved requires a primary-category overlap; a shared
runtime kind or platform fact is insufficient.

A transition of `same` keeps the frontier open and appends verifier history.
`narrower` keeps the frontier open, marks candidates that no longer fail as
`verified`, and updates `closure_state.next_action`. `moved` supersedes the old
closure state but preserves evidence refs and opens a new candidate set. `new`
closes or defers the old frontier with a reason and opens a new frontier.

Generic unit-case examples:

- Same: the same targeted verifier exits nonzero with the same exception class
  and failing test, but the absolute temp path and tool call id changed.
- Narrower: after a patch, four related failing tests become one failing test
  with the same error token and runtime component kind.
- Moved: a load proof now succeeds, but the first behavior invocation for the
  same component fails at a different source anchor with overlapping runtime
  tokens.
- New: an acquisition/setup timeout is replaced by an unrelated behavior
  assertion failure with no shared strong token.

### Runtime Component Kind Detection

`runtime_component_kind` must come from positive evidence in the work session,
not from task, package, benchmark, or project names.

Generic signals:

- `native_module`: compiled extension suffix or loader path in command output
  such as `.so`, `.pyd`, `.dylib`, or `.dll` tied to a language import/load
  command; import machinery traceback for a compiled extension; extension load
  errors from a runtime such as undefined symbol, wrong architecture, or module
  initialization failure.
- `shared_library`: dynamic loader/linker output; `ctypes`, `cffi`, `dlopen`,
  `ffi.load`, or equivalent FFI load traces; linker errors naming a shared
  object; runtime search-path failures.
- `plugin`: a host application or framework loading a plugin/entrypoint;
  plugin manifest or entrypoint discovery in command output; loader failures
  that identify a plugin path or registered entrypoint.
- `executable`: subprocess or shell execution of a built/generated binary;
  `exec`, spawn, permission, shebang, `exec format`, command-not-found, or
  process exit evidence tied to that artifact.
- `interpreter`, `simulator`, or `custom_runtime`: a harness command runs a
  bytecode/program/image/ROM/model through a custom runtime and the failure
  reports runtime coordinates such as opcode, syscall, program counter,
  register, frame, or expected generated artifact.
- `unknown`: no positive runtime-component signal. `unknown` must not trigger
  the runtime-component finish gate by itself, though other frontier obligations
  may still block broad verifier or finish.

When multiple signals appear, choose the most specific component involved in
the failing verifier. Store the evidence refs that justify the classification.

### `evidence_refs`

Purpose: keep the frontier auditable without copying raw logs into every prompt.

Allowed refs:

- `{"kind": "command_evidence", "id": N}` from execution-contract evidence;
- `{"kind": "tool_call", "id": N}` for older command/tool surfaces;
- `{"kind": "work_report_step", "index": N}`;
- `{"kind": "verifier_stdout", "path": "..."}`;
- `{"kind": "harbor_result", "path": "..."}`;
- `{"kind": "normalized_trace", "path": "..."}`;
- `{"kind": "resume_key", "key": "verifier_failure_repair_agenda"}`;
- `{"kind": "dogfood_fixture", "path": "..."}`.

Each ref should include a short `summary` and optional `line_refs` when the
source can be line-addressed. The canonical raw output remains in the original
artifact.

### `anchors`

Purpose: describe concrete places where the family is visible or where the next
action should inspect before editing.

Fields:

```json
{
  "id": "anchor-1",
  "kind": "stack_frame|source_location|search_query|search_match|test_name|build_config|generated_to_source_map",
  "subject": "path, symbol, test, command, or query",
  "path": "relative/or/artifact/path",
  "line": 123,
  "query": "literal search term",
  "source_event": {"kind": "tool_call", "id": 12},
  "read_status": "unread|read|stale|not_needed",
  "freshness": {"tool_call_id": 14, "window_sha1": "sha1:..."},
  "evidence_refs": []
}
```

Search results become anchors only when they are successful or diagnostically
useful. A successful search anchor that has not been read should block repeated
same-search rediscovery and should prefer the narrow `read_file` suggested by
`search_anchor_observations`.

### `sibling_candidates`

Purpose: make the visible same-family repair set explicit.

Fields:

```json
{
  "id": "candidate-1",
  "kind": "file|symbol|test|config|generated_source|runtime_entrypoint",
  "subject": "short stable label",
  "path": "relative path when known",
  "anchors": ["anchor-1"],
  "reason": "why this belongs to the same family",
  "status": "unexplored|read|anchored|edited|verified|rejected|deferred|blocked",
  "rejection_reason": "",
  "last_updated_turn": 17,
  "evidence_refs": []
}
```

Candidates are not required to be exhaustive across the whole world. They must
cover the visible sibling set discovered from the current evidence before mew
spends another broad build/test loop.

### `hypotheses`

Purpose: track the compact causal repair plan without relying on prose memory.

Fields:

```json
{
  "id": "hypothesis-1",
  "summary": "same-family compatibility repair remains open in visible siblings",
  "status": "open|patched|rejected|verified|superseded",
  "candidate_ids": ["candidate-1"],
  "expected_effect": "cheap verifier changes or clears the failure signature",
  "required_next_action": "search|read|edit|cheap_verify|broad_verify|defer|finish_blocked",
  "blocking_evidence_refs": [],
  "updated_at": "iso8601-or-null"
}
```

### `patch_batch`

Purpose: connect applied or proposed edits to the frontier.

Fields:

```json
{
  "id": "patch-batch-1",
  "status": "not_started|drafted|pending_approval|applied|rejected|rolled_back",
  "candidate_ids": ["candidate-1", "candidate-2"],
  "tool_call_ids": [15, 16],
  "paths": ["src/example.py", "tests/test_example.py"],
  "diff_refs": [],
  "read_token_refs": [],
  "evidence_refs": [],
  "verifier_history_ids": [],
  "summary": "bounded same-family edit slice",
  "must_verify_with": ["cheap-targeted-command"],
  "latest_rejection_frontier_id": ""
}
```

The write barrier remains serial. The frontier may encourage a batch of related
edits, but it must not create concurrent write races.

### `verifier_history`

Purpose: prevent repeated broad verification while the same family remains
open, and provide proof when it is safe to escalate.

Fields:

```json
{
  "id": "verifier-1",
  "kind": "static_check|behavior_smoke|targeted_test|repository_tail|broad_build|external_verifier",
  "scope": "cheap|targeted|broad",
  "command_evidence_ref": {"kind": "command_evidence", "id": 9},
  "tool_call_id": 18,
  "exit_code": 1,
  "signature_fingerprint": "stable-hash",
  "family_changed": false,
  "closed_candidate_ids": [],
  "opened_candidate_ids": [],
  "notes": "short bounded summary"
}
```

### `closure_state`

Purpose: make finish and broad verifier readiness deterministic.

Fields:

```json
{
  "state": "open|search_needed|read_needed|edit_needed|cheap_verify_needed|broad_verify_ready|closed|deferred|blocked",
  "reason": "short deterministic reason",
  "evidence_strength": "none|weak|actionable|blocking",
  "guard_mode": "observe_only|prompt_nudge|block_broad|block_finish",
  "open_candidate_count": 2,
  "unread_anchor_count": 1,
  "unverified_patch_batch_count": 1,
  "verifier_obligations": [
    "invoke behavior through original runtime context"
  ],
  "blocked_action_kinds": ["broad_verifier", "finish", "repeat_search"],
  "blocked_action_fingerprints": [],
  "broad_verifier_allowed": false,
  "finish_allowed": false,
  "next_action": "read_file anchor-3"
}
```

Closure criteria for v0:

1. Every visible sibling candidate is `verified`, `rejected`, `deferred`, or
   `blocked` with a concrete reason.
2. Any applied patch batch has a cheap or targeted verifier result.
3. The latest same-family cheap/targeted verifier either passes or changes the
   failure family.
4. Runtime components have behavior invocation proof or repository-test-tail
   proof, not only import/load/path proof.
5. No active rejection frontier invalidates the patch family.

Only then may broad verifier selection outrank local search/read/edit/cheap
verify. Finish remains blocked until the acceptance done gate also passes.

### `compact_summary`

Purpose: survive context compression and wall-time handoff.

Fields:

```json
{
  "one_line": "same-family repository/runtime verifier failure; 2 sibling candidates open",
  "failure_signature": "stable-hash",
  "evidence_refs": [],
  "open_candidates": ["candidate-1", "candidate-2"],
  "next_action": "read candidate-2 anchor then apply one bounded edit batch",
  "guard_mode": "block_broad",
  "blocked_action_kinds": ["broad_verifier"]
}
```

This summary should be short enough to keep in compact resume modes.

### Guard Eligibility Contract

The guard is driven by `closure_state.evidence_strength` and
`closure_state.guard_mode`. `compact_summary` only renders those fields; it does
not introduce separate advisory-only `do_not_repeat` text.

`guard_mode` is the single source of truth for whether the frontier may block
actions. `blocked_action_kinds` is the exact set of blocked action families
under that mode. The booleans `broad_verifier_allowed` and `finish_allowed` are
serialized convenience fields only, and tests should require them to equal the
derived values:

```text
broad_verifier_allowed =
  "broad_verifier" not in blocked_action_kinds
  and closure_state.state in {"broad_verify_ready", "closed", "deferred"}

finish_allowed =
  "finish" not in blocked_action_kinds
  and closure_state.state in {"closed", "deferred"}
  and verifier_obligations is empty
```

If stored booleans disagree with the derived values, the guard must use
`guard_mode` and record a state-normalization warning.

Evidence strength:

- `none`: no normalized failure signature. No prompt nudge and no blocking.
- `weak`: a failure line or generic error exists, but there is no command
  evidence ref and no exact anchor, candidate, or external verifier ref. Prompt
  visible only. It cannot block broad verifier or finish.
- `actionable`: stable signature plus at least one command/tool/artifact
  evidence ref and one exact next-step source: an unread anchor, sibling
  candidate, failing test, runtime behavior obligation, or patch batch needing
  verifier history. May prefer read/search/edit in prompt text. If exact
  repeated actions should be blocked, the derivation table must promote the
  guard to `block_broad` with only those repeat fingerprints in
  `blocked_action_fingerprints`.
- `blocking`: actionable evidence plus one open obligation that would make a
  broad verifier or finish wasteful or false: unread exact anchor, open sibling
  candidate, unverified applied patch batch, active rejection frontier for the
  patch family, finish false-positive evidence, or runtime behavior proof
  missing for a positively detected runtime component.

Guard mode:

- `observe_only`: no blocking; state is for resume/reporting.
- `prompt_nudge`: the prompt and `next_action` should prefer the frontier, but
  the deterministic guard should not override the model action.
- `block_broad`: the guard may reject broad verifier/build/test actions and
  repeat-search fingerprints while allowing targeted read/search/edit/cheap
  verifier and unrelated safe work.
- `block_finish`: the guard may reject finish in addition to `block_broad`.
  This requires either explicit verifier obligations, finish false-positive
  evidence, or missing behavior proof for a positively detected runtime
  component.

Derivation table:

| Evidence / closure condition | `guard_mode` |
|---|---|
| `evidence_strength == "none"` | `observe_only` |
| `evidence_strength == "weak"` | `prompt_nudge` |
| `evidence_strength == "actionable"` and no blocking predicate is true | `prompt_nudge` |
| `evidence_strength in {"actionable", "blocking"}` and repeat-search fingerprint is the only blocked action | `block_broad` with `blocked_action_kinds = ["repeat_search"]` |
| `broad_blocker == true` and `finish_blocker == false` | `block_broad` with `blocked_action_kinds` including `broad_verifier` |
| `finish_blocker == true` | `block_finish` with `blocked_action_kinds` including `finish` and usually `broad_verifier` |
| `closure_state.state in {"closed", "deferred"}` and verifier obligations are empty | `observe_only` |

`closure_state.state == "open"` is transient. Before action selection, the
normalizer must classify it into `search_needed`, `read_needed`, `edit_needed`,
`cheap_verify_needed`, `broad_verify_ready`, `closed`, `deferred`, or
`blocked`. If an `open` state reaches the guard with actionable or blocking
evidence, treat it as `block_broad` until normalized. If it reaches the guard
with weak evidence, demote to `prompt_nudge`.

The `broad_blocker` predicate is:

```text
signature exists
and at least one evidence_ref exists
and closure_state.state in {"open", "search_needed", "read_needed", "edit_needed", "cheap_verify_needed"}
and at least one exact anchor, candidate, patch_batch, failing test, or runtime obligation exists
```

The `finish_blocker` predicate is:

```text
broad_blocker
or failure_signature.kind == "finish_false_positive"
or closure_state.verifier_obligations is non-empty
or runtime_component_kind != "unknown" and behavior proof is missing
```

`blocked_action_fingerprints` are normalized action shapes such as a repeated
same search query/path or the same broad verifier command. They are deterministic
guard inputs, not prose.

## Extraction Sources

The frontier extractor should merge evidence from these existing surfaces.

### Verifier Output

Sources:

- `run_tests` and verifier-shaped `run_command` results;
- `result.verification` records;
- `build_verifier_failure_repair_agenda()` output;
- external verifier stdout from Terminal-Bench result artifacts;
- repository-test-tail emulator summaries.

Extract:

- normalized error lines;
- source locations;
- failing test names;
- runtime component hints;
- missing import/attribute/symbol facts;
- sibling search queries;
- behavior-vs-load proof gaps.

### Command Transcript and Result

Sources:

- `work_report.steps`;
- `session.tool_calls`;
- command lifecycle records and `execution_contract`;
- `CommandEvidence` refs once available;
- terminal/nonterminal status, exit code, timeout, stdout/stderr head/tail.

Extract:

- failure signature source command;
- repeated broad verifier/build count for the same signature;
- latest cheap verifier after a patch;
- whether the command proved behavior or only load/path existence.

### Runtime Stack Traces

Sources:

- stderr/stdout traceback frames;
- compiled/native loader/runtime failures;
- generated-artifact paths with matching workspace source;
- `runtime_contract_gap` from existing verifier agenda.

Extract:

- stack frame path/line anchors;
- generated-to-source mapping candidates;
- runtime component kind;
- behavior invocation obligations;
- recommended mapping tools for native/runtime failures.

### Search Results

Sources:

- successful `search_text` calls;
- `search_anchor_observations`;
- repeated zero-match and redundant search observations;
- read coverage after search anchors.

Extract:

- sibling candidate paths;
- query-to-anchor refs;
- unread anchors that must become `read_file` before more rediscovery;
- stale or repeated search patterns to avoid.

### Active Work Todo, Rejection, and Existing Frontier State

Sources:

- `active_work_todo`;
- `work_todos`;
- `active_rejection_frontier` and `rejection_frontiers`;
- `failed_patch_repair`, `broad_rollback_slice_repair`, and retry context;
- any prior `active_compatibility_frontier`.

Extract:

- whether a scoped edit frontier already exists;
- cached read windows and freshness refs;
- patch-family rejection that should block another similar edit;
- open edit or verification obligations;
- continuity across a frontier update.

### Mew Report and Resume State

Sources:

- `work_session.resume`;
- `terminal_bench_replay.replay_terminal_bench_job()` output;
- dogfood scenario fixture contexts;
- Harbor `result.json`;
- normalized agent traces.

Extract:

- wall-time handoff/finish reason;
- external reward vs internal finish;
- latest bottom failure after compaction;
- time from first failure signature to first sibling search/read/edit;
- broad rebuild/test cycles while the same frontier was open.

## Action-Selection Policy

v0 should add deterministic action guards around the model's proposed action.
Prompt text may explain the policy, but the guard must own enforcement.

The guard reads canonical session state, not only the prompt-rendered compact
summary. It applies only according to `closure_state.guard_mode`.

When an open guard-eligible `ActiveCompatibilityFrontier` exists:

1. If `closure_state.state == "search_needed"`, prefer a search/read action
   that can discover sibling candidates. Block broad rebuild/test unless no
   search/read capability is available.
2. If successful anchors exist with `read_status == "unread"`, prefer the
   narrow `read_file` suggested by the anchor. Block repeating the same search.
3. If sibling candidates are `read` or `anchored` and no patch batch covers
   them, prefer one bounded edit slice. For multiple same-family visible
   candidates, prefer a complete visible sibling slice over a one-occurrence
   patch.
4. If a patch batch is `applied` and lacks verifier history, prefer the cheapest
   verifier that can falsify the current hypothesis.
5. If the cheap/targeted verifier shows the same signature and open candidates
   remain, keep the frontier open and require new evidence/search/read/edit
   before another broad verifier.
6. If the failure family changes, close or supersede the old frontier and open
   a new frontier from the new evidence.
7. If `failure_signature.kind == "finish_false_positive"`, reopen or create the
   frontier from the external verifier evidence and choose the missing behavior
   proof, repository tail proof, search/read, or targeted repair action before
   any new finish attempt.
8. Allow a broad verifier only when `closure_state.broad_verifier_allowed` is
   true.
9. Block finish when `closure_state.finish_allowed` is false, when verifier
   obligations remain, when an active rejection frontier invalidates the current
   patch family, or when acceptance evidence refs do not satisfy the done gate.

Action priority while open:

```text
finish_false_positive -> missing behavior/repository-tail proof or targeted repair
unread anchor -> targeted read
missing sibling evidence -> search/read
anchored unedited candidate -> edit/write batch
applied unverified patch -> cheap verifier
closed visible frontier -> broad verifier
all gates pass -> finish
```

Broad verifier means any expensive reinstall, full test suite, task verifier,
or broad rebuild/test cycle. Cheap verifier means a static check, targeted unit
test, behavior smoke, focused import plus behavior call, or a single repository
tail test that exercises the frontier.

The guard should be conservative. A `weak` or `prompt_nudge` frontier should
not block normal work. A `blocking` frontier should outrank general prompt
guidance only for the blocked action kinds named in `closure_state`.

### Priority With Existing Work State

`ActiveCompatibilityFrontier` is not a replacement for existing work-session
state. Precedence should be deterministic:

1. Pending approvals and active reviewer rejection recovery remain first. If
   `active_rejection_frontier` says the current patch family was rejected, the
   next action is the rejection recovery read/replan unless the proposed action
   is a verifier or read that directly satisfies that recovery.
2. Running command lifecycle remains first for the same command. If a managed
   command is running, poll/read-output rules still apply before starting a new
   mutating broad verifier.
3. `finish_false_positive` frontier state blocks finish even if
   `active_work_todo` is completed, because completion of a draft does not prove
   external behavior.
4. A write-ready `active_work_todo` may proceed when its target paths, cached
   windows, or plan item directly cover every open anchored frontier candidate
   that needs editing. In that case the todo is the edit projection of the
   frontier, not a competing state.
5. Frontier read/search obligations take precedence over a write-ready todo
   when the todo target paths do not cover an unread exact anchor or open
   sibling candidate.
6. After a frontier-covering patch is applied or approved, cheap verifier
   obligations take precedence over starting another unrelated edit todo.
7. Broad verifier remains blocked while `guard_mode == "block_broad"` unless
   `closure_state.broad_verifier_allowed` is true.

If the frontier and `active_work_todo` disagree about target paths, the design
prefers the state with fresher evidence refs. If neither has fresh exact
evidence, the guard demotes to `prompt_nudge` and should not block.

### `active_work_todo` Coverage Predicate

`todo_covers_frontier(todo, frontier)` is true only when every open
editing-required candidate is covered by the todo's target paths and fresh
cached windows.

Editing-required candidates are candidates with status `read`, `anchored`,
`edited`, `unexplored`, or `blocked` when the blocker is missing exact context.
Candidates with status `verified`, `rejected`, `deferred`, or `blocked` for an
external reason are ignored.

For each editing-required candidate:

1. A candidate path or one of its anchor paths must match one of
   `active_work_todo.source.target_paths` after normalizing separators and
   repository-relative prefixes. Suffix matching is allowed only for
   repository-relative paths; arbitrary prefix containment is not enough.
2. If the candidate has a line anchor, at least one
   `active_work_todo.cached_window_refs` item for the matched path must cover
   that line and have either the same `window_sha1` as the anchor freshness ref
   or a `tool_call_id` later than the anchor's source event.
3. If the candidate has no line anchor but has a path anchor, the todo must have
   a complete or structurally sufficient cached window for that path after the
   candidate source event.
4. Symbol-only candidates without a path are not covered until a search/read
   converts them into path anchors.

A write-ready todo may proceed only when `todo_covers_frontier()` is true and
the todo plan item is an edit/repair action, not a verifier-only or no-change
closeout. If any editing-required candidate is uncovered, frontier read/search
obligations take precedence.

## Finish Gate for Runtime Components

For loadable runtime components, import/load/path evidence is insufficient.
This applies generically to native modules, shared libraries, plugins, generated
executables, interpreters, simulators, and custom runtime harnesses.

This gate is a pre-check before `acceptance_done_gate_decision()` in
`src/mew/acceptance.py`. It decides whether a proposed `finish` may become an
acceptance candidate. The existing acceptance done gate remains the final
authority for cited evidence refs and task acceptance constraints.

Behavior invocation proof is a completed `CommandEvidence` or legacy tool-call
result satisfying `behavior_proof_passes(frontier, evidence)`.

`behavior_proof_passes()` is true only if all required predicates pass:

- `terminal_success`: the command completed after the latest relevant
  edit/build/install evidence and exited successfully.
- `command_kind`: the evidence is from `run_tests`, verifier-shaped
  `run_command`, or an external verifier result.
- `context_match`: the command ran in the task's original runtime context, or
  in a documented installed/runtime context produced by the current session.
- `target_overlap`: the command or test target overlaps at least one frontier
  candidate path, anchor path, generated artifact ref, runtime component
  artifact, or failing test identity.
- `callable_invocation`: the command invokes a callable/function/method,
  executable entrypoint, plugin host entrypoint, runtime harness program, or
  targeted test body. Import followed only by attribute access is not callable
  invocation.
- `observable_behavior`: the output, test report, return value, exit behavior,
  or produced side effect proves behavior not derivable from import/load/path
  existence alone.
- `evidence_ref_attached`: the evidence ref appears in the frontier verifier
  history or acceptance checks.

For `run_tests`, `target_overlap` can be satisfied by a test node id, test file,
or test report entry matching a candidate path, source anchor, runtime
component artifact, or failing test identity. For external verifier success,
`target_overlap` is satisfied only when the result is for the same
`runtime_component_kind` and same or narrower family key.

Negative signals that do not satisfy behavior proof by themselves:

- the file exists;
- the artifact is executable;
- the package imports;
- a module or extension loads;
- import followed only by attribute existence or `hasattr` succeeds;
- a path points at the expected build output;
- build/install succeeds;
- `file`, `ldd`, `otool`, `readelf`, `nm`, `which`, `ls`, checksum, metadata,
  or permission checks pass;
- a smoke command exercises only an unrelated neutral path;
- `--version` or help text runs unless the task explicitly asks only for that
  command shape.

The finish gate should be implemented as a deterministic guard in the same
family as existing calibration and acceptance gates. It should also populate or
reopen `ActiveCompatibilityFrontier` with `kind = "finish_false_positive"` when
internal finish succeeds but external verifier evidence remains red.

If `runtime_component_kind == "unknown"`, this specific runtime finish gate
does not block finish by itself. Other frontier or acceptance obligations may
still block.

## Compact and Reentry Behavior

Context compression must not lose the bottom failure.

The canonical frontier object remains in session state across compaction.
`compact_summary` is only the prompt-rendered view. Deterministic guards must
load the canonical object from session/resume state before applying policy; they
must not make blocking decisions from a lossy one-line summary alone.

Required behavior:

- Add `active_compatibility_frontier` to `build_work_session_resume()`.
- Add a compact rendering to `format_work_session_resume()`.
- Add the frontier to `compact_resume_for_prompt()` in `src/mew/work_loop.py`
  and to any focused recovery keep-list that would otherwise drop it.
- Keep `compact_summary`, `failure_signature`, `evidence_refs`,
  `open_candidates`, and `closure_state.next_action` in compact modes.
- Do not copy raw verifier logs into compact context; preserve refs to
  command evidence, result artifacts, or verifier stdout.
- On reentry, if an open frontier exists, `next_action` should name the
  frontier action before generic "continue work session" language.
- Wall timeout, model timeout, stop request, or context compaction must not
  demote an open frontier into only historical transcript text.

If the canonical guard state cannot be read after compaction or resume, the
guard must demote to `prompt_nudge`, record a recovery warning, and avoid
blocking broad verifier/finish until the frontier is reconstructed from durable
evidence refs.

### Reconstruction From Evidence Refs

Reconstruction is best-effort and should be deterministic. It rebuilds enough
canonical state to resume safely, then requires fresh evidence before returning
to blocking mode if required fields are missing.

Ref-to-field mapping:

- `command_evidence` or legacy `tool_call`: rebuilds
  `failure_signature.tool`, `command_shape`, `cwd_shape`, `exit_class`,
  command evidence refs, and `verifier_history` entries from command status,
  exit code, execution contract, and bounded output.
- `verifier_stdout`: rebuilds `error_tokens`, `failing_test_tokens`,
  stack/source anchors, runtime-component detection signals, and verifier
  history notes.
- `harbor_result`: rebuilds external reward, mew exit/stop reason,
  `finish_false_positive` evidence, external verifier stdout refs, and
  same-shape trial identity.
- `search_anchor_observations` or source `search_text` events: rebuilds
  `anchors`, `sibling_candidates`, read status, and repeat-search blocked
  fingerprints.
- `verifier_failure_repair_agenda` resume keys: rebuild error lines, source
  locations, symbols, sibling search queries, runtime contract gap,
  `closure_state.next_action`, and initial hypotheses.
- `active_work_todo`: rebuilds current edit projection, cached-window refs,
  patch-batch target paths, and todo coverage candidates.
- `active_rejection_frontier`: rebuilds patch-family blockers and closure
  reasons for rejected or stale edit families.

Fallback modes:

- If only a failure signature and command/verifier refs can be rebuilt, set
  `evidence_strength = "actionable"` and `guard_mode = "prompt_nudge"` until a
  fresh search/read/verifier produces exact anchors or candidates.
- If finish false-positive external verifier evidence is rebuilt with a valid
  Harbor or external verifier ref, set `guard_mode = "block_finish"` even if
  sibling anchors need fresh reconstruction.
- To leave demotion after reentry, the session must add fresh evidence: a
  targeted read for an anchor, a new search result, a cheap verifier result, or
  a command evidence record that satisfies the guard eligibility predicate.

The state must make this reentry sentence mechanically true:

```text
The bottom failure is still <signature>; the next action is <read/edit/cheap verifier>, not rediscovery.
```

## Reference Trace Metrics

The 2026-05-05 reference traces should be used as evaluation baselines, not as
recipes to clone.

Track these metrics for mew before and after v0:

- `time_to_first_failure_signature`: first command/verifier output that creates
  or updates the frontier.
- `time_to_first_sibling_search`: elapsed time from frontier creation to a
  sibling search/read action.
- `time_from_first_anchor_to_first_patch`: elapsed time from first successful
  anchor to first related edit.
- `same_frontier_broad_cycle_count`: broad rebuild/test cycles while the same
  frontier has open candidates.
- `same_frontier_rediscovery_count`: repeated searches/reads that ignore known
  anchors.
- `frontier_open_duration_seconds`: total time frontier remains open.
- `finish_false_positive_count`: internal finish with external verifier failure
  and open frontier obligations.
- `repository_tail_after_main_smoke_count`: main smoke passed but repository or
  behavior tail remained open.
- `speed_1_delta`: change in runtime, stop reason, and score for exactly one
  same-shape live trial after local proof passes.

Reference comparison should answer:

```text
Did mew reduce broad cycles and anchor-to-patch delay after first known failure?
```

A successful v0 does not need to match the reference agents' exact command or
edit counts. It should reduce rediscovery and broad-cycle waste on the selected
same-shape proof.

## UT, Replay, Dogfood, and Emulator Proofs

No live `speed_1` should run until these pass on current head.

Focused unit tests:

- frontier extraction from verifier output and command transcripts;
- search-anchor-to-read obligations;
- sibling candidate closure state;
- patch-batch verifier obligations;
- finish blocked for runtime component load/path-only proof;
- finish allowed after behavior invocation or repository-test-tail proof;
- compact resume preserves frontier summary and evidence refs;
- broad verifier blocked while open candidates remain;
- weak/empty frontier does not overblock unrelated tasks.

Replay:

- replay the latest relevant saved Terminal-Bench artifact with assertions for
  `external_reward=0`, mew exit/stop shape, and current bottom failure;
- include the current-head wall-time frontier exhaustion artifact;
- include the finish false-positive artifact where internal finish succeeded
  but external verifier failed.

Dogfood:

- `m6_24-terminal-bench-replay` on the saved artifact and task filter;
- `m6_24-repository-test-tail-emulator` on the same artifact shape;
- a dogfood assertion that compact/reentry state contains the frontier
  signature, open candidates, and next action.

Emulator:

- a generic same-family compatibility fixture that produces verifier output,
  stack/search anchors, sibling candidates, a model action that tries a broad
  rebuild too early, and a guard result that redirects to read/edit/cheap
  verify;
- a runtime component fixture where import/load/path proof exists but behavior
  invocation or repository-tail proof is missing.

Only after all four proof layers pass should the controller spend exactly one
same-shape live `speed_1`.

## Non-Goals

- No task-specific solver.
- No fixed compatibility-symbol table.
- No package, benchmark, or Cython-extension recipe encoded in source.
- No broad M6.24 scoped measurement before the selected same-shape repair is
  locally proved and speed-tested.
- No new authoritative lane.
- No write-capable helper lane.
- No concurrent write batching.
- No full Codex or Claude Code clone.
- No replacement of mew's deterministic acceptance done gate with final-message
  trust.
- No prompt-only guidance as the primary repair.
- No expansion of shell-string classifiers where typed state or evidence refs
  are available.

## What Not To Copy From Codex or Claude Code

Codex and Claude Code appear to solve this shape mostly through transcript
continuity, tool-result visibility, read/search/edit tool discipline, prompt
policy, todo/task reminders, and verification habits. Neither reviewed source
contained an explicit active compatibility frontier object.

Mew should copy the invariants, not the implicit implementation:

- Keep failure evidence structured and model-visible.
- Preserve tool output and patch lifecycle refs.
- Prefer search/read before edit and specific-to-broad verification.
- Serialize writes.
- Preserve compact summaries across recovery.
- Use read-only exploration and verification as evidence patterns when useful.

Mew should not copy:

- prompt-only reliance on model discipline;
- `update_plan` or todo state as algorithmic repair state;
- complete session/rollout/subagent complexity;
- feature-flag and UI machinery unrelated to the failure;
- large raw tool-result persistence as the frontier memory model;
- final assistant-message semantics as proof of completion.

## Phased Implementation Plan

### Phase 0: Contract Freeze

Files likely touched:

- `docs/DESIGN_2026-05-05_M6_24_ACTIVE_COMPATIBILITY_FRONTIER.md`
- optional design review/handoff artifacts only

Work:

- Review this design against M6.24 controller docs.
- Decide whether v0 starts in `work_session.py` helpers or a new
  `src/mew/compatibility_frontier.py` module.

Rollback criteria:

- Reviewers find that the proposal is task-specific, prompt-only, or conflicts
  with the M6.24 controller chain.

### Phase 1: Extractor and State

Files likely touched:

- `src/mew/work_session.py`
- possibly `src/mew/compatibility_frontier.py`
- `tests/test_work_session.py`
- possibly `tests/test_compatibility_frontier.py`

Work:

- Add a normalizer/extractor that builds or updates
  `active_compatibility_frontier` from calls, resume, and prior frontier state.
- Reuse existing verifier agenda and search-anchor extraction rather than
  duplicating parsers.
- Add stable failure signatures and evidence refs.
- Merge prior frontier state when the fingerprint remains the same.

Rollback criteria:

- The extractor creates frontiers from weak noise and overblocks unrelated
  implementation tasks.
- The extractor needs task/package-specific names to pass tests.
- The frontier grows raw log bodies instead of evidence refs.

### Phase 2: Resume, Compact, and Reentry

Files likely touched:

- `src/mew/work_session.py`
- `src/mew/work_loop.py`
- `src/mew/commands.py`
- `tests/test_work_session.py`
- `tests/test_work_replay.py`

Work:

- Add frontier projection to `build_work_session_resume()`.
- Add compact text to `format_work_session_resume()`.
- Preserve compact summary and refs in `compact_resume_for_prompt()` in
  `src/mew/work_loop.py` and focused recovery mode.
- Make `next_action` prefer open frontier obligations.
- Expose the frontier in follow/status only as compact state.

Rollback criteria:

- Compact context size materially regresses.
- Reentry drops `failure_signature`, evidence refs, or next action.
- Canonical guard state is unreadable after compaction/resume and cannot be
  reconstructed from durable evidence refs.
- Follow/status becomes noisy enough to obscure the actionable frontier.

### Phase 3: Action-Selection Guard

Files likely touched:

- `src/mew/work_loop.py`
- `tests/test_work_session.py`
- `tests/test_work_loop_patch_draft.py`
- `tests/test_work_replay.py`

Work:

- Add a deterministic post-normalization guard for open frontiers.
- Redirect repeated broad verifier/build or finish actions to search/read/edit
  or cheap verifier when obligations remain.
- Preserve existing `active_work_todo` and rejection-frontier gates.
- Record guard outcomes in model metrics or session notes for replay.

Rollback criteria:

- The guard blocks broad verification after closure criteria are met.
- The guard blocks tasks without exact frontier evidence.
- The guard causes a model/action loop with no new evidence.

### Phase 4: Runtime Component Finish Gate

Files likely touched:

- `src/mew/work_loop.py`
- `src/mew/acceptance.py`
- `src/mew/work_session.py`
- `tests/test_work_session.py`
- `tests/test_acceptance.py`

Work:

- Distinguish load/path/import proof from behavior proof.
- Require behavior invocation, targeted component tests, repository-test-tail
  proof, or external verifier proof before finish for runtime components.
- Reopen or create a finish-false-positive frontier when internal finish
  conflicts with external verifier result.

Rollback criteria:

- The gate cannot distinguish runtime component tasks from ordinary code tasks
  without task-specific names.
- It rejects valid no-change investigations or pure documentation tasks.
- It duplicates existing acceptance done-gate logic instead of using evidence
  refs.

### Phase 5: Proof Harness

Prerequisite:

- Trace-metric work depends on `src/mew/agent_trace.py` and
  `src/mew/reference_trace_runner.py`. If those files are still unmerged or
  part of parallel work, land them first or gate the trace-metric portion behind
  a post-trace-merge step. Replay, dogfood, and emulator proof should still run
  without assuming trace modules are present.

Files likely touched:

- `src/mew/dogfood.py`
- `src/mew/terminal_bench_replay.py`
- `src/mew/agent_trace.py`
- `src/mew/reference_trace_runner.py`
- `tests/test_dogfood.py`
- `tests/test_terminal_bench_replay.py`
- `tests/test_agent_trace.py`
- `tests/test_reference_trace_runner.py`

Work:

- Add replay assertions for frontier signature and next action.
- Extend the repository-test-tail emulator to assert frontier preservation.
- Add a same-family compatibility emulator and runtime finish-gate emulator.
- Normalize mew trace timing for anchor-to-patch and same-frontier broad-cycle
  metrics.

Rollback criteria:

- Emulator fixtures become benchmark recipes.
- Metrics cannot be computed from current reports without invasive trace format
  changes.
- Proof harness passes without proving the actual frontier obligations.

### Phase 6: Same-Shape Trial and Decision Record

Files likely touched:

- `docs/M6_24_DECISION_LEDGER.md`
- `proof-artifacts/m6_24_gap_ledger.jsonl`
- a new proof summary document if the controller requires it

Work:

- Run the focused UT/replay/dogfood/emulator gate.
- Spend exactly one same-shape live `speed_1`.
- Record score, stop reason, reference-metric delta, same-frontier broad-cycle
  count, and adopted/rejected decision.

Rollback criteria:

- Live `speed_1` is unchanged or regresses and replay can reproduce the miss.
- The new miss is a frontier guard false positive rather than a moved bottom
  failure.
- The change increases broad-cycle count or finish false positives.

## Review Questions

Reviewers should focus on these points:

1. Is the state model generic enough, with no hidden task recipe?
2. Does it fit the current M6.24 controller and implementation/tiny lane?
3. Are extraction sources complete enough to preserve the bottom failure through
   compact/reentry?
4. Are the action guard and finish gate deterministic, not just prompt advice?
5. Are closure criteria strict enough to block false finish but loose enough to
   avoid overblocking unrelated tasks?
6. Do the proof requirements prevent another live proof before replay, dogfood,
   and emulator can detect the selected same-shape failure?
