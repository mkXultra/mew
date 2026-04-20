# M5 Close Review 2026-04-20

Status: ready for human close approval.

This document reviews Milestone 5 against the current documented gate. It does
not add new post-hoc requirements. The separate accelerator review in
`docs/REVIEW_2026-04-20_M5_ACCELERATORS.md` is treated as post-M5/M5.1 input,
not as a retroactive M5 gate change.

## Gate Source

`ROADMAP.md` defines M5 done when:

- mew can run at least five consecutive safe self-improvement loops;
- those loops require no human rescue edits; human intervention is limited to
  approval, rejection, redirection, or product judgment;
- at least one loop exercises interruption or failure recovery and resumes
  through Milestone 4 recovery surfaces without manual reconstruction;
- every loop records product-goal rationale, tool/effect journal,
  verification result, approvals, recovery events, and budget outcome in a
  readable audit bundle.

M5 also depends on M3 and M4 entry gates. M4 is already closed. M3 is now
closed by `docs/M3_CLOSE_GATE_2026-04-20.md`.

## Current Machine Evidence

Command:

```bash
./mew self-improve --audit-sequence 307 308 309 310 311
```

Current result:

- status: `candidate_sequence_ready`
- count: `5`
- found: `True`
- consecutive: `True`
- done: `True`
- closed: `True`
- verification: `True`
- recovery: `True`
- no_rescue_review: `True`
- candidate_credit: `True`

Sequence:

| Task | Work session | Verification | Recovery events | Human review | Credit |
|---|---:|---|---:|---|---|
| `#307` | `#286` | passed | 0 | no rescue reviewed | candidate pending M3 |
| `#308` | `#287` | passed | 0 | no rescue reviewed | candidate pending M3 |
| `#309` | `#288` | passed | 0 | no rescue reviewed | candidate pending M3 |
| `#310` | `#289` | passed | 1 | no rescue reviewed | candidate pending M3 |
| `#311` | `#290` | passed | 0 | no rescue reviewed | candidate pending M3 |

## Interpretation

The M5 loop sequence is ready as candidate evidence under the documented gate.
The strongest point is that `#310` includes an actual failed edit/test attempt
that rolled back and was followed by a passing correction, so the sequence is
not only a happy-path run.

The sequence should not be counted as final M5 closure until M3 is honestly
closed. That is the remaining entry-gate dependency, not a weakness in the
M5 sequence itself.

## Do Not Move The Gate

Adversarial verifier, hook-based safety, guardian cache, plan mode, and
sub-agent spawning are valuable follow-up patterns. They should not be added
to this M5 close review retroactively. Doing so would invalidate evidence that
was collected under the active gate and would make M5 non-convergent.

Post-M5/M5.1 likely next work:

- add `mew-adversarial-verifier` as a review-quality skill;
- add hook-based safety boundaries for M5 safety rules.

## Close Decision

Ready for explicit human governance approval.

Completed prerequisites:

1. task `#300` collected the 4h M3 proof artifacts;
2. `./mew proof-summary proof-artifacts/mew-proof-real-4h-20260420-1312 --json --strict` passed;
3. `ROADMAP_STATUS.md` marks M3 done;
4. this review records the M5 sequence as ready under the documented gate.

Final step:

- With explicit human approval, update this review from `ready for human close
  approval` to `passed` and mark M5 `done` in `ROADMAP_STATUS.md`.
