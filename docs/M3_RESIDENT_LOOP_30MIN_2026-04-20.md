# M3 Resident Loop 30-Minute Dogfood

Generated: 2026-04-20 08:40 JST

Command:

```bash
./mew dogfood --scenario resident-loop --duration 1800 --interval 60 --poll-interval 0.2 --workspace /tmp/mew-resident-loop-30min-20260420-0811 --json
```

Result: `pass`

Artifacts:

- workspace: `/tmp/mew-resident-loop-30min-20260420-0811`
- requested duration: `1800.0` seconds
- requested interval: `60.0` seconds
- processed events: `30`
- passive events: `29`
- passive gaps: 28 gaps, mostly `60.0` seconds with one `61.0` second gap

Checks:

- `resident_loop_starts_and_stops`: pass
- `resident_loop_processes_multiple_events`: pass
- `resident_loop_records_passive_effect`: pass
- `resident_loop_compacts_repeated_wait_thoughts`: pass
- `resident_loop_echoes_passive_output`: pass

Interpretation:

This does not prove multi-day resident operation yet, but it is the first
half-hour cadence proof using the parameterized resident-loop dogfood path. It
shows the passive runtime can keep processing spaced passive ticks without
flooding thought memory or losing runtime effects.
