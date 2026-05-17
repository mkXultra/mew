# Codex Command ID Lifecycle Review

Date: 2026-05-17

Scope: reference source under `references/fresh-cli/codex`. No source files were changed.

## Summary

Codex keeps provider tool-call identity separate from long-running terminal process identity. The provider/native transcript is paired by `call_id`. When a unified exec command remains live, Codex exposes a short numeric `session_id`/`process_id` to the model for `write_stdin` polling or continuation. It does not ask the model to reuse a long composite internal run id.

For mew, the best fix is: **both with aliasing, but only the short command id should be model-visible**. Keep the long internal id for persistence, evidence, logs, and exact backward-compatible lookup. Do not display it as the polling key.

## 1. Async Shell Identity

The model-facing unified exec tools are `exec_command` and `write_stdin`. `exec_command` is described as returning output or a session ID, and `write_stdin` requires numeric `session_id` for a running session (`references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:70`, `:92`, `:95`, `:120`, `:127`). The output schema also calls this field `session_id` and defines it as the identifier to pass to `write_stdin` while the process is still running (`references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:300`, `:315`).

In the handler, `write_stdin` parses `session_id: i32`; the comment says the model is trained on `session_id` (`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:70`). A new `exec_command` allocates a `process_id` before launch (`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:222`) and passes it into the exec request (`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:336`). Follow-up `write_stdin` maps the model's numeric `session_id` back to `process_id` (`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:382`).

Process ids are small integers: deterministic tests start at `1000`; production chooses a random value in `1_000..100_000` and reserves it (`references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:181`). If the command remains alive, Codex stores the process before yielding (`references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:271`) and returns `Some(process_id)` in the tool output (`references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:346`, `:392`). If it exits, Codex removes the process and omits the session id (`references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:527`).

The model-visible text says `Process running with session ID {process_id}` only when the process is still alive (`references/fresh-cli/codex/codex-rs/core/src/tools/context.rs:453`, `:467`). `Chunk ID` is also exposed, but it is generated separately and is not used for polling (`references/fresh-cli/codex/codex-rs/core/src/unified_exec/mod.rs:166`).

## 2. Transcript Pairing

Provider-visible tool pairing uses `call_id`, not `session_id`. `ResponseItem::FunctionCall` carries `call_id` (`references/fresh-cli/codex/codex-rs/protocol/src/models.rs:725`), and `ResponseInputItem::FunctionCallOutput` also carries `call_id` (`references/fresh-cli/codex/codex-rs/protocol/src/models.rs:616`). The router turns provider function calls into internal `ToolCall`s while preserving that `call_id` (`references/fresh-cli/codex/codex-rs/core/src/tools/router.rs:181`, `:200`). Tool results are converted back into response items with the same `call_id` (`references/fresh-cli/codex/codex-rs/core/src/tools/registry.rs:107`, `:115`; `references/fresh-cli/codex/codex-rs/core/src/tools/context.rs:540`, `:561`).

Codex also emits UI/protocol events with `call_id` for begin/end pairing and optional `process_id` for the underlying terminal process (`references/fresh-cli/codex/codex-rs/protocol/src/protocol.rs:3061`, `:3085`). Output deltas are keyed by `call_id` (`references/fresh-cli/codex/codex-rs/protocol/src/protocol.rs:3141`), while terminal interactions carry both `call_id` and `process_id` (`references/fresh-cli/codex/codex-rs/protocol/src/protocol.rs:3155`). Internally, the process store keeps both fields: `process_id` is the lookup key, while `call_id` is retained for final events and hooks (`references/fresh-cli/codex/codex-rs/core/src/unified_exec/mod.rs:113`, `:147`).

The app-server `command/exec` path uses the same separation in a different protocol: streaming or TTY execution requires a client-supplied, connection-scoped `processId`; buffered execution may get an internal id that is not exposed (`references/fresh-cli/codex/codex-rs/app-server-protocol/schema/typescript/v2/CommandExecParams.ts:19`). The app-server stores either `InternalProcessId::Generated` or `InternalProcessId::Client` (`references/fresh-cli/codex/codex-rs/app-server/src/command_exec.rs:123`) and only sends client process ids in output-delta notifications (`references/fresh-cli/codex/codex-rs/app-server/src/command_exec.rs:244`, `:605`).

## 3. Model Output Rendering

Unified exec tool output includes:

- `Chunk ID`
- `Wall time`
- `Process exited with code`, when exited
- `Process running with session ID`, when still alive
- `Original token count`, when known
- `Output`

This layout is implemented in `ExecCommandToolOutput::response_text` (`references/fresh-cli/codex/codex-rs/core/src/tools/context.rs:453`). It does not include cwd, provider `call_id`, stdout/stderr as separate fields, process start command, or hidden spool-file references. Cwd and split stdout/stderr are present in UI/protocol `ExecCommandEndEvent`, not in the model tool-output text (`references/fresh-cli/codex/codex-rs/protocol/src/protocol.rs:3085`).

The older shell output format serializes `{ output, metadata: { exit_code, duration_seconds } }` for structured function tools (`references/fresh-cli/codex/codex-rs/core/src/tools/mod.rs:30`). Freeform shell output uses text headers for exit code, wall time, total output lines, and output (`references/fresh-cli/codex/codex-rs/core/src/tools/mod.rs:71`).

Codex keeps retained terminal transcript in a capped in-memory `HeadTailBuffer`, not as a model-visible spool artifact (`references/fresh-cli/codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs:4`). The final event resolves output from that transcript (`references/fresh-cli/codex/codex-rs/core/src/unified_exec/async_watcher.rs:190`).

## 4. Internal IDs and Artifacts

Codex has several separate identities:

- Provider `call_id`: pairs function calls and outputs in the model transcript.
- Unified exec `process_id`/model `session_id`: short numeric live-process handle for polling/writing.
- `chunk_id`: short random hex output chunk marker, not a process handle.
- App-server `processId`: client-supplied, connection-scoped id for UI/client streaming.
- Internal generated app-server id: used for buffered commands and not exposed.

There is no evidence in the unified exec path of hidden spool-file ids being surfaced to the model. Output retention is in memory via `HeadTailBuffer`, and process state is in `ProcessStore` keyed by numeric `process_id`.

## Recommendation for mew

Adopt Codex's split:

1. Generate a short model-visible `command_id` for every live command, for example `cmd_1`, `cmd_2`, or a 4-5 digit numeric id.
2. Show only that `command_id` in command results and require it for polling/continuation.
3. Keep the long id (`1:1:implement_v2:native:command:call_xxx-deadbeef`) as an internal run id for logs, persistence, evidence, and exact backward-compatible lookup.
4. Maintain aliases from `command_id`, provider call id, and exact old internal run id to the same command record, but do not print the long id in model-facing instructions.
5. On unknown id, return an error that lists active short command ids and command summaries.
6. Do not reuse provider `call_id` or output `chunk_id` as the polling handle.

This is effectively **both with aliasing**, with a strict UX rule: the model sees and uses only the short command id. That addresses the current truncation failure because the model no longer needs to copy a long composite string.
