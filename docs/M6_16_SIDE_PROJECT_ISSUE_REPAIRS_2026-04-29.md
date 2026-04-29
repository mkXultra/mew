# M6.16 Side-Project Issue Repairs - 2026-04-29

Context: side-project dogfood was blocked by open `[side-pj]` issues #17 and
#21-#28. This repair slice treats the issue queue as implementation-lane
hardening input before returning to M6.24.

## Repairs

| Issue | Repair |
|---|---|
| #17 | Git closeout fallback now prefers directory allow-read roots before file roots, so side-project `git_status` / `git_diff` scopes to the isolated side-project directory even when roadmap/status files are also allowed. |
| #21, #27 | Verifier-failed applied writes now preserve `failed_patch` metadata before rollback, including diff, stats, parameters, and a recovery hint. |
| #25 | `approve-all` now skips superseded older same-path pending dry-run writes, reducing stale-hunk rollback of newer verified work. |
| #26 | Added regression coverage that a side-project batch can carry coordinated multi-file `edit_file_hunks` dry-run patches under one allowed write root. |
| #22 | Work-session finish now blocks invalid `.mew-dogfood/reports/*.json` files by validating the canonical side-dogfood schema. |
| #24 | Work-session finish now blocks stale side-project identity in side-dogfood reports when the work context names a canonical side project such as `mew-wisp`. |
| #23 | Work command subprocesses on macOS default `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` to suppress Objective-C fork-safety crash logs during closeout tools. |
| #28 | Pending reviewer steer now enforces target-path / no-read / no-test boundaries before tool execution and coerces requested dry-run writes away from direct apply. |
| #29 | Broad rollback repair now detects UI/readability failure tails and steers the next attempt to a smaller presentation/readability slice before reconnecting broader live/state behavior. |

## Validation

```text
uv run pytest tests/test_side_project_dogfood.py tests/test_toolbox.py tests/test_work_session.py -k 'side_dogfood or objc_fork_safety or side_project_multi_file_hunks or git_tools_scope_to_allowed_read_root or failed_verifier_preserves or steer_blocks_wrong_target or invalid_side_dogfood or stale_side_project_identity or write_tools_default_to_dry_run or approve_all_skips_superseded or approve_all_verifies_after_entire_batch or approve_all_rolls_back_deferred_writes or can_approve_all_pending' --no-testmon -q
20 passed, 778 deselected

uv run ruff check src/mew/toolbox.py src/mew/work_session.py src/mew/commands.py tests/test_toolbox.py tests/test_work_session.py tests/test_side_project_dogfood.py
All checks passed

uv run pytest tests/test_work_session.py -k 'broad_rollback_slice_repair or work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
3 passed, 781 deselected

uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py
All checks passed
```
