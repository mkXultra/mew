# M6.24 System Service ACT Proof 5 - 2026-04-30

Task: `git-multibranch`

Job:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-system-service-act-git-multibranch-5attempts-20260430-0304/result.json`

## Result

- trials: `5`
- runner errors: `0`
- reward: `5/5`
- pass@2: `1.000`
- pass@4: `1.000`
- pass@5: `1.000`
- runtime: `8m 12s`
- frozen Codex target: `5/5`

## Interpretation

The v0.1 ACT capability-boundary repair reached the frozen Codex target on the
same task shape.

The original `git-multibranch` Batch 6 failure mixed one setup error and
completed-trial failures where mew stopped because required system-service
state lived outside native write roots. After the repair, all five trials
passed without runner errors.

This closes the selected
`system_service_state_permission_contract` / `system_service_state_act_capability_boundary`
repair. It does not by itself reopen broad measurement; the M6.24 controller
requires threshold recheck first.

## Threshold Recheck

Using the same operational convention as the decision ledger:

- original aggregate baseline: roughly `92/210` mew vs `156/210` Codex;
- after `gpt2-codegolf` proof: roughly `97/210`;
- after replacing the original `git-multibranch` `1/5` shape with this `5/5`
  proof: roughly `101/210`.

The aggregate gap remains above the `>20pp` improvement threshold:

- mew: `101/210 = 48.1%`
- Codex: `156/210 = 74.3%`
- absolute gap: about `-26.2pp`

The current Batch 6 measured slice is no longer the main blocker after replacing
`gpt2-codegolf` and `git-multibranch` with their proof results:

- `feal-linear-cryptanalysis`: `5/5`
- `fix-ocaml-gc`: `4/5`
- `git-multibranch`: `5/5`
- `gpt2-codegolf`: `5/5`
- adjusted measured slice: `19/20` vs Codex target `20/20`

## Decision

Stay in `improvement_phase` because the adjusted aggregate gap is still above
threshold. Do not resume broad measurement yet.

Next action:

Reclassify the remaining aggregate gap and select the next generic gap class
from the existing Batch 1-5 evidence. The next repair should not be selected
from Batch 6 alone, because Batch 6 is now near parity after the two closed
same-shape repairs.
