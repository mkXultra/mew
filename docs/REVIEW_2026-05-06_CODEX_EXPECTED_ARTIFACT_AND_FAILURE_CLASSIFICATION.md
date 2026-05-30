# Codex Expected Artifact and Failure Classification Review

Date: 2026-05-06

Scope: read-only review of `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex`.

## Findings

1. Codex does not appear to have a structured equivalent of `execution_contract.expected_artifact`.
   - Repository searches found no `expected_artifact`, generic artifact-check contract, or command-execution artifact verifier.
   - The closest pattern is an instruction in `codex-rs/core/templates/goals/continuation.md:17-23` telling the agent to build a prompt-to-artifact checklist and inspect evidence before completion. That is prompt policy, not runtime-enforced structured verification.
   - There is an under-development `artifact` feature flag (`codex-rs/features/src/lib.rs:202-203`, `codex-rs/features/src/lib.rs:982-985`), but it is skipped in config schema generation (`codex-rs/config/src/schema.rs:24-26`) and does not provide generic expected-artifact checks for command execution.

2. Codex has typed execution results internally and typed command lifecycle events externally.
   - Internal shell execution returns `ExecToolCallOutput { exit_code, stdout, stderr, aggregated_output, duration, timed_out }` with truncation metadata on streams (`codex-rs/protocol/src/exec_output.rs:15-19`, `codex-rs/protocol/src/exec_output.rs:39-47`).
   - Command-end events preserve structured fields including stdout, stderr, aggregated output, exit code, duration, formatted output, and status (`codex-rs/protocol/src/protocol.rs:3053-3059`, `codex-rs/protocol/src/protocol.rs:3085-3124`).
   - App-server v2 turns those events into `ThreadItem::CommandExecution` with status, output, exit code, and duration (`codex-rs/app-server-protocol/src/protocol/v2.rs:5623-5647`; builders at `codex-rs/app-server-protocol/src/protocol/item_builders.rs:89-133`).
   - `codex exec` JSONL keeps the same typed command item/status shape (`codex-rs/exec/src/exec_events.rs:145-163`; mapping at `codex-rs/exec/src/event_processor_with_jsonl_output.rs:160-178`).

3. Tool result schemas exist, but mostly for unified exec and MCP, not classic shell.
   - `exec_command` declares an output schema (`codex-rs/tools/src/local_tool.rs:19-89`) whose fields are `chunk_id`, `wall_time_seconds`, `exit_code`, `session_id`, `original_token_count`, and `output` (`codex-rs/tools/src/local_tool.rs:299-330`).
   - The unified exec implementation stores the same typed fields in `ExecCommandToolOutput` (`codex-rs/core/src/tools/context.rs:374-386`) and can serialize a structured code-mode result (`codex-rs/core/src/tools/context.rs:416-443`), while normal model-facing output is formatted text (`codex-rs/core/src/tools/context.rs:453-479`).
   - Tool definitions include optional output schemas (`codex-rs/tools/src/tool_definition.rs:7-12`), but `ResponsesApiTool.output_schema` is skipped during serialization (`codex-rs/tools/src/responses_api.rs:25-38`), so this is not uniformly a model/API-enforced runtime contract.

4. MCP is the strongest structured-result pattern.
   - MCP tools carry an `output_schema` (`codex-rs/protocol/src/mcp.rs:29-43`) and return `CallToolResult { content, structured_content, is_error, meta }` (`codex-rs/protocol/src/mcp.rs:137-151`).
   - Codex wraps MCP output schemas into a generic result schema with `structuredContent` and `isError` (`codex-rs/tools/src/mcp_tool.rs:22-59`).
   - `CallToolResult::success()` is derived from `is_error`, and structured content is preferred when converting to function-call output (`codex-rs/protocol/src/models.rs:1426-1490`); a test asserts structured content wins over text content (`codex-rs/core/src/session/tests.rs:2498-2522`).

5. Standalone app-server `command/exec` has structured run-command results but no build/runtime failure taxonomy.
   - The request supports cwd/env/timeout/output cap/sandbox/permission profile (`codex-rs/app-server-protocol/src/protocol/v2.rs:3256-3344`).
   - The response is only `exit_code`, `stdout`, and `stderr` (`codex-rs/app-server-protocol/src/protocol/v2.rs:3346-3360`).
   - Runtime maps timeout to `EXEC_TIMEOUT_EXIT_CODE` and returns the final structured response (`codex-rs/app-server/src/command_exec.rs:442-564`); streaming output chunks include stream name and truncation flag (`codex-rs/app-server/src/command_exec.rs:566-627`).

6. Hook execution is verifier-like but still not a generic verifier evidence contract.
   - Hook command runs return structured `CommandRunResult { started_at, completed_at, duration_ms, exit_code, stdout, stderr, error }` (`codex-rs/hooks/src/engine/command_runner.rs:13-22`, `codex-rs/hooks/src/engine/command_runner.rs:24-100`).
   - Hook summaries have typed statuses `Running`, `Completed`, `Failed`, `Blocked`, and `Stopped`, plus typed output entries (`codex-rs/protocol/src/protocol.rs:1573-1621`).
   - Event-specific parsers classify hook behavior from structured exit code plus parsed JSON output, for example PostToolUse maps exit code 0, invalid JSON, code 2 feedback, and other exit codes into typed statuses/entries (`codex-rs/hooks/src/events/post_tool_use.rs:178-285`).

7. Codex avoids brittle string-only classification in some paths, but not all.
   - Command success/failure is mainly `exit_code == 0` versus nonzero (`codex-rs/core/src/tools/events.rs:302-359`, `codex-rs/core/src/tools/events.rs:419-491`).
   - Sandbox timeout and sandbox denial are typed errors carrying the original execution output (`codex-rs/core/src/exec.rs:647-705`), and the orchestrator retries denied sandbox attempts through a typed `SandboxErr::Denied` path (`codex-rs/core/src/tools/orchestrator.rs:224-353`).
   - However, sandbox-denial detection is explicitly heuristic: the code comments say it is not deterministic and then checks common stderr/stdout keywords plus exit-code rules (`codex-rs/core/src/exec.rs:707-767`).
   - `ToolError::Rejected` currently conflates user-declined approvals with some operational/runtime rejection paths, and a TODO calls out the need for a distinct variant (`codex-rs/core/src/tools/events.rs:332-341`).

## Should mew adopt the pattern?

Adopt the typed execution-result and lifecycle-event pattern: separate stdout/stderr/aggregated output, exit code, duration, timeout flag, output truncation metadata, source, status enum, and streaming deltas. Also adopt the MCP-style result shape for tools: `content`, `structuredContent`, `isError`, and declared output schemas where possible.

Do not copy Codex's lack of a generic expected-artifact contract. For `implement_v2`, artifact verification should be runtime-owned and schema-backed, not only a prompt checklist. Also do not use string-only sandbox/build/runtime classification as the primary classifier; text matching should be a fallback signal with confidence metadata.

## Suggested generic design for mew `implement_v2`

Define a first-class execution contract:

```text
ExecutionContract
  steps: ExecutionStep[]
  expected_artifacts: ExpectedArtifact[]

ExecutionStep
  id, role: setup | build | test | runtime | verify | artifact_check
  command, cwd, env, timeout_ms
  expected_exit: zero | nonzero | any | code_set
  produces: artifact_id[]

ExpectedArtifact
  id, kind: file | directory | glob | json | image | report | log
  path_or_uri, required
  checks: exists | non_empty | size_range | sha256 | json_schema | contains | mtime_after_step
```

Capture evidence with typed results:

```text
ExecutionResult
  step_id, status, exit_code, stdout_ref, stderr_ref, aggregated_ref
  duration_ms, timed_out, output_truncated, started_at, completed_at

ArtifactCheckResult
  artifact_id, status, metadata(size, sha256, mtime), failed_check, preview_ref

VerifierRun
  id, command_result: ExecutionResult
  artifact_results: ArtifactCheckResult[]
  structured_outputs: junit | tap | json | custom

FailureClassification
  phase: setup | dependency | build | test | runtime | artifact | verification | internal
  kind: spawn_failed | timeout | nonzero_exit | assertion_failed | missing_artifact | schema_mismatch | sandbox_denied | network_denied | permission_denied | internal_error
  confidence, retryable, reason, evidence_refs, signals
```

Classifier rules should prefer structured signals in this order: step role and expected exit policy, typed runtime/tool error kind, exit code and timeout flag, parser outputs from known test/build formats, artifact check failures, then text regex heuristics as low-confidence supporting signals. The final `implement_v2` result should include compact evidence refs and typed classifications rather than asking later code to infer build/runtime/artifact failure from terminal text.
