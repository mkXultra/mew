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

Fresh Comparator on Isolated Artifact:

A fresh `codex-ultra` comparator was then run from the generated fresh restart
workspace:

```text
proof-workspace/mew-proof-m3-reentry-gate-20260420-1040/m3-fresh-cli-restart-workspace
```

It wrote:

```text
proof-workspace/mew-proof-m3-reentry-gate-20260420-1040/.mew/dogfood/fresh-codex-ultra-docker-report.json
```

The report was merged with:

```bash
./mew dogfood --scenario m3-reentry-gate \
  --workspace proof-workspace/mew-proof-m3-reentry-gate-merged-20260420-1045 \
  --m3-comparison-report proof-workspace/mew-proof-m3-reentry-gate-20260420-1040/.mew/dogfood/fresh-codex-ultra-docker-report.json \
  --json
```

Merged result: `pass`

Important caveat:

- `manual_rebrief_needed=true`
- `repository_only_compliance=false`
- reason: the fresh comparator ran git metadata commands before realizing the
  git root was outside the current work folder
- it did not inspect parent `.mew` or the report template before the independent
  attempt, but this is still recorded as a strict-rule violation
- the Docker-specific verifier path `/mew/.venv/bin/python` was not available
  on the host; the same verifier predicate passed with `python3`

Fresh reconstruction burden from this run:

- comparison choice: `mew_preferred`
- repository-only steps before first verifier-correct action: `5`
- needed to read verifier before first correct action: `true`
- needed to run verifier before first correct action: `false`
- mew resume would have changed first action: `true`
- persistent advantage:
  - `mew_saved_reconstruction=true`
  - `mew_saved_verifier_rerun=true`
  - `mew_prevented_wrong_first_action=true`

Interpretation of this comparator:

The result is useful but not clean enough to close M3 by itself. It confirms
the core pattern again: the fresh restart inferred the semantic direction from
README.md, but made a wrong first edit before reading the verifier. mew had the
pending approval, failed verifier, queued follow-up, exact next action, and
verifier context already preserved.

Strict Fresh Comparator:

The comparator was repeated from a non-git `/tmp` workspace with stricter rules:

- use only `README.md` and `VERIFY_COMMAND.txt` before the independent attempt
- do not run git commands
- do not inspect parent directories
- inspect the report template only after the README recovery and verifier pass

Workspace:

```text
/tmp/mew-m3-fresh-strict-20260420-1049
```

Durable report copy:

```text
docs/M3_FRESH_STRICT_COMPARATOR_2026-04-20.json
```

Merged result:

```bash
./mew dogfood --scenario m3-reentry-gate \
  --workspace proof-workspace/mew-proof-m3-reentry-gate-strict-merged-20260420-1052 \
  --m3-comparison-report /tmp/mew-m3-fresh-strict-20260420-1049/fresh-codex-ultra-strict-report.json \
  --json
```

Result: `pass`

Clean comparator evidence:

- `manual_rebrief_needed=false`
- `repository_only_compliance=true`
- `verification_exit_code=0`
- comparison choice: `mew_preferred`
- repository-only steps before first correct action: `2`
- needed to read verifier before first correct action: `true`
- needed to run verifier before first correct action: `false`
- mew resume would have changed first action: `true`
- `mew_saved_reconstruction=true`
- `mew_saved_verifier_rerun=true`
- `mew_prevented_wrong_first_action=false`

Interpretation:

This is the cleanest M3 comparator in this sequence. Fresh CLI did not make a
wrong turn, but it still needed two repository-only reads before the first
correct action and depended on `VERIFY_COMMAND.txt` to recover the exact marker.
mew's resume already held the pending edit, prior failed verifier, queued
follow-up, and exact next action, so the comparator still chose `mew_preferred`.
