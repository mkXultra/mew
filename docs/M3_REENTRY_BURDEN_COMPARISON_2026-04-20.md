# M3 Reentry Burden Comparison

Generated: 2026-04-20 09:20 JST

Purpose:

Prove a richer M3 reentry-vs-fresh comparison where mew's persisted resume
state changes the first correct action instead of only producing a parity
artifact.

Protocol change:

- `m3-reentry-gate` fresh comparator prompt no longer prints the verifier
  command inline, avoiding a direct leak of the expected recovery token.
- The fresh report template is now `schema_version: 2`.
- The template records `reconstruction_burden` and
  `persistent_advantage_signal` so future comparisons can say what the fresh
  restart had to reconstruct and whether mew's resume would have changed the
  first action.
- `mew_resume_evidence` now records the decisive next action and which context
  is missing from a repository-only restart.

Commands:

```bash
./mew dogfood --scenario m3-reentry-gate --workspace /tmp/mew-m3-reentry-burden-20260420-0922 --json
```

Then a fresh `codex-ultra` comparator followed the generated prompt and wrote:

```text
/private/tmp/mew-m3-reentry-burden-20260420-0922/fresh-codex-ultra-report.json
```

The completed report was merged back into the scenario:

```bash
./mew dogfood --scenario m3-reentry-gate \
  --workspace /tmp/mew-m3-reentry-burden-merged-20260420-0920 \
  --m3-comparison-report /private/tmp/mew-m3-reentry-burden-20260420-0922/fresh-codex-ultra-report.json \
  --json
```

Result:

- scenario: `m3-reentry-gate`
- merged status: `pass`
- fresh tool/model: `Codex CLI` / `codex-ultra`
- context mode: `true_restart`
- manual rebrief: `false`
- repository-only compliance: `true`
- verification exit code: `0`
- comparison choice: `mew_preferred`

Fresh reconstruction burden:

- repository-only steps before first verifier-correct action: `4`
- reading the verifier before first correct action: `true`
- running the verifier before first correct action: `false`
- mew resume would have changed first action: `true`

Persistent advantage signal:

- `mew_saved_reconstruction`: `true`
- `mew_saved_verifier_rerun`: `false`
- `mew_prevented_wrong_first_action`: `true`

Interpretation:

The fresh restart correctly inferred the intended state transition from the
repository, but its first edit used a semantically plausible token that did not
match the verifier. Reading `VERIFY_COMMAND.txt` was needed before the first
verifier-correct action.

mew's resume already preserved the pending dry-run edit, the prior verifier
failure, the queued follow-up, and the exact next action. For this interrupted
task shape, mew is preferred because persistence avoided a wrong first action
and reduced reconstruction.

Limit:

This is still a tiny synthetic README task. It strengthens the M3
context-reconstruction proof, but it does not replace several-hour or multi-day
resident cadence evidence.

Docker Isolation Follow-up:

```bash
MEW_PROOF_NAME=mew-proof-m3-reentry-gate-20260420-1040 \
MEW_PROOF_SCENARIO=m3-reentry-gate \
MEW_PROOF_IMAGE=mew-proof:m3-reentry-gate \
scripts/run_proof_docker.sh
docker wait mew-proof-m3-reentry-gate-20260420-1040
scripts/collect_proof_docker.sh mew-proof-m3-reentry-gate-20260420-1040
```

Result: `pass`

The isolated run proved the mew-side reentry gate and generated fresh CLI
comparison assets with:

- continuity status: `strong`
- continuity score: `9/9`
- pending approval count: `1`
- unresolved failure: `run_tests` exit `7`
- decisive next action: `approve_pending_readme_edit_then_rerun_verifier`
- repo-only missing context:
  - pending dry-run edit diff
  - already-observed verifier failure
  - queued follow-up to approve then verify
- collected artifacts under
  `proof-artifacts/mew-proof-m3-reentry-gate-20260420-1040/`
