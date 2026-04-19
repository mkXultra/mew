# Follow Reply Schema

`mew work --live` and `mew work --follow` write structured cockpit snapshots to
`.mew/follow/latest.json` and `.mew/follow/session-<id>.json`.

The snapshot is a local contract for another model or UI. It includes:

- `schema_version`: currently `1`
- `heartbeat_at`: when the snapshot was written
- `producer.pid`: the process that wrote the snapshot
- `session_id` and `task_id`
- `session_updated_at`: the session timestamp this snapshot observed
- `latest_context_checkpoint`: a compact reentry checkpoint from
  `mew context --save`, without the raw checkpoint `text`
- `current_git`: the git head/status observed when the snapshot was written
- `last_step`, `resume`, `cells`, and `controls`
- running command/test cells may include bounded stdout/stderr `tail` entries
  while the tool is still active. The same partial output appears in
  `resume.commands[]` with `output_running: true` and `output_updated_at`; when
  the tool finishes, the final command result replaces the running tail.
- `pending_approvals`: top-level pending dry-run write approvals for observers
  with chat-style `approve_hint`/`reject_hint` and CLI-style
  `cli_approve_hint`/`cli_reject_hint` when approval is currently allowed.
  Approvals also expose `defer_verify_hint` and `cli_defer_verify_hint` for
  the test-first case where an observer needs to apply one part of a paired
  change before the final verifier can pass.
  - each approval includes `diff_preview` for terminal display plus a capped
    `diff` for machine review. `diff_truncated` tells observers whether the
    diff hit `diff_max_chars`; when true, refresh/re-read the file before
    approving if the omitted tail matters.
  - approvals may include an advisory `pairing_status`. For `src/mew/**`
    writes, `missing_test_edit` means no changed `tests/**` write/edit has been
    produced in the same work session yet; `ok` points at the paired test tool
    call. Missing-test statuses may include `suggested_test_path`, inferred
    from the source filename, as the first paired-test candidate.
    `missing_test_edit` blocks approval by default; CLI approvals require
    `--allow-unpaired-source-edit`, and reply-file `approve` / `approve_all`
    actions require `"allow_unpaired_source_edit": true` to override it.
  - blocked approvals leave `approve_hint` and `cli_approve_hint` empty, and
    expose `approval_blocked_reason`, `override_approve_hint`, and
    `cli_override_approve_hint` instead. `approve_all` follows the same pattern
    with `approve_all_blocked_reason` and `override_approve_all_hint`.
- `suggested_recovery`: a machine-readable recovery hint when the resume has a
  retryable interrupted read, side-effecting interruption, or replannable model
  turn. When the source is known, `effect_classification` explains the risk
  class such as `no_action`, `verify_pending`, `action_committed`,
  `write_started`, or `rollback_needed`
- `supported_actions`: the safe reply actions this mew version accepts
- `reply_command`: where to submit a reply file
- `reply_template`: a minimal safe reply payload. When pending approvals are
  safe to approve, this template points at an `approve` action. If any visible
  or approve-all-blocking `src/mew/**` source edit still needs a paired test,
  it uses `steer` instead of presenting plain approval.

To refresh the snapshot without spending a model turn, run either live or
follow with zero steps:

```sh
mew work <task-id> --follow --max-steps 0 --quiet --allow-read .
mew work <task-id> --follow --max-steps 0 --quiet --allow-read . --json
```

`--quiet` is optional; it suppresses the refresh command's terminal output while
still writing the snapshot files. With `--json`, zero-step live/follow refreshes
print the structured refresh report while still skipping model calls.

## Inspecting Freshness

Observers can check whether the latest snapshot exists, how old its heartbeat
is, and whether the producing process is still alive:

```sh
mew work --follow-status --json
mew work <task-id> --follow-status --json
```

The command reads `.mew/follow/latest.json`, or the session-specific snapshot
when a task id maps to a work session, and returns `status`, `producer_alive`,
`producer_health`, `heartbeat_age_seconds`, `pending_approval_count`,
`suggested_recovery`, and the snapshot path.
`fresh` means the heartbeat is recent, `working` means the producer is still
alive, `completed` means the producer exited after writing a stopped snapshot,
and `dead` means an old producer disappeared without a stop reason. It exits
nonzero when no snapshot exists. JSON and text output both include the compact
`latest_context_checkpoint` and `current_git` when available, even for absent
snapshots, so an observer can still recover the long-session reentry point.

When the snapshot is absent, stale, or dead, `suggested_recovery.command` points
at the next safe observer command, such as a zero-step refresh or
`mew work <task-id> --session --resume --allow-read . --auto-recover-safe`.
When the snapshot resume already has a recovery plan, that plan wins.
Successful zero-step refreshes write `stop_reason: "snapshot_refresh"` without
spending a model turn.

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
null, `submit_ready: false`, and `schema_only: true`; use it as documentation,
not as a reply payload. The JSON includes both `docs` and `docs_path`;
`docs_path` is useful when mew is launched from a temporary directory outside
the repository.

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

Approval actions may include `allow_unpaired_source_edit: true` to explicitly
override the default block on `src/mew/**` edits without a paired `tests/**`
write/edit in the same work session.
Single `approve` actions may include `defer_verify: true` to apply the write
without running the session verifier immediately. Use this for test-first or
other paired-change flows where a later approval or manual verify will run the
complete check. `approve_all` already defers intermediate approvals and verifies
after the final write.

## Task Helpers

Observers should avoid parsing task text output. The task lifecycle has JSON
surfaces for the common automation path:

```sh
mew task add "Inspect observer flow" --kind coding --json
mew task list --kind coding --json
mew task show <task-id> --json
mew task update <task-id> --status ready --json
mew task done <task-id> --summary "verified" --json
```

Task JSON responses place the full task object under `task` and also expose
top-level `id`, `title`, `status`, `kind`, and `effective_kind` aliases for
simple automation. `task done --json` also returns `completion_summary`. List
responses use `tasks` plus `count`.

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
`mew work --reply-file`, unless a single approval explicitly uses
`defer_verify: true`.

`--reply-file` fails with a nonzero status when there is no matching active
session, when `schema_version` is not `1`, or when
`observed_session_updated_at` is missing or no longer matches the active
session's `updated_at`. After a reply is applied, mew rewrites
`.mew/follow/latest.json` and `.mew/follow/session-<id>.json` with
`mode: "reply_file"` so observers can see the acknowledgement without waiting
for another live/follow step.
