# Claude Code Expected Artifact and Failure Classification Review

Date: 2026-05-06

Reference inspected: `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code`

Constraint: the Claude Code repository was used only as a read-only reference. This report is the only file written.

## Direct answer

Claude Code does not appear to have a direct structured equivalent of `execution_contract.expected_artifact`: there is no generic expected-artifact contract, artifact-check DSL, or artifact validator tied to a Bash/tool execution contract.

It does have several adjacent patterns worth adopting:

- Typed tool input and output schemas.
- Internal command execution records with raw exit code, stdout, stderr, interruption, backgrounding, and persisted-output metadata.
- Command-specific exit-code semantics to avoid treating every nonzero code as the same kind of failure.
- Structured hook outputs and structured-output tools for verifier-like gates.
- Stable runtime result subtypes and shape-based success handling, rather than relying only on strings.
- Tool-local artifact validation for file writes and edits, including stale-file checks and structured patches.

The important gap for mew is that Claude Code keeps many facts structured internally, but often flattens them into model-facing text or XML-like tags. For `implement_v2`, mew should keep the structured execution, artifact, and verifier records as the source of truth and generate text summaries from those records.

## Findings

### 1. Tool calls have structured schemas and typed results

Claude Code's base tool interface is structured. `ToolResult<T>` carries typed `data`, optional injected messages, optional context modifiers, and MCP metadata including `structuredContent` (`src/Tool.ts:321-336`). Tools define `inputSchema`, optional JSON schemas, and optional `outputSchema`; `call()` returns `Promise<ToolResult<Output>>` (`src/Tool.ts:362-400`). MCP tool listing exposes both input and output JSON schemas (`src/entrypoints/mcp.ts:59-92`).

Tool execution validates model-provided inputs using zod before calling the tool (`src/services/tools/toolExecution.ts:614-679`). It then runs tool-specific validation and returns structured validation errors with error codes (`src/services/tools/toolExecution.ts:682-732`). Tool calls return typed `result.data`, which is mapped to a Claude `tool_result` block (`src/services/tools/toolExecution.ts:1207-1295`).

Should mew adopt this pattern? Yes. `implement_v2` should have a typed tool/run result object first, then derive model-facing content from it. The raw result should not be replaced by a text transcript.

### 2. Bash execution records raw process facts, but the model-facing Bash output omits raw exit code

Claude Code's shell layer records raw execution facts in `ExecResult`: `stdout`, `stderr`, `code`, `interrupted`, background-task fields, persisted output-file path and size, and pre-spawn errors (`src/utils/ShellCommand.ts:13-30`). Exit codes are normalized from process close events (`src/utils/ShellCommand.ts:195-203`) and included in the final `ExecResult` (`src/utils/ShellCommand.ts:291-328`).

The Bash tool has an output schema with stdout, stderr, interruption/background flags, return-code interpretation, expected-no-output, structured content, and persisted-output metadata (`src/tools/BashTool/BashTool.tsx:279-294`). However, that schema does not include a first-class `exit_code`. The exit code is logged (`src/tools/BashTool/BashTool.tsx:754-816`), and nonzero semantic errors are converted into `ShellError` text with `Exit code N` (`src/tools/BashTool/BashTool.tsx:624-719`; `src/utils/toolErrors.ts:24-31`).

Should mew adopt this pattern? Partially. Adopt the raw `ExecResult` style, but expose `exit_code` as a first-class field in every `ToolRunRecord`. Do not require consumers to recover it from error text.

### 3. Claude Code avoids some brittle exit-code handling with command-specific semantics

Claude Code explicitly documents that some commands use nonzero exit codes for non-error outcomes, for example `grep` no matches (`src/tools/BashTool/commandSemantics.ts:1-6`). The default behavior is code `0` is success and nonzero is error (`src/tools/BashTool/commandSemantics.ts:22-26`), but specific commands override that: `grep`/`rg` code `1` means no matches, `diff` code `1` means files differ, and `test`/`[` code `1` means false condition (`src/tools/BashTool/commandSemantics.ts:31-89`). The command parser is documented as heuristic and not security-critical (`src/tools/BashTool/commandSemantics.ts:108-119`), and `interpretCommandResult()` returns the semantic result (`src/tools/BashTool/commandSemantics.ts:124-140`).

Should mew adopt this pattern? Yes, with a stronger contract boundary. `implement_v2` should keep raw exit code and add `semantic_exit: { category, message, source }`, where `source` can be `default`, `known_command`, or `contract_override`. This avoids brittle stderr parsing while still handling known command conventions.

### 4. Large, empty, and background outputs are handled as artifacts, but not as expected artifacts

Claude Code persists large tool outputs under a session tool-results directory and replaces the transcript content with a preview (`src/utils/toolResultStorage.ts:80-87`, `src/utils/toolResultStorage.ts:137-184`, `src/utils/toolResultStorage.ts:205-226`). Empty tool results are replaced with an explicit completion sentinel so the model is not left with an empty tool result (`src/utils/toolResultStorage.ts:244-295`). Tool-result budgeting persists the largest fresh results and freezes decisions by `tool_use_id` (`src/utils/toolResultStorage.ts:739-856`).

For background shell tasks, notifications include a task id, output file, status, summary, and exit-code-derived completion status (`src/tasks/LocalShellTask/LocalShellTask.tsx:105-171`, `src/tasks/LocalShellTask/LocalShellTask.tsx:180-245`). `TaskOutputTool` can retrieve background output and exposes `task_id`, status, output, optional exit code and error, plus retrieval status (`src/tools/TaskOutputTool/TaskOutputTool.tsx:38-54`, `src/tools/TaskOutputTool/TaskOutputTool.tsx:60-89`, `src/tools/TaskOutputTool/TaskOutputTool.tsx:250-307`).

Should mew adopt this pattern? Yes for output persistence, previews, empty-output sentinels, and background run records. But mew should add explicit expected-artifact checks on top: persisted output is evidence, not proof that the intended artifact exists or is fresh.

### 5. Hooks provide the strongest structured verifier-like mechanism

Hook JSON output is schema-validated with zod (`src/types/hooks.ts:49-176`; `src/utils/hooks.ts:378-451`). Hook responses can approve, block, provide a reason, suppress output, add context, or update tool inputs/outputs for specific hook events (`src/utils/hooks.ts:489-653`). Hook command execution captures stdout, stderr, combined output, status, and aborted state (`src/utils/hooks.ts:1200-1328`). Exit code `2` is treated as blocking feedback, while other nonzero codes are non-blocking errors (`src/utils/hooks.ts:2647-2697`).

Post-tool hooks receive structured tool context: `tool_name`, `tool_input`, `tool_response`, and `tool_use_id` (`src/utils/hooks.ts:3450-3467`). Post-tool-failure hooks receive `tool_name`, `tool_input`, `tool_use_id`, `error`, and `is_interrupt` (`src/utils/hooks.ts:3492-3517`).

Claude Code also has a structured agent-hook response schema: `{ ok: boolean, reason?: string }` (`src/utils/hooks/hookHelpers.ts:16-24`). It creates a `StructuredOutput` tool from a JSON schema and forces the hook agent to call it exactly once (`src/utils/hooks/hookHelpers.ts:37-82`). Agent-hook execution validates the structured output, treats missing output as cancellation, and maps `ok: false` to blocking error (`src/utils/hooks/execAgentHook.ts:211-303`).

Should mew adopt this pattern? Yes. For mew, expand `{ ok, reason }` into a verifier schema with `verdict`, `checks`, `evidence`, `run_ids`, and `artifact_ids`. The verifier result should be machine-validated and blocking when required.

### 6. The built-in verifier agent is evidence-oriented, but its final verdict is prompt-level

Claude Code's built-in verification agent is explicitly adversarial, read-only for project files, and allowed to write temporary scripts (`src/tools/AgentTool/built-in/verificationAgent.ts:10-22`). Its prompt requires strategies by change type, including command stdout/stderr/exit codes and data shape/schema checks (`src/tools/AgentTool/built-in/verificationAgent.ts:27-40`). It requires build/test/lint baselines and regression checks (`src/tools/AgentTool/built-in/verificationAgent.ts:42-49`) and warns that tests are context, not evidence, unless paired with adversarial probes (`src/tools/AgentTool/built-in/verificationAgent.ts:51-72`).

The requested output includes a strict textual shape with command run, output observed, result, and final `VERDICT: PASS|FAIL|PARTIAL` (`src/tools/AgentTool/built-in/verificationAgent.ts:81-129`). The agent metadata marks it as a background verification agent and disallows edit/write tools (`src/tools/AgentTool/built-in/verificationAgent.ts:131-152`).

Should mew adopt this pattern? Partially. Adopt the adversarial verification posture and evidence requirements. Do not make a final `VERDICT:` string authoritative. The verdict should be structured JSON validated by schema, with each check tied to concrete run and artifact records.

### 7. File artifact validation is tool-local, not a generic execution contract

Claude Code's file write and edit tools validate file paths, content, stale reads, missing prior reads, denied paths, and conflicting file state before writing (`src/tools/FileWriteTool/FileWriteTool.ts:153-221`, `src/tools/FileWriteTool/FileWriteTool.ts:266-305`; `src/tools/FileEditTool/FileEditTool.ts:137-361`, `src/tools/FileEditTool/FileEditTool.ts:442-491`). After successful writes/edits, they update read state (`src/tools/FileWriteTool/FileWriteTool.ts:331-337`; `src/tools/FileEditTool/FileEditTool.ts:519-525`) and return structured outputs including file path, original content, structured patch, and git diff (`src/tools/FileWriteTool/FileWriteTool.ts:68-87`, `src/tools/FileWriteTool/FileWriteTool.ts:390-416`; `src/tools/FileEditTool/types.ts:63-80`, `src/tools/FileEditTool/FileEditTool.ts:560-573`).

These are artifact-adjacent checks, but they validate safe editing rather than checking that a declared post-run artifact exists, is fresh, matches schema, or satisfies a contract.

Should mew adopt this pattern? Yes for stale-state protection and structured patch evidence. Mew should still add a generic `expected_artifacts` mechanism because Claude Code does not provide one.

### 8. Failure classification is mostly structured, but not a build/runtime taxonomy

Claude Code classifies tool exceptions through stable fields: `TelemetrySafeError`, Node errno `code`, stable `.name`, and fallback `Error`, explicitly avoiding brittle constructor names (`src/services/tools/toolExecution.ts:150-171`, `src/services/tools/toolExecution.ts:1639-1645`). Query success is based on message/result shape, such as assistant text/thinking, tool-result-only user messages, or `stopReason === "end_turn"` (`src/utils/queryHelpers.ts:48-94`). SDK results use structured subtypes such as `error_during_execution`, `error_max_turns`, `error_max_budget_usd`, and `error_max_structured_output_retries` (`src/QueryEngine.ts:1082-1150`; `src/entrypoints/sdk/coreSchemas.ts:1407-1436`).

Claude Code also backfills missing tool results on streaming/model errors and aborts, preventing orphaned tool-use blocks (`src/query.ts:123-149`, `src/query.ts:900-919`, `src/query.ts:980-1028`). Streaming tool execution cancels siblings based on `tool_result.is_error` and tool type, not by parsing stderr strings (`src/services/tools/StreamingToolExecutor.ts:320-365`).

What Claude Code does not appear to have is a generic classifier for `build_failure` vs `runtime_failure` vs `artifact_validation_failure`. Background shell tasks mark status as completed or failed from `result.code === 0` (`src/tasks/LocalShellTask/LocalShellTask.tsx:180-245`), while Bash has command-specific exit semantics but no higher-level build/runtime taxonomy.

Should mew adopt this pattern? Yes for structured signals and stable error categories. Mew should add its own taxonomy driven by run role, contract, exit semantics, artifact checks, and verifier checks, not by global string matching.

## Suggested generic design for mew `implement_v2`

### Core records

`ExecutionContract`

- `id`
- `kind: "command" | "tool" | "verifier"`
- `role: "build" | "test" | "runtime" | "lint" | "artifact_probe" | "custom"`
- `command` or `tool_name`
- `input`
- `cwd`
- `timeout_ms`
- `expected_exit`
- `expected_artifacts: ExpectedArtifact[]`
- `verifier_required: boolean`
- `failure_policy`

`ExpectedArtifact`

- `id`
- `kind: "file" | "directory" | "stdout" | "stderr" | "json" | "http" | "process" | "metric"`
- `path`, `url`, or `selector`
- `required: boolean`
- `freshness: "created_after_run_start" | "modified_after_run_start" | "any"`
- `checks: ArtifactCheck[]`

`ArtifactCheck`

- `type: "exists" | "non_empty" | "size_between" | "mtime_after" | "hash" | "json_schema" | "text_contains" | "regex" | "command_probe" | "http_status" | "custom_probe"`
- `expected`
- `probe_command` or `schema` where relevant
- `severity: "blocking" | "warning"`

`ToolRunRecord`

- `run_id`
- `contract_id`
- `started_at`
- `ended_at`
- `status: "success" | "failed" | "timeout" | "interrupted" | "backgrounded" | "pre_spawn_error"`
- `exit_code`
- `semantic_exit: { ok, category, message, source }`
- `stdout_preview`, `stderr_preview`
- `stdout_path`, `stderr_path`, `combined_output_path`
- `structured_output`
- `error`
- `failure_class`

`ArtifactEvidence`

- `artifact_id`
- `check_type`
- `passed`
- `observed`
- `expected`
- `path`
- `mtime`
- `size`
- `run_id`
- `message`

`VerifierEvidence`

- `verdict: "pass" | "fail" | "partial"`
- `reason`
- `checks: [{ id, passed, run_ids, artifact_ids, observed, expected, message }]`
- `missing_evidence`

### Execution flow

1. Validate the `ExecutionContract` before running anything.
2. Execute the command or tool and persist a `ToolRunRecord` with raw facts, including raw exit code.
3. Interpret exit code through a declarative semantic table:
   - default semantics
   - known-command semantics
   - explicit contract overrides
4. Persist large stdout/stderr/combined outputs and keep previews in the run record.
5. Run every declared artifact check after execution, using run start/end timestamps for freshness checks.
6. Run verifier checks only from structured records. If an AI verifier is used, require schema output and references to `run_id` and `artifact_id`.
7. Classify failure from structured signals in priority order:
   - `pre_spawn_error`
   - `timeout`
   - `interrupted`
   - `permission_or_sandbox_denied`
   - `exit_code_failure`
   - `artifact_missing`
   - `artifact_stale`
   - `artifact_schema_failed`
   - `artifact_probe_failed`
   - `verifier_failed`
   - `unknown_failure`
8. Map to higher-level labels using contract role, not stderr text:
   - `role=build` plus failed semantic exit -> `build_failure`
   - `role=test` plus failed semantic exit -> `test_failure`
   - `role=runtime` plus failed process/probe -> `runtime_failure`
   - failed required artifact check -> `artifact_validation_failure`
9. Generate model/user summaries from the structured records. The summary is never the source of truth.

### String handling rule

Avoid global success/failure regexes over stdout or stderr. String checks are allowed only as explicit artifact checks, where the contract states the exact text or regex expectation and the evidence records expected vs observed. If a classifier needs to inspect output, it should produce a structured, low-confidence annotation unless backed by exit code, schema, file stats, process status, or explicit artifact checks.

## Recommendation

Mew should adopt Claude Code's structured tool schemas, raw shell execution records, persisted-output previews, hook schema validation, and command-specific exit semantics. Mew should not copy the absence of a first-class expected-artifact contract, the omission of raw `exit_code` from model-facing Bash output, or prompt-only verifier verdicts.

For `implement_v2`, the source of truth should be:

1. `ToolRunRecord`
2. `ArtifactEvidence`
3. `VerifierEvidence`
4. `FailureClassification`

This gives mew a generic mechanism for expected artifacts and failure classification while preserving Claude Code's strongest pattern: classify from structured facts first, and use text only as explicitly declared evidence.
