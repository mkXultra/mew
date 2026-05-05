# M6.24 Long-Build Clean Closeout State Repair

Date: 2026-05-02

## Context

The same-shape `compile-compcert` speed_1 rerun after the acceptance closeout
evidence repair externally passed:

- Harbor mean: `1.0`
- runner errors: `0`
- trial reward: `1.0`
- command transcript exit code: `0`
- `mew work` exit code: `0`
- `mew work` stop reason: `finish`

Artifact root:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-acceptance-closeout-compile-compcert-1attempt-20260502-0255`

The remaining defect was internal state projection: top-level
`resume.long_build_state` still reported an old
`runtime_install_before_build` / `runtime_install_before_runtime_library_build`
failure after command evidence 10 had successfully built the runtime library,
installed default runtime/config files, and ran a default compile/link/run
smoke.

## Failure Shape

The successful final proof command was not reduced as a full final-contract
proof because two generic evidence recognizers were too narrow:

- source authority output used practical acquisition transcript lines such as
  `url=https://...` and `CHOSEN https://...`
- the required artifact was invoked inside an `if /path/to/artifact ...; then`
  shell segment rather than as the first command token

That left:

- `source_authority`: `unknown`
- latest attempt stage: `artifact_proof` instead of `default_smoke`
- `default_smoke`: `blocked`
- stale `strategy_blockers` and `current_failure`

## Repair

The reducer now accepts these generic evidence shapes:

- direct source authority lines beginning with `url=https://`
- selected-source lines beginning with `CHOSEN https://`
- direct source authority only when that URL matches a strict non-Python
  source fetch in the command transcript
- required artifact invocation as a real compile/link smoke command, including
  the normal `test -x artifact && artifact source -o probe && probe` shell
  chain and guarded `if artifact ...; then ... else ... exit 1; fi`

The strict source fetch path requires `set -e`, rejects masked fetch failures,
rejects URL-bearing HEAD/no-download probes and partial/range probes, and
intentionally does not accept Python heredoc source fetches as direct source
authority. The default-smoke path rejects `echo`/`printf` spoofing, negated
invocations, unguarded `if` wrappers, `elif`/`while`/`until` wrappers, skipped
short-circuit forms, masked forms such as `artifact ... || true`, and
semicolon/newline masking unless `set -e` protects the transcript. This also
applies to later semicolon/newline masking after an `artifact && probe` smoke
chain. Piped artifact compile or follow-up probe segments are rejected outright
because `set -e` alone does not prove the left side of a pipeline succeeded.
Backgrounded artifact/probe execution is also rejected, while shell fd
redirections such as `2>&1` remain valid.

## Validation

Before final same-shape rerun:

- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py`: `139 passed`
- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py -k 'source_authority or if_wrapped or runtime_link_failure_output or default_smoke or dependency_generation'`: `100 passed, 39 deselected`
- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py -k 'runtime_install or default_runtime_link or default_smoke or long_build'`: `155 passed, 847 deselected`
- `uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`
- `git diff --check`

The regression suite includes a later-failure protection case so a later
runtime/link failure is not cleared just because an earlier smoke succeeded.
It also includes adversarial source-authority and default-smoke spoof cases
for printed URLs, mismatched fetched URLs, masked fetches, no-errexit source
fetches, HEAD/no-download probes, partial/range source probes, Python heredoc
spoofing, short-circuit skipped smokes, and masked smoke failures.

## Next Gate

Run exactly one same-shape `compile-compcert` speed_1 after this repair.

Do not run proof_5 or broad measurement until the rerun records all of:

- Harbor reward `1.0`
- runner errors `0`
- command transcript exit code `0`
- `mew-report.json` clean internal closeout
- no stale `resume.long_build_state.current_failure`
- no active stale `strategy_blockers` for the resolved runtime/toolchain/source
  blockers
