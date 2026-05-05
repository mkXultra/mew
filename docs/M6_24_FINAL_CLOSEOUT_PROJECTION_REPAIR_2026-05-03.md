# M6.24 Final Closeout Projection Repair - 2026-05-03

## Trigger

The non-timeout source retry same-shape `compile-compcert` rerun passed
externally:

- Harbor reward: `1/1`
- runner exceptions: `0`
- `mew-report.work_exit_code`: `0`
- `work_report.stop_reason`: `finish`
- external verifier: `3 passed`

Internal `resume.long_build_state` still stayed pessimistic:

- `status=blocked`
- `source_authority=unknown`
- `default_smoke=unknown`
- stale `dependency_generation_required` blocker from earlier evidence

codex-ultra classified this as:

`final_artifact_and_default_smoke_closeout_not_projected_to_long_build_state`

and recommended repairing the reducer/closeout layer now, before `proof_5`.

## Repair

Generic reducer/closeout repair, with no CompCert-specific recipe:

1. Safe default-smoke shell guards are accepted.
   `cmd || exit 1` and `cmd || { ... exit 1; }` are now treated as terminal
   failure guards rather than masking, while `|| true`, missing exit guards,
   pipelines without `pipefail`, backgrounding, and later mutation remain
   rejected.

2. Selected authoritative source archive acquisition is recognized.
   A strict successful command that selects an authoritative archive URL,
   downloads to a versioned local archive, hashes it, lists it, and extracts it
   can satisfy source authority even when earlier candidate probes printed
   failed URLs. After codex-ultra review, this was tightened so the selected
   authoritative URL must be correlated with the actual fetch path; printing an
   authoritative-looking URL next to a non-authoritative fetch is rejected.
   The selected marker must be followed immediately by the top-level `curl` or
   `wget` fetch using the selected variable; any intervening command breaks the
   correlation. This rejects reassignment, `VAR+=...`, `readonly`, `unset`,
   `read`, `printf -v`, and other unmodeled mutation forms.
   Loop-alias marker commands must not contain authoritative literal URLs; the
   selected URL must be output through the fetch variable, and the marker
   command must be a `printf` or `echo` readback that may not reference other
   shell variables or redirect/pipe/background stdout. `printf -v` marker
   commands are rejected because they write to a variable rather than stdout.
   Multiple selected/chosen marker commands are rejected because
   output-to-command attribution becomes ambiguous. Command substitution,
   backticks, and process substitution are rejected in selected marker commands.
   If a selected loop alias receives a non-empty top-level reassignment or
   unmodeled shell-state mutation before the accepted marker/fetch pair, the
   selected-output-to-fetch correlation is discarded. The same lifetime rule is
   applied inside the selected loop body: aliases mutated after
   `alias="$loop_variable"` are not trusted, and a loop variable explicitly
   reassigned before the loop-body fetch is not trusted.
   `while read ... done < "$candidate_file"` source-candidate inputs are
   resolved from segment-ordered assignment state at the loop boundary, so a
   stale candidate-file binding cannot survive a prior mutation.
   Direct `curl` / `wget` fetch correlation requires exactly one remote source
   URL for the output path; mixed authoritative/non-authoritative URL segments
   are rejected.
   Heredoc candidate-file writes preserve overwrite vs append order: `>` and
   non-append `tee` replace older content, while `>>` / `tee -a` append.
   A while-read candidate file is trusted only when the first effective URL is
   authoritative; later appended authoritative URLs do not prove the fetched
   candidate when the loop may break on the first entry.
   For `for ... in` candidate lists, the first effective URL must be
   authoritative. Conditional fetch/validation guards alone do not prove an
   earlier non-authoritative candidate failed.
   Loop-backed `curl` / `wget` fetches must fetch exactly one effective remote
   source, and that source must be the trusted loop variable/candidate. Mixed
   literal-plus-variable remote fetches are rejected for both `for` and
   `while read` acquisition paths. `curl --url` and `curl --url=...` are
   counted as effective source operands, not ignored as ordinary options.
   `curl -K` / `curl --config` source acquisition is conservatively rejected
   for source-authority projection because the external config can inject a URL
   outside the visible command operands. `wget -i` / `wget --input-file` is
   rejected for the same reason.
   Direct and selected-direct fetch correlation also counts unresolved shell
   variable source operands as effective sources. A fetch with an authoritative
   literal plus an untrusted dynamic source is rejected rather than projecting
   source authority from the literal alone. Command substitution, backticks,
   process substitution, and complex shell expansion in source position are
   likewise counted as untrusted dynamic sources. Scheme-less and other
   non-option operands are counted as untrusted source operands unless they are
   explicitly modeled as non-source option values such as `--retry 3`.
   Selected-loop alias correlation uses the same authoritative-first candidate
   rule and requires the first candidate to match the selected output URL.
   Direct top-level fetch URL variables
   are resolved segment-by-segment rather than from global shell assignments,
   so `read`, `printf -v`, `unset`, append assignment, and other top-level
   mutations before `curl`/`wget` invalidate stale authoritative URL bindings.
   Shell-builtin wrapper forms such as `builtin read`, `command read`, and
   `command printf -v` are treated as the same binding mutation. Unmodeled
   top-level shell-state mutators such as `eval`, `source`, `.`, `mapfile`,
   and `readarray` conservatively invalidate URL bindings before fetch
   correlation.

3. Source archive readback helpers now resolve simple shell assignments.
   This keeps `archive=/tmp/foo-1.2.3.tar.gz; sha256sum "$archive"; tar -tzf
   "$archive"` equivalent to direct path readback for reducer purposes.

4. Stale blockers are only cleared after the final contract is satisfied.
   Target/default-smoke evidence alone no longer clears non-source blockers
   while `source_authority` is still unknown.

## Validation

Initial focused:

```text
uv run pytest tests/test_long_build_substrate.py -q -k "or_failure_exit_guard or final_artifact_and_default_smoke_closeout or stale_strategy_blockers_after_final_contract_proof or source_authority_rejects_python_fetch_archive_with_errexit_masked_by_or_true or backgrounded"
7 passed, 268 deselected
```

Review follow-up focused:

```text
uv run pytest tests/test_long_build_substrate.py -q -k "selected_archive_source_authority or final_artifact_and_default_smoke_closeout or stale_strategy_blockers_after_final_contract_proof"
56 passed, 272 deselected
```

Broader reducer/resume slice after review follow-up:

```text
uv run pytest tests/test_long_build_substrate.py tests/test_work_session.py -q -k "source_authority or default_smoke or final_artifact_and_default_smoke_closeout or stale_strategy_blockers or long_build_state or long_build_current_failure or dependency_generation_order_issue or runtime_link_failed or timed_out_long_command or recover_long_command"
261 passed, 960 deselected
```

Lint:

```text
uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py
All checks passed
```

## Next Action

codex-ultra requested changes for selected-URL spoofing, selected-alias
mutation including `VAR+=...`, `readonly`, `read`, and `printf -v`,
literal-URL / other-variable / non-print marker spoofing, redirected marker
output, multiple selected markers, dynamic marker output, stale direct fetch
URL bindings after `read` / `builtin read` / `command printf -v`, and
unmodeled shell-state mutators such as `eval` / `source` / `.`, non-stdout
`printf -v` marker commands, split selected stdout vs non-authoritative marker
stdout, loop-body alias/loop-variable reassignment before fetch, stale
while-read candidate-file variable bindings, candidate-file overwrite ordering,
while-read first-candidate ordering, authoritative-first for-loop/selected-alias ordering, and
mixed direct-fetch URL rejection, mixed for/while loop fetch URL rejection, and
`curl --url` source operand accounting, and
`curl -K` / `--config` plus `wget --input-file` rejection, and
dynamic/command-substitution extra source operand rejection, and
scheme-less source operand rejection, and
premature blocker clearing. These follow-ups
are implemented and locally validated. Ask
codex-ultra to re-review this generic reducer/closeout repair. If approved, run
exactly one same-shape `compile-compcert` speed_1 before `proof_5` or broad
measurement.
