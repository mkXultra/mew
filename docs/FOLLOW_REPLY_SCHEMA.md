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
- `reply_command`: where to submit a reply file
- `reply_template`: a minimal safe reply payload

## Reply File

Apply a reply with:

```sh
mew work <task-id> --reply-file .mew/follow/reply.json
```

Print the current session-specific template with:

```sh
mew work <task-id> --reply-schema --json
```

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
- `note`: record durable session memory from the observer.
- `stop`: request a stop at the next model/tool boundary.
- `reject`: reject a pending dry-run `write_file` or `edit_file` tool call.

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

`--reply-file` fails with a nonzero status when there is no matching active
session, when `schema_version` is not `1`, or when
`observed_session_updated_at` is missing or no longer matches the active
session's `updated_at`. After a reply is applied, mew rewrites
`.mew/follow/latest.json` and `.mew/follow/session-<id>.json` with
`mode: "reply_file"` so observers can see the acknowledgement without waiting
for another live/follow step.
