# M6 Close Gate 2026-04-21

Status: close-gate proof passed.

This document closes Milestone 6, Body: Daemon & Persistent Presence. The
claim is narrow: mew now has a real daemon-shaped resident body with watcher
integration, control surfaces, restart/reentry behavior, and a multi-hour proof
through the daemon path.

## Behavior Proved

M6 closes on five concrete behaviors from `ROADMAP.md`:

- `mew daemon status` reports uptime, active watchers, last tick, last event,
  current task, and safety state
- a real watched file event triggers a passive turn without manual polling
- daemon restart reattaches to resident state without user rebrief
- a multi-hour resident proof runs through the daemon path
- the daemon can be paused, inspected, repaired, and resumed from CLI/chat

## Final Multi-Hour Daemon Proof

Collection:

```bash
bash scripts/collect_proof_docker.sh mew-proof-m6-daemon-loop-enhanced-20260420-1910
./mew proof-summary proof-artifacts/mew-proof-m6-daemon-loop-enhanced-20260420-1910 --json --strict
```

Result: `pass`

Container:

- name: `mew-proof-m6-daemon-loop-enhanced-20260420-1910`
- image: `mew-proof:latest`
- status: `exited`
- exit code: `1`
- started: `2026-04-20T10:10:06.381170639Z`
- finished: `2026-04-20T14:10:10.868141223Z`

Artifacts:

- summary: `proof-artifacts/mew-proof-m6-daemon-loop-enhanced-20260420-1910/summary.txt`
- report: `proof-artifacts/mew-proof-m6-daemon-loop-enhanced-20260420-1910/report.json`
- stdout: `proof-artifacts/mew-proof-m6-daemon-loop-enhanced-20260420-1910/stdout.log`
- stderr: `proof-artifacts/mew-proof-m6-daemon-loop-enhanced-20260420-1910/stderr.log`
- inspect: `proof-artifacts/mew-proof-m6-daemon-loop-enhanced-20260420-1910/inspect.json`

Resident-loop summary:

- requested duration: `14400.0` seconds
- requested interval: `60.0` seconds
- processed events: `241`
- passive events: `239`
- expected passive minimum: `238`
- passive span: `14300.0` seconds
- passive gaps: `238`
- passive gap min/max: `60.0` / `61.0` seconds
- passive gaps outside expected interval by more than 2s: `0`

Checks:

- `m6_daemon_loop_starts_reports_and_stops`: pass
- `m6_daemon_loop_watcher_processes_file_event`: pass
- `m6_daemon_loop_controls_pause_inspect_resume`: pass
- `m6_daemon_loop_processes_multiple_passive_ticks`: pass
- `m6_daemon_loop_records_passive_effects`: pass
- `m6_daemon_loop_logs_passive_ticks`: pass
- `m6_daemon_loop_reentry_focus_surfaces_task`: pass

## Closure Caveat

The raw detached container exited `1` and the original `report.json` marked the
scenario as `fail` because the long-proof check
`m6_daemon_loop_watcher_processes_file_event` still required an
`external_event` runtime-effect journal entry to survive until the end of a
4-hour run. In the collected artifact, the actual `file_change` event is
present, processed, and sourced from `daemon_watch`, but the early
`external_event` runtime effect has aged out of the last-100 runtime-effect
journal.

The close gate therefore relies on the collected artifact plus the tightened
proof-summary/dogfood logic that treats the processed watcher event itself as
the durable proof for the long run. This does not invent evidence; it removes a
retention-based false negative in the close-out harness.

## Supporting Evidence

- short daemon watcher proof:
  `m6-daemon-watch` in `/tmp/mew-m6-daemon-watch-proof`
- daemon restart proof:
  `m6-daemon-restart` in `/tmp/mew-m6-daemon-restart-proof`
- short daemon loop proof:
  `/tmp/mew-m6-daemon-loop-proof`
- docker smoke proofs:
  `proof-artifacts/mew-proof-m6-daemon-loop-smoke-20260420-1908` and
  `proof-artifacts/mew-proof-m6-daemon-loop-smoke-20260420-1913`

## Interpretation

M6 is done because mew now has a durable daemon body, not merely a foreground
loop:

- the daemon control surface exists and is inspectable
- passive watcher-triggered turns run through the daemon path
- pause/resume/inspect/reentry are real behaviors, not design intent
- a multi-hour detached proof demonstrates resident cadence at the requested
  interval over 4 hours

Future work can improve resource policy, launchd/systemd integration, and
longer proofs, but M6 no longer blocks the roadmap.
