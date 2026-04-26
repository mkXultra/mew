# M6.8 Close Gate Audit - 2026-04-26

Milestone: **M6.8 Task Chaining - Supervised Self-Selection**

Verdict: **closed**

## Gate Evidence

- Three consecutive auto-selected bounded handoffs exist in the live selector
  ledger:
  - proposal `#9`: `#635 -> #636`
  - proposal `#11`: `#636 -> #637`
  - proposal `#13`: `#637 -> #638`
- Reviewer approval was recorded for each link before handoff execution.
- `mew task selector-status --json` reported:
  - `approved_handoffs=4`
  - `rejected_attempts=2`
  - `blocked_proposals=6`
  - `proof_summary.contiguous_chain_length=4`
  - `proof_summary.has_three_consecutive_handoffs=true`
- Each proof-chain implementation was mew-first:
  - `#635`: approved selector handoff records
  - `#636`: selector proof status CLI
  - `#637`: joined recent handoff chain
  - `#638`: consecutive proof summary
- Validation for the proof-chain slices passed:
  - `uv run pytest -q tests/test_commands.py --no-testmon`
  - `uv run pytest -q tests/test_tasks.py tests/test_commands.py --no-testmon`
  - `uv run ruff check src/mew/commands.py src/mew/cli.py tests/test_commands.py`
  - `git diff --check`

## Rejection And Guard Evidence

- Reviewer rejection occurred during M6.8 implementation:
  - `#631` rejected a cosmetic output-only patch before the durable selector
    ledger shipped.
  - `#633` rejected two patches, including one that allowed approving blocked
    governance proposals.
  - `#635` rejected a patch that omitted the required `next_command` handoff
    evidence.
- The next approved tasks continued the chain after rejection without changing
  the approval contract.
- Unapproved execution was rejected and logged:
  - proposal `#7` was executed before approval and recorded a rejected
    `selector_execution_attempt`.
- Blocked/governance proposal execution was rejected and logged:
  - proposal `#5` recorded a blocked execution rejection.
- Automatic selection skips blocked governance candidates. Explicit blocked
  candidates remain reviewer-visible and cannot be approved.

## Scope And Drift

- Selector-owned output did not author roadmap-status, milestone-close, or
  governance changes. Those remain reviewer-owned.
- The proof chain stayed within task/coding CLI surfaces:
  `src/mew/tasks.py`, `src/mew/commands.py`, `src/mew/cli.py`, and focused
  tests.
- M6.8.5 curriculum, habit, preference, and memory-signal policy was not
  implemented in M6.8. Optional fields remain reserved for M6.8.5.

## Caveats

- The oldest handoff in the live contiguous summary is proposal `#7`
  (`#634 -> #635`), which was an explicit candidate. The latest three links
  (`#9`, `#11`, `#13`) are automatic selector choices and satisfy the close
  gate.
- M6.8 proves safe reviewer-approved chaining, not intelligent task selection.
  Intelligent selector policy moves to M6.8.5.

## Close Decision

M6.8 is closed because the supervised selector can propose, approve, reject or
block, hand off, and continue a bounded mew-first implementation chain without
unapproved dispatch or supervisor product rescue.
