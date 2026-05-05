# M6.24 Post-Loop Source Signal Repair

Date: 2026-05-02 JST

## Goal

Allow `source_authority` to be satisfied for nonterminal long-build commands
when source acquisition completed correctly, but later build/toolchain work
failed.

This is not a `compile-compcert` solver. It is a generic reducer rule for
archive-based source acquisition.

## Repair

`src/mew/long_build_substrate.py` now accepts nonterminal validated archive
source evidence only when the command has an ordered source-acquisition proof:

1. fetch authoritative archive
2. hash the exact fetched archive
3. validate archive structure
4. extract the archive
5. move the extracted source root
6. only then allow later build failure

The nonterminal path rejects common spoof/ordering failures:

- pre-fetch static or dynamic hash output
- heredoc, `echo`, `printf`, `python`, `cat`, and same-line stdout spoofing
- fake hash output after fetch but before the real hash command
- build/failure commands before hash, validation, extraction, or source-root move
- failable post-hash setup such as `test -f missing`
- command-substitution assignments such as `probe=$(false)`
- nounset assignments such as `probe=$UNSET_SOURCE_PROOF_SENTINEL`
- builtins with arbitrary/failable arguments such as `export -z`

The post-hash safe setup allowlist is intentionally conservative. Some real
scripts may remain false negatives if they run harmless `mkdir` or `cd` after
hashing and before validation. That is acceptable here; false negatives are
safer than unsafe source-authority approvals.

## Validation

Local validation:

- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py -k 'source_authority'`
  - `132 passed, 74 deselected`
- `uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`
  - passed
- `git diff --check`
  - passed
- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py`
  - `1201 passed, 1 warning, 67 subtests passed`

Review:

- codex-ultra session `019de5fe-2059-7bd2-8853-4184e3e1f472`
- Final status: `APPROVE`

## Next Action

Commit this repair, then rerun one same-shape `compile-compcert` speed_1.

Close gate remains:

- Harbor reward `1.0`
- runner errors `0`
- command transcript exit `0`
- `mew-report.work_exit_code=0`
- `source_authority=satisfied`
- `current_failure=null`
- `strategy_blockers=[]`

