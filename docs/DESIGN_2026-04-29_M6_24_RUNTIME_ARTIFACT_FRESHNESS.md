# DESIGN 2026-04-29 - M6.24 Runtime Artifact Freshness

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> runtime_artifact_cleanup_external_verifier_alignment -> rerun make-doom-for-mips same shape`

## Trigger

The hard-runtime same-shape rerun in
`docs/M6_24_HARD_RUNTIME_RERUN_2026-04-29.md` stayed 0/5, but the best trial
reached a stronger state than prior attempts:

- built `/app/doomgeneric_mips`
- ran exact `node vm.js`
- observed Doom startup stdout
- verified `/tmp/frame.bmp` as a valid 640x400 32bpp BMP
- external verifier reached 2/3

The remaining miss was caused by verifier freshness. The agent's self-check
left `/tmp/frame.bmp` in place. The external verifier waits until that path
exists, waits one second, then terminates the fresh VM process. Since the stale
frame existed before the verifier started, stdout was captured too early.

## Architecture Fit

Decision: `implementation_profile`.

This repair stays in the authoritative implementation/tiny lane. It strengthens
the finish policy for generated runtime artifacts and external verifier
alignment, while preserving the same coding authority: produce the task change,
run or preserve verifier evidence, and block false completion.

No new lane is introduced because artifact freshness is a verifier/finish
contract inside the implementation lane. A future verifier helper lane may
audit these proofs, but the write-capable owner remains implementation/tiny.

## v0 Repair

Implemented in:

- `src/mew/acceptance.py`
- `src/mew/work_session.py`
- `src/mew/work_loop.py`

Behavior:

- task text that combines a fresh runtime command with generated `/tmp/...`
  artifacts is recognized as a runtime artifact freshness surface
- `acceptance_finish_blocker()` blocks `task_done=true` when a completed
  self-check created a runtime `/tmp/...` artifact and no later cleanup command
  is visible
- work-session resume now surfaces
  `stale_runtime_artifact_risk` with the artifact path, source tool, and cleanup
  guidance
- the THINK prompt tells the model to preserve self-check evidence, then clean
  stale runtime artifacts before finish unless the task explicitly requires the
  artifact to pre-exist

This is generic arbitrary-workspace behavior. It applies to frames, screenshots,
runtime logs, sockets, pid files, and similar generated verifier artifacts. It
does not encode Doom or Terminal-Bench-specific logic.

## v0.1 Discovered Artifact Repair

The `make-mips-interpreter` speed rerun in
`docs/M6_24_HARD_PROFILE_MAKE_MIPS_SPEED_RERUN_2026-04-29.md` exposed a narrower
miss: the task text described generated frames but did not name `/tmp/frame.bmp`.
mew discovered `/tmp/frame.bmp` from source and self-check output, left it in
place, and the external verifier terminated the fresh `node vm.js` process too
early because the stale frame already existed.

The guard now also infers runtime `/tmp/...` artifacts from verified checks and
completed tool output when the task text has the fresh runtime / generated
artifact shape. This keeps the rule generic while covering tasks where the
artifact path is discovered from source rather than stated by the user.

## v0.2 Deferred Verify Cleanup

The v0.1 speed rerun in
`docs/M6_24_DISCOVERED_ARTIFACT_CLEANUP_RERUN_2026-04-29.md` showed a second
handoff miss: after tool #30 successfully ran exact `node vm.js`, emitted the
expected `I_InitGraphics` stdout, and wrote `/tmp/frame.bmp`, the session hit
`wall_timeout` before a final cleanup/finish turn. Because
`mew work --oneshot --defer-verify` then returned to the external harness with
the stale frame still present, the fresh verifier process was terminated too
early again.

The repair is deliberately outside Terminal-Bench:

- only `mew work --oneshot --defer-verify` performs this cleanup;
- only `/tmp/...` artifacts already surfaced by `stale_runtime_artifact_risk`
  are removed;
- the final one-shot report records `post_run_cleanup`;
- if every stale artifact was removed, the final resume clears
  `stale_runtime_artifact_risk` before handoff.

This protects external verifier freshness even when the model has no final turn
left after a successful runtime self-check.

## v0.3 Report-Step Cleanup Fallback

The v0.2 same-shape speed rerun in
`docs/M6_24_DEFER_VERIFY_CLEANUP_SPEED_RERUN_2026-04-29.md` showed the next
handoff miss. mew finished normally after exact `node vm.js` succeeded and
after inspecting valid `/tmp/frame.bmp` plus `/tmp/frame_000001.bmp`, but the
final resume had no `stale_runtime_artifact_risk`, so `post_run_cleanup` was
empty and the external verifier again observed a stale frame too early.

The cleanup path now falls back to the final one-shot `work_report`:

- collect completed `tool_call` entries from `work_report.steps`;
- build the same generic stale-runtime-artifact risk from task text and tool
  output;
- remove only `/tmp/...` artifacts found by that risk detector when
  `--defer-verify` is active.

The marker set also recognizes common report shapes from runtime frame
inspection:

- `saved /tmp/`
- `exists size=`

This keeps the authority model unchanged: the implementation lane may verify
and inspect runtime artifacts, but one-shot handoff cleans fresh-verifier
artifacts even if the resume bundle missed the risk.

## v0.4 Runtime Visual Artifact Quality Contract

The five-trial make-mips rerun showed that freshness cleanup was no longer the
only blocker. Some trials finished with valid frame artifacts but still failed
the external verifier because the frame/output was not semantically correct:

- accepted `320x200x32 BMP` self-consistency when the verifier expected
  `640x400`;
- accepted frame creation while missing the expected Doom boot stdout marker;
- relied on artifact existence, nonzero pixels, valid headers, or matching
  self-generated outputs.

The guard now treats runtime frame, screenshot, rendered image, and framebuffer
tasks with explicit expected/correct/check language as a quality-contract
surface. Before `task_done=true`, such tasks must cite completed grounding
evidence for at least one externally meaningful property:

- expected dimensions or resolution;
- reference similarity or comparison;
- exact stdout, boot marker, screen-size marker, or equivalent runtime marker.

This is still generic implementation-lane behavior. It does not encode Doom,
Terminal-Bench, or `make-mips-interpreter`; it blocks false completion when a
runtime visual artifact exists but the observed properties are only format or
self-consistency checks.

## v0.5 External Artifact Path And Cleanup Contract

The v0.4 five-trial proof in
`docs/M6_24_VISUAL_QUALITY_PROOF_5_2026-04-29.md` showed that the visual-quality
miss moved but the verifier handoff still had two generic holes:

- one successful internal run validated `/tmp/frame.bmp`, but the validator
  output shape was `BMP ok: frames/... and /tmp/frame.bmp ...`, so deferred
  cleanup did not remove the stale `/tmp` artifact before the external verifier
  handoff;
- one finish validated `frames/frame000001.bmp` and a root `frame000001.bmp`
  copy while the runtime banner named `/tmp/frame.bmp` as the verifier-read
  artifact path.

The repair keeps the same implementation-lane boundary:

- runtime artifact discovery now recognizes expected verifier paths from
  output such as `Frames will be saved to /tmp/...` without treating that as a
  created stale artifact by itself;
- runtime artifact creation/cleanup detection recognizes validator lines such
  as `BMP ok: frames/... and /tmp/...`;
- finish gating now blocks when the discovered verifier-read `/tmp/...` path is
  not cited by acceptance evidence, even if a semantically valid sibling frame
  exists elsewhere;
- THINK guidance explicitly tells the model not to finish when it only proved
  `frames/foo`, `output/foo`, or a root copy while the verifier reads
  `/tmp/foo`.

This is still not Terminal-Bench-specific. It is a general handoff rule for
fresh external verifiers that read generated runtime artifacts from `/tmp`.

## Validation

Focused validation:

```sh
uv run pytest tests/test_acceptance.py -k 'runtime_artifact or complete_verified_checks' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'stale_runtime_artifact or runtime_contract_gap or work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py src/mew/work_loop.py tests/test_acceptance.py tests/test_work_session.py
```

Observed:

- `3 passed, 48 deselected`
- `4 passed, 767 deselected`
- `ruff`: all checks passed

Additional v0.1 validation:

```sh
uv run pytest tests/test_acceptance.py -k 'stale_runtime_artifact or runtime_command_pass_without_artifact' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'stale_runtime_artifact or final_verifier_state_transfer' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py tests/test_acceptance.py tests/test_work_session.py
```

Observed:

- `4 passed, 49 deselected`
- `4 passed, 769 deselected`
- `ruff`: all checks passed

Additional v0.2 validation:

```sh
uv run pytest tests/test_acceptance.py -k 'stale_runtime_artifact or runtime_command_pass_without_artifact' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'stale_runtime_artifact or final_verifier_state_transfer or oneshot_cleanup' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py src/mew/commands.py tests/test_acceptance.py tests/test_work_session.py
```

Observed:

- `4 passed, 49 deselected`
- `6 passed, 769 deselected`
- `ruff`: all checks passed

Additional v0.3 validation:

```sh
uv run pytest tests/test_acceptance.py -k 'stale_runtime_artifact or runtime_command_pass_without_artifact' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'stale_runtime_artifact or final_verifier_state_transfer or oneshot_cleanup' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py src/mew/commands.py tests/test_acceptance.py tests/test_work_session.py
```

Observed:

- `4 passed, 49 deselected`
- `7 passed, 769 deselected`
- `ruff`: all checks passed

Additional v0.4 validation:

```sh
uv run pytest tests/test_acceptance.py -k 'runtime_visual_artifact or runtime_artifact or runtime_command_pass_without_artifact' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_loop.py tests/test_acceptance.py tests/test_work_session.py
git diff --check
jq -c . proof-artifacts/m6_24_gap_ledger.jsonl
```

Observed:

- `7 passed, 49 deselected`
- `1 passed, 781 deselected`
- `ruff`: all checks passed
- `git diff --check`: passed
- gap ledger parsed as JSON Lines

Additional v0.5 validation:

```sh
uv run pytest tests/test_acceptance.py -k 'runtime_artifact or runtime_command_pass_without_artifact' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'stale_runtime_artifact or final_verifier_state_transfer or oneshot_cleanup or work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py src/mew/work_loop.py tests/test_acceptance.py tests/test_work_session.py
```

Observed:

- `5 passed, 52 deselected`
- `9 passed, 774 deselected`
- `ruff`: all checks passed

## Same-Shape Rerun Gate

Next proof should rerun:

`terminal-bench/make-mips-interpreter`

Accept as improved only if:

- no stale runtime artifact finish is accepted;
- `post_run_cleanup` removes self-verifier `/tmp/...` artifacts before external
  verifier handoff when `--defer-verify` is active;
- the trial no longer accepts format-only or self-consistent visual artifacts
  as proof for expected rendered output;
- acceptance cites grounded expected dimensions/resolution, reference
  similarity, or exact stdout/boot markers before finish;
- reward improves, or the external verifier failures move away from visual
  artifact quality / stdout-contract evidence;
- finish no longer accepts sibling frame paths such as `frames/...` or root
  copies when the verifier-read runtime artifact path is `/tmp/...`;
- `post_run_cleanup` catches validator output that mentions a generated
  `/tmp/...` artifact, including `BMP ok: ... and /tmp/...` shapes.

If the rerun remains 0/1 but fails on a different concrete verifier condition,
record that new condition in `proof-artifacts/m6_24_gap_ledger.jsonl` before
choosing another repair.
