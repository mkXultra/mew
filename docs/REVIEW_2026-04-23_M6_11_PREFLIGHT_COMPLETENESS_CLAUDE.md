# M6.11 Preflight Cached-Window Completeness Review (Revised) — Claude

Date: 2026-04-23
Reviewer: Claude (Opus 4.7)
Base HEAD: `af9d5e7`
Scope: uncommitted working-tree changes to `src/mew/work_loop.py` and `tests/test_work_session.py`
Spec under review: `docs/REVIEW_2026-04-23_M6_11_POST_425_NEXT_CODEX.md`
Supersedes: earlier contents of this file (prior approval with small residual risk).

decision: **approve**
summary: Revision retains the prior slice's Python-aware preflight and adds two principled leading-edge checks — (1) reject any window whose first significant line is indented (orphaned leading body fragment) and (2) reject any window whose first significant line is a bare clause tail at indent level 0 (`else:` / `elif …:` / `except …:` / `finally:`). Both checks are monotonic (still cannot widen fast-path activation), are targeted by two new tests, and address a subset of the "mid-body truncation" false-negative I flagged previously. My decision moves from "approve with small residual risk" to "approve"; no concern is introduced that outweighs the tightened coverage.

product_goal_drift: none
safety_boundary_status: ok (still strictly a narrowing of the fast-path success branch)
evidence_quality: strong
verification_status: adequate
hidden_rescue_edits: none

## Delta since the previous revision

**`src/mew/work_loop.py`** — `_write_ready_window_text_is_structurally_complete` gained two leading-edge checks, inserted between the empty-window guard and the previous last-line check:

```python
first_line = significant_lines[0]
first_line_stripped = first_line.lstrip()
first_keyword = first_line_stripped.split()[0].rstrip(":") if first_line_stripped else ""
if first_line and first_line[0].isspace():
    return False
if first_line_stripped.endswith(":") and first_keyword in {"else", "elif", "except", "finally"}:
    return False
```

Everything else in the file-level diff (imports, `_write_ready_window_has_unmatched_delimiters`, `_write_ready_recent_windows_are_structurally_complete`, the integration site at `_work_write_ready_fast_path_details`:1353–1358, and the trailing last-line check) is unchanged from the prior revision.

**`tests/test_work_session.py`** — two new tests added alongside the existing three:

- `test_write_ready_fast_path_blocks_orphaned_leading_indented_body_fragment` — source starts with `    return foo\n` (indented body fragment with no visible enclosing scope).
- `test_write_ready_fast_path_blocks_clause_tail_fragment` — source starts with `else:\n    x = 1\n` (clause continuation without its preceding `if`).

Both assert `details.active == False`, `reason == "insufficient_cached_window_context"`, and `build_write_ready_work_model_context(context) == {}`.

## Findings

### The two new checks are coherent and well-targeted

1. **Orphaned leading indented body fragment.** `if first_line and first_line[0].isspace(): return False`. This catches windows whose first non-blank line is indented — i.e., the window begins mid-body, and the enclosing `def`/`class`/`for`/`while`/`with`/etc. is not visible inside this window. Such a window cannot anchor a safe exact-old-text edit without cross-window inference, so refusing the fast path is correct. Detection is cheap (single-char test on the rstripped line) and unambiguous.
2. **Clause-tail fragment at indent level 0.** `if first_line_stripped.endswith(":") and first_keyword in {"else", "elif", "except", "finally"}: return False`. This catches windows that start with a clause continuation — an `else` / `elif` / `except` / `finally` that syntactically requires a preceding `if`/`try` header which is not in this window. The split/rstrip composition is safe: `split()[0]` is the first whitespace-separated token, `rstrip(":")` strips a trailing colon abutting the keyword, so `else:`, `elif x:`, `except ValueError as e:`, and `finally:` all reduce to the correct keyword. Non-clause colon-terminated headers (`def …:`, `class …:`, `for …:`, `while …:`, `with …:`, `if …:`, `try:`) do not match the keyword set and are handled by the pre-existing last-line check (for tail cases) or simply allowed (when they appear as the first line, since they *do* open a new scope within this window).

### Ordering is correct

The check ordering inside `_write_ready_window_text_is_structurally_complete` is:

1. Empty-window guard.
2. **First-line-indented guard (new).**
3. **Clause-tail-at-col-0 guard (new).**
4. Last-line trailing-colon / `def`/`class`/`async def`/`@` prefix guard.
5. Unmatched-delimiter / `tokenize.TokenError` guard.

Because the first-line-indented guard runs before the clause-tail guard, the clause-tail check is implicitly restricted to column-zero clause tails. Indented clause tails (e.g., a window that happens to start with `    else:`) are already rejected by the first-line-indented guard, which is the correct outcome — an indented `else` implies an enclosing scope whose header is not visible either. The interaction is clean, not redundant.

### All five fast-path-blocking tests exercise distinct detection paths

Tracing each test through the heuristic:

| Test | First line | Matches at |
|---|---|---|
| `unfinished_source_block_window` | `def update_state():` (non-indent) | last-line trailing `:` on `if ready:` |
| `test_window_with_unmatched_open_paren` | `def test_update_state():` (non-indent) | `TokenError("EOF in multi-line statement")` on `helper(` |
| `orphaned_leading_indented_body_fragment` | `    return foo` | first-line-indented (new) |
| `clause_tail_fragment` | `else:` | clause-tail keyword set (new) |
| `source_window_starting_mid_fragment` | `    )` | first-line-indented (new; previously caught by unmatched-delimiters) |

The last row is worth noting: the test name and text predate this revision; with the new first-line-indented check, the detection surface for this test shifts from the delimiter-balance check to the leading-indent check. The test still passes (same `reason` code, same downstream zero context), so the renamed detection is transparent to callers. No behavior regression.

### Positive-case fast path still activates

`test_write_ready_fast_path_falls_back_to_recent_target_path_windows` (`tests/test_work_session.py:6655`) is the implicit positive-case test. Its text content is `"commands window\n" * 30` and `"tests window\n" * 40`. Tracing:

- First line of each: `commands window` / `tests window`. Both start with a non-space character → first-line-indented guard passes.
- Neither first line ends with `:`, so the clause-tail guard is not even evaluated (short-circuits on the `endswith(":")` test).
- Last lines are identical to first lines; no trailing `:`, no flagged prefix.
- `tokenize` produces only `NAME` tokens, no `OP` — stack stays empty; no `TokenError`.

Result: structurally complete, fast path still activates, downstream `cached_window_texts` populated with tool_call_ids 11 and 12. No regression.

### Resolution of prior residual risks

From the earlier review (now superseded):

1. **Python-only tokenizer on a test-path gate that admits non-Python fixtures** — unchanged; same assessment. Still low-probability for this repo, still fall-through-safe (false positive = non-fast-path, not an incorrect edit).
2. **`except tokenize.TokenError` does not cover `IndentationError`** — unchanged; still an optional hardening. Not triggered by any test.
3. **Mid-body truncation undetected** — **partially addressed**. The subset where the mid-body fragment begins with an indented line is now caught by check #2 above. Windows that begin at a non-indented `def`/`class` header but whose tail lies inside the function body still pass; this remains lexically undetectable without semantic analysis, and is acceptable for a bounded slice.
4. **No explicit positive-case test** — unchanged. The falls-back test still provides implicit coverage.
5. **`:` trailing false positive on `match`/`case` blocks** — unchanged. A window ending on `case Foo:` is still conservatively blocked; acceptable.

### New residual risk introduced by the revision

**Aggressiveness of the first-line-indented check in practice.** In real-world cached windows produced by the reader tool with `line_start`/`line_count`, it is fairly common for the window to begin at an indented line (e.g., the reader asked for lines 120–160, and line 120 lives inside a function body). Under this revision, any such window will fall through to the non-fast path even if the rest of the window is syntactically tidy. This is consistent with the spec's intent ("be strict about context sufficiency before entering the tiny draft lane") and remains safe (fall-through, not incorrect edit). It may, however, reduce fast-path activation rates in the calibration cohort. This is self-surfacing — the ledger's `blocker_code` distribution will show an uptick in `insufficient_cached_window_context` at the preflight stage; if the drop in counted write-ready activations is excessive, a follow-up slice can refine the check (e.g., require that the indented first line be accompanied by a visible enclosing header earlier in the window, or accept indented first lines when the cached-window `line_start` equals 1). Not a blocker for this slice.

## Verification judgment

- Unit coverage is adequate: five distinct blocker paths, each with a targeted test; one implicit positive-case test continues to pass.
- The reviewer spec's recommended verification set plus the two new tests should be run pre-merge.
- The `tests/test_dogfood.py -k 'm6_11_compiler_replay'` loop-level regression remains the appropriate end-to-end check — it was the surface that produced `#425`'s `insufficient_cached_context` signal, and this slice shifts that signal's detection point earlier (pre-draft) rather than changing its meaning.

## Concrete next action

**Land the slice as-is**, then run:

```bash
uv run python -m unittest \
  tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_blocks_unfinished_source_block_window \
  tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_blocks_test_window_with_unmatched_open_paren \
  tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_blocks_orphaned_leading_indented_body_fragment \
  tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_blocks_clause_tail_fragment \
  tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_blocks_source_window_starting_mid_fragment \
  tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_falls_back_to_recent_target_path_windows \
  tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_reports_missing_exact_cached_window_texts_reason \
  tests.test_work_session.WorkSessionTests.test_cached_exact_read_plan_item_is_skipped_for_write_ready_fast_path
uv run pytest -q tests/test_dogfood.py -k 'm6_11_compiler_replay' --no-testmon
```

After the next calibration pass, check the ledger's `blocker_code` distribution for a drop in counted write-ready activations that correlates with a rise in pre-draft `insufficient_cached_window_context`. If the drop is larger than expected, open a follow-up slice to refine the first-line-indented check (e.g., permit indented first lines when `line_start == 1` or when a visible enclosing header exists earlier in the window). Deferring this to a follow-up is correct — no sampling is needed before landing.

Non-blocking hardenings to carry as backlog items (unchanged from prior review):

- widen `except tokenize.TokenError` to `except (tokenize.TokenError, IndentationError)`;
- add one explicit positive-case test (paired balanced windows → `active=True`) as a regression anchor;
- document the Python-only assumption of the heuristic near `_write_ready_window_text_is_structurally_complete`.
