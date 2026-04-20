# M3 Resident Loop 1-Hour Real-Time Proof

Generated: 2026-04-20 12:05 JST

Command:

```bash
docker wait mew-proof-real-1h-20260420-1105
scripts/collect_proof_docker.sh mew-proof-real-1h-20260420-1105
```

Result: `pass`

Container:

- name: `mew-proof-real-1h-20260420-1105`
- image: `mew-proof:real-1h`
- exit code: `0`
- started: `2026-04-20T02:05:20Z`
- finished: `2026-04-20T03:05:23Z`

Artifacts:

- stdout: `proof-artifacts/mew-proof-real-1h-20260420-1105/stdout.log`
- stderr: `proof-artifacts/mew-proof-real-1h-20260420-1105/stderr.log`
- inspect: `proof-artifacts/mew-proof-real-1h-20260420-1105/inspect.json`
- requested duration: `3600.0` seconds
- requested interval: `60.0` seconds
- time dilation: `1.0`
- processed events: `60`
- passive events: `59`
- open questions: `1`
- deferred questions: `0`
- passive span: `3483.0` seconds
- passive gaps: 58 gaps, all `60.0` or `61.0` seconds

Checks:

- `resident_loop_starts_and_stops`: pass
- `resident_loop_processes_multiple_events`: pass
- `resident_loop_records_passive_effect`: pass
- `resident_loop_compacts_repeated_wait_thoughts`: pass
- `resident_loop_echoes_passive_output`: pass
- `resident_loop_reentry_focus_surfaces_next_action`: pass
- `resident_loop_reentry_brief_surfaces_current_state`: pass
- `resident_loop_reentry_context_saves_checkpoint`: pass

Interpretation:

This is supporting M3 evidence, not full closure. It upgrades the resident
cadence proof from 30 minutes to one real hour in an isolated Docker container
with no time dilation, proving that passive ticks, thought compaction, runtime
effects, and post-runtime reentry surfaces continue to work across 60 processed
events. Several-hour and multi-day real-time cadence remain unproven.
