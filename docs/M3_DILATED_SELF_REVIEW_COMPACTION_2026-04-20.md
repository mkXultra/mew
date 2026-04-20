# M3 Dilated Self-Review Compaction

Generated: 2026-04-20 10:07 JST

Trigger:

A 10-minute `resident-loop` run with `--time-dilation 144` completed the
runtime cadence but failed `resident_loop_compacts_repeated_wait_thoughts`.
The state showed a real M3 bloat risk: at multi-hour logical intervals, the
runtime appended the same passive `self_review` decision to deep memory on
every tick, and the thought journal did not compact repeated wait thoughts
because `self_review` was excluded from the passive-wait compaction shape.

Fix:

- repeated passive wait thoughts may compact when the only extra action is a
  passive `self_review` without a proposed task
- duplicate `Self review: ...` deep-memory decisions are not appended when the
  same text is already recent

Verification command:

```bash
./mew dogfood --scenario resident-loop --duration 7 --interval 2 --poll-interval 0.1 --time-dilation 3600 --workspace /tmp/mew-dilation-self-review-compact-20260420 --json
```

Result: `pass`

Artifacts:

- workspace: `/tmp/mew-dilation-self-review-compact-20260420`
- requested duration: `7.0` seconds
- requested interval: `2.0` seconds
- time dilation: `3600.0`
- processed events: `4`
- passive events: `3`
- passive span: `14579.0` logical seconds
- passive gaps: `[7291.0, 7288.0]` logical seconds
- thought journal after run: 2 entries, with the repeated passive wait thought
  compacted to `repeat_count=3`
- deep-memory self-review decisions after run: 1 duplicate-free entry

Interpretation:

This is not a real-time uptime proof. It is a targeted memory-bloat proof for
day-scale logical gaps: repeated passive waiting with recurring self-review no
longer grows thought memory and deep-memory decisions linearly per tick.
