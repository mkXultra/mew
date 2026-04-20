# M3 Aged Reentry 7-Day Dogfood

Generated: 2026-04-20 09:55 JST

Command:

```bash
./mew dogfood --scenario day-reentry --workspace /tmp/mew-aged-reentry-7day-20260420 --json
```

Result: `pass`

Artifacts:

- workspace: `/tmp/mew-aged-reentry-7day-20260420`
- synthetic age: `7` days
- session created at: `2026-04-12T00:55:17Z`
- session updated at: `2026-04-12T01:31:17Z`
- observed inactive hours: `191.4`

Checks:

- `day_reentry_focus_surfaces_aged_active_session`: pass
- `day_reentry_focus_text_is_copy_paste_reentry`: pass
- `day_reentry_resume_restores_memory_and_world_state`: pass
- `day_reentry_activity_preserves_old_work_events`: pass

Interpretation:

This proves the synthetic aged reentry path at week scale. It does not prove
real week-long process uptime. It does prove that a work session aged by more
than seven days can still surface stale age, unresolved verifier risk, working
memory, notes, touched file world-state, and copy-paste resume/follow controls.

Boundary:

The scenario synthesizes old timestamps in `.mew/state.json` and then exercises
normal CLI surfaces. It should count toward the accelerated M3 proof pyramid's
aged-reentry layer, not toward OS/process stability or external API TTL proof.
