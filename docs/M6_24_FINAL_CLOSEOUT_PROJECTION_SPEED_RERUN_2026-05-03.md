# M6.24 Final Closeout Projection Speed Rerun - 2026-05-03

## Run

- Job: `mew-m6-24-final-closeout-projection-compile-compcert-1attempt-20260503-0728`
- Task: `terminal-bench/compile-compcert`
- Shape: same-shape `speed_1`, `k=1`, `n=1`
- Result path:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-final-closeout-projection-compile-compcert-1attempt-20260503-0728/result.json`

## Result

- Harbor reward: `1.0`
- Trials: `1`
- Runner errors: `0`
- Runtime: about `30m17s`
- External verifier: `3 passed`

The external task is solved, but internal mew closeout is not clean:

- `mew-report.work_exit_code`: `1`
- `work_report.stop_reason`: `wall_timeout`
- `timeout_shape.latest_long_command_run_id`: `null`
- `resume.long_build_state.status`: `blocked`
- `source_authority`: `unknown`
- `target_built`: `satisfied`
- `default_smoke`: `satisfied`
- stale blockers:
  - `toolchain_version_constraint_mismatch`
  - `dependency_generation_order_issue`

The latest working memory is correct: command evidence `#13` read back the
saved upstream source URL, archive sha256, archive members, `ccomp` artifact,
configured target, runtime library, and a default-link functional smoke.

## Classification

This is a narrower reducer/closeout projection gap, not a Terminal-Bench task
gap. The original acquisition evidence is no longer present in the compacted
live reducer window, but the final terminal proof still has enough grounded
identity evidence:

- it reads `source_url=https://...` from a saved `*source-url*` file,
- it hashes and lists the versioned source archive,
- it proves the final artifact and default functional smoke.

## Repair

`src/mew/long_build_substrate.py` now treats this compacted final proof as
source-authority evidence only at aggregate reducer time and only when all
conditions hold:

- command exits successfully,
- command reads a saved source URL file via `cat`/`grep`/`sed`/`awk`,
- output contains an authoritative `source_url=https://...`,
- command hashes and lists a versioned source archive,
- output contains matching hash/list evidence,
- command is not an assertion-only source-authority segment,
- the same reducer window does not contain a prior non-acquisition command that
  fabricated the same `*source-url*` file.

After review, the fabrication guard was broadened: any current-window writer to
the same `*source-url*` file is treated as fabricated unless that writer
evidence itself satisfies source authority. This covers failed writers and
masked/invalid acquisition-looking commands. It also recognizes fd-prefixed
stdout redirections such as `1> /tmp/foo-source-url.txt`, including clobber
forms such as `>| /tmp/foo-source-url.txt` and
`1>| /tmp/foo-source-url.txt`, and combined stdout/stderr redirections such as
`&> /tmp/foo-source-url.txt` and `&>> /tmp/foo-source-url.txt`. Simple shell
variable targets such as `p=/tmp/foo-source-url.txt; printf ... > "$p"` are
resolved before readback acceptance, including chained simple path assignments
like `dir=/tmp; p="$dir/foo-source-url.txt"`. Redirection operators are
recognized even when adjacent to command words, e.g. `printf ...>/tmp/foo-source-url.txt`
or `printf ...>"$p"`. If a non-authority command writes to an unresolved
dynamic redirection or `tee` target, that window blocks saved source-url
readback closeout instead of trying to infer the target. Process-substitution
writers such as `printf ... > >(tee /tmp/foo-source-url.txt >/dev/null)` are
tracked as fabricated writers too. Common file materialization commands
(`cp`, `install`, `mv`) that create or replace a `*source-url*` path are also
tracked, as are explicit output-path writers such as `dd of=...`. Unmodeled
script writers that mention both `source_url` content and a concrete
`*source-url*` path are treated as fabricated too. Script write primitives with
`source_url` payload and dynamic path construction are handled by the dynamic
fabricated-writer sentinel.

Regression:

- `test_reducer_projects_saved_source_url_archive_readback_closeout_after_compacted_acquisition`
- `test_reducer_rejects_fabricated_saved_source_url_archive_readback_closeout`
- `test_reducer_rejects_unvalidated_current_window_saved_source_url_writer_closeout`

Validation after repair:

```text
uv run pytest tests/test_long_build_substrate.py -q -k "compacted_acquisition or schemeless_extra_source_operand or command_substitution_source_operand or dynamic_extra_source_operand or wget_input_file_url or curl_config_url or mixed_remote_urls or mixed_curl_url_option or fetch_with_mixed_remote_urls or loop_alias_later_authoritative_candidate or later_authoritative_loop_candidate_without_failure_evidence or for_loop_later_authoritative_candidate_after_bad_first or later_authoritative_candidate_after_bad_first or while_read_candidate_file_overwrite or while_read_candidate_path_variable_mutation or for_loop_variable_reassignment or loop_body_alias_reassignment or marker_stdout_split or printf_v_marker_command or url_variable_mutation or selected_archive_source_authority or final_artifact_and_default_smoke_closeout or stale_strategy_blockers_after_final_contract_proof"
83 passed, 272 deselected

uv run pytest tests/test_long_build_substrate.py tests/test_work_session.py -q -k "source_authority or default_smoke or final_artifact_and_default_smoke_closeout or stale_strategy_blockers or long_build_state or long_build_current_failure or dependency_generation_order_issue or runtime_link_failed or timed_out_long_command or recover_long_command"
261 passed, 987 deselected

uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py
All checks passed

jq empty proof-artifacts/m6_24_gap_ledger.jsonl
git diff --check
```

## Next Action

Ask codex-ultra to review the compacted acquisition/source-url readback repair.
If approved, run exactly one same-shape `compile-compcert` speed_1 again. Do
not run `proof_5` or broad measurement first.

## Same-Shape Rerun After Review

Job:

`mew-m6-24-compacted-source-url-closeout-compile-compcert-1attempt-20260503-0751`

Result:

- Harbor reward: `0.0`
- runner errors: `0`
- runtime: `30m24s`
- `mew work` exit: `1`
- `stop_reason`: `wall_timeout`
- external verifier: `/tmp/CompCert/ccomp` missing

This does not invalidate the compacted source-url readback repair. The run
failed earlier on the long dependency/toolchain recovery path:

- the apt-provided Coq was unsupported for CompCert 3.13.1,
- mew tried external Flocq/MenhirLib but did not inspect compatibility
  override terms such as `-ignore-coq-version`,
- it then spent the remaining budget on `opam install coq.8.16.1`,
- the managed long-command state reported stale optimistic remaining budget,
  so the next model turn was attempted with about 32 seconds left and timed out.

Classification:

`source_toolchain_before_compatibility_override` plus
`terminal_long_command_budget_after_missing`.

Repair:

- Treat filtered `configure --help` probes as incomplete compatibility-override
  probes unless the filter/output actually includes override terms such as
  `ignore`, `override`, `compatib`, or `allow-unsupported`.
- Record `duration_seconds` for normal and managed command results.
- For terminal managed long-command runs, carry forward
  `wall_budget_after_seconds` as the recovery budget instead of the stale
  start-of-poll budget.

Validation:

```text
uv run pytest tests/test_toolbox.py tests/test_work_session.py -q -k "duration_seconds or managed_long_command_finish_updates_existing_run_with_terminal_evidence or filtered_help_that_skips_override_terms or version_pinned_source_toolchain_before_override or source_toolchain_after_override_attempt"
4 passed, 902 deselected

uv run ruff check src/mew/toolbox.py src/mew/work_session.py tests/test_toolbox.py tests/test_work_session.py
All checks passed
```

codex-ultra review requested changes:

- bare `grep -i ignore` should count as an override probe,
- redirect filenames such as `/tmp/compatibility-help.txt` must not satisfy the
  override probe if neither the filter nor observed output contains override
  terms,
- terminal poll budget accounting must subtract only the current tool-call
  elapsed time, not the managed command's total runtime since original start.

Follow-up repair:

- compatibility override term matching now accepts bare `ignore`,
- filtered help matching removes redirection target filenames before checking
  the filter expression,
- terminal managed-command evidence writes explicit
  `wall_budget_after_seconds` from the current tool-call elapsed time before
  long-command run reduction.

Follow-up validation:

```text
uv run pytest tests/test_work_session.py tests/test_toolbox.py -q -k "compatibility_override or source_toolchain or managed_long_command_finish_updates_existing_run_with_terminal_evidence or duration_seconds or wall_budget_after"
13 passed, 895 deselected

uv run ruff check src/mew/toolbox.py src/mew/work_session.py tests/test_toolbox.py tests/test_work_session.py
All checks passed
```

codex-ultra re-review requested one test-shape fix:

- the redirect-filename regression asserted
  `compatibility_override_probe_missing`, but the fixture had no failing
  configure/API-mismatch call that could produce that blocker,
- the test name also did not match the stated `compatibility_override` focused
  validation filter.

Second follow-up repair:

- renamed the redirect-filename regression so it is selected by the
  `compatibility_override` validation filter,
- changed the fixture to run filtered `configure --help` into
  `/tmp/compatibility-help.txt`, then fail `./configure x86_64-linux` with a
  Coq version mismatch before the version-pinned OPAM install.

Second follow-up validation:

```text
uv run pytest tests/test_work_session.py tests/test_toolbox.py -q -k "compatibility_override or source_toolchain or managed_long_command or long_command_budget or duration_seconds or wall_budget_after"
28 passed, 880 deselected, 3 subtests passed
```

Next action:

Run the broader long-build/work-session regression slice, then request
codex-ultra review for the compatibility-override and terminal-budget repair.
Do not run another Harbor speed rerun until that review is clean.
