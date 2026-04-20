# M3 Time Dilation Foundation

Generated: 2026-04-20 09:50 JST

Command:

```bash
./mew dogfood --scenario resident-loop --duration 7 --interval 2 --poll-interval 0.1 --time-dilation 24 --workspace /tmp/mew-time-dilation-smoke-20260420 --json
```

Result: `pass`

Artifacts:

- workspace: `/tmp/mew-time-dilation-smoke-20260420`
- requested duration: `7.0` seconds
- requested interval: `2.0` seconds
- time dilation: `24.0`
- processed events: `4`
- passive events: `3`
- passive gaps: `[49.0, 51.0]` logical seconds

Checks:

- `resident_loop_starts_and_stops`: pass
- `resident_loop_processes_multiple_events`: pass
- `resident_loop_records_passive_effect`: pass
- `resident_loop_compacts_repeated_wait_thoughts`: pass
- `resident_loop_echoes_passive_output`: pass

Interpretation:

This is a foundation proof, not an M3 closure proof. It confirms that
`resident-loop` can run with real scheduling while mew's state timestamps use
dilated logical time. That makes the accelerated M3 proof pyramid practical:
longer resident-loop runs can now compress day-scale or week-scale timestamp
aging into shorter real-time dogfood sessions.

Boundary:

Runtime scheduling remains real time. The dilation path affects mew logical
timestamps exposed through `now_iso()` and `now_date_iso()` in subprocesses
launched by the dogfood scenario. External CLI/API TTLs, file mtimes, process
timers, and OS-level waits are still real time.
