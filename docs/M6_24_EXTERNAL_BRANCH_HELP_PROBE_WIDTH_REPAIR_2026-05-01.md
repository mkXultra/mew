# M6.24 External-Branch Help-Probe Width Repair

Date: 2026-05-01

## Purpose

Repair the `compile-compcert` same-shape speed miss where mew filtered
configure help too narrowly, hid possible external/prebuilt branch wording, and
then spent the remaining wall budget on a heavy version-pinned source-toolchain
build.

This is a generic long-dependency/source-build repair, not a CompCert solver.

## Implementation

`src/mew/work_session.py` now emits
`external_branch_help_probe_too_narrow_before_source_toolchain` when all of the
following are visible:

- the long-dependency final artifact is missing;
- configure/project help was probed through a narrow filter that omitted
  `external`, `use-external`, `prebuilt`, `system`, or `library` terms;
- dependency/API mismatch appeared after that probe;
- a version-pinned source-built toolchain/dependency path started.

The detector covers both same-command probes such as:

```sh
./configure --help | grep -Ei 'coq|menhir|ignore|version'
```

and split probes such as:

```sh
./configure --help > /tmp/help.txt
grep -Ei 'coq|menhir|ignore|version' /tmp/help.txt
```

`src/mew/work_loop.py` updates `LongDependencyProfile` to require broad or
unfiltered help inspection before concluding no source-provided
external/prebuilt branch exists.

## Non-Goals

- Do not encode CompCert, Coq, or Flocq as the solution.
- Do not replace the existing late
  `compatibility_branch_budget_contract_missing` blocker.
- Do not add another lane; this remains implementation-profile guidance.

## Validation

- `uv run pytest --no-testmon tests/test_work_session.py -q`
  - `850 passed, 1 warning, 67 subtests passed`
- `uv run pytest --no-testmon tests/test_acceptance.py -q`
  - `115 passed`
- `uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py`
- `git diff --check`
- `jq -c . proof-artifacts/m6_24_gap_ledger.jsonl`

Review:

- `codex-ultra` session `019de2e0-cb86-7d00-a465-43db81e4f45d`
  - initial review: PASS
  - follow-up after split-probe false-negative fix: PASS

## Next Action

Run one same-shape `compile-compcert` speed_1 on this repair head before
another proof_5 or broad measurement.
