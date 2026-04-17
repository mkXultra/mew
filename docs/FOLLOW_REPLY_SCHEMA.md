# Follow Reply Schema

`mew work --live` and `mew work --follow` write structured cockpit snapshots to
`.mew/follow/latest.json` and `.mew/follow/session-<id>.json`.

The snapshot is a local contract for another model or UI. It includes:

- `schema_version`: currently `1`
- `heartbeat_at`: when the snapshot was written
- `producer.pid`: the process that wrote the snapshot
- `session_id` and `task_id`
- `session_updated_at`: the session timestamp this snapshot observed
- `last_step`, `resume`, `cells`, and `controls`
- `pending_approvals`: top-level pending dry-run write approvals for observers
  with both chat-style `approve_hint`/`reject_hint` and CLI-style
  `cli_approve_hint`/`cli_reject_hint`
- `supported_actions`: the safe reply actions this mew version accepts
- `reply_command`: where to submit a reply file
- `reply_template`: a minimal safe reply payload. When pending approvals exist,
  this template points at the first pending `approve` action; otherwise it uses
  a `steer` action.

To refresh the snapshot without spending a model turn, run either live or
follow with zero steps:

```sh
mew work <task-id> --follow --max-steps 0 --quiet --allow-read .
```

`--quiet` is optional; it only keeps the refresh command's terminal output
compact.

## Reply File

Apply a reply with:

```sh
mew work <task-id> --reply-file .mew/follow/reply.json
```

Print the current session-specific template with:

```sh
mew work <task-id> --reply-schema --json
```

Without an active session, `mew work --reply-schema --json` prints the generic
schema with `session_id`, `task_id`, and `observed_session_updated_at` set to
null. The JSON includes both `docs` and `docs_path`; `docs_path` is useful when
mew is launched from a temporary directory outside the repository.

Minimal payload:

```json
{
  "schema_version": 1,
  "session_id": 1,
  "task_id": 1,
  "observed_session_updated_at": "2026-04-18T00:00:00Z",
  "actions": [
    {"type": "steer", "text": "Inspect the failing test before editing."}
  ]
}
```

Supported actions:

- `steer`: queue one-shot guidance for the next live/follow step.
- `followup`: queue FIFO user input for a later live/follow step.
- `interrupt_submit`: stop at the next model/tool boundary and submit text as the next step.
- `note`: record durable session memory from the observer.
- `stop`: request a stop at the next model/tool boundary.
- `reject`: reject a pending dry-run `write_file` or `edit_file` tool call.
- `approve`: approve and apply a pending dry-run `write_file` or `edit_file` tool call.
- `approve_all`: approve and apply all pending dry-run `write_file` or `edit_file` tool calls.

Example:

```json
{
  "schema_version": 1,
  "session_id": 12,
  "task_id": 34,
  "observed_session_updated_at": "2026-04-18T00:00:00Z",
  "actions": [
    {"type": "note", "text": "Observer saw a risky edit preview."},
    {"type": "reject", "tool_call_id": 7, "reason": "Wrong file."},
    {"type": "stop", "reason": "Pause for human review."}
  ]
}
```

Approval actions may include `allow_write`. If `allow_write` is omitted, mew
reuses the work-session write gates and then falls back to the pending write
path. Reply files cannot set verification commands; verification must come from
the existing work-session defaults or explicit trusted CLI flags passed to
`mew work --reply-file`.

`--reply-file` fails with a nonzero status when there is no matching active
session, when `schema_version` is not `1`, or when
`observed_session_updated_at` is missing or no longer matches the active
session's `updated_at`. After a reply is applied, mew rewrites
`.mew/follow/latest.json` and `.mew/follow/session-<id>.json` with
`mode: "reply_file"` so observers can see the acknowledgement without waiting
for another live/follow step.
