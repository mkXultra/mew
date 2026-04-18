# Why Mew

Mew should not win by copying Claude Code or Codex CLI. It should win when a
resident model benefits from persistence, passive state, recovery, and reentry.

This file records bake-off evidence. The product question is:

> Would a frontier coding model rather inhabit mew than start a fresh coding CLI?

## Current Judgment

Mew is already useful as a task-scoped resident work room. It is not yet proven
as a long-lived body.

The strongest expected advantage is interrupted work: a model returning after
time passes should recover faster from mew's task memory, work-session journal,
risks, notes, and resume commands than from a fresh session with only the repo.

The expected weakness is single-session speed and cockpit polish: a fresh
Claude Code or Codex CLI session is still likely smoother for a small isolated
edit.

## Bake-Off Method

Each task should be run with two perspectives:

- `mew`: use mew task state, `mew self-improve`, `mew work --follow`,
  `mew focus`, `mew work --session --resume`, and normal repo verification.
- `fresh`: use a fresh frontier coding model with the repo, but without mew's
  task-local work-session history unless explicitly given the same public files.

Record:

- setup and command path
- whether the model knew the next action without reconstruction
- time or step count to useful action
- friction observed
- whether mew's persistent state created an advantage
- whether a fresh session was simpler

## Candidate Tasks

| ID | Task | Why It Matters | Expected Winner |
|---|---|---|---|
| B1 | Reenter a self-improve task after it has tool history and a committed fix | Tests whether mew's resume memory beats rereading the repo | mew |
| B2 | Find and fix one machine-interface inconsistency in work-session JSON paths | Tests small real coding speed and observer reliability | unclear |
| B3 | Investigate a cockpit pain without editing, then resume later from memory | Tests multi-session investigation continuity | mew |
| B4 | Force an interrupted native work step and recover safely | Tests the recovery promise directly | mew if recovery is real |
| B5 | Let a fresh model solve the same scoped issue from repo-only context | Tests whether mew's overhead is justified | fresh for speed |

## Live Results

### 2026-04-19 Session

Start: 2026-04-19 00:16 JST

Goal: spend the session proving or disproving the claim that mew is preferable
for resident task/coding work.

Initial state:

- Worktree clean.
- Roadmap goal is explicit: make mew the task/coding execution shell that
  frontier models would prefer to inhabit over Claude Code or Codex CLI.
- Latest product evaluations from Codex and claude-ultra agree: mew is
  inhabitable for scoped work, but not yet proven as a long-lived body.

#### B0: Scaffolding

Result: this file now exists as the evidence ledger.

Friction: none yet.

Next: run B2 through mew first, because it is small, real, and likely to expose
whether the observer JSON surface is consistent enough for resident operation.

#### B2: Work-Session JSON No-Active Responses

Setup:

- Created task #139 with `mew task add --kind coding --json`.
- Started a native work session with `mew work 139 --start-session --allow-read . --json`.
- Ran `mew work 139 --follow --quiet --auth auth.json --allow-read . --compact-live --max-steps 3`.

Observed mew advantage:

- The first model call failed with a DNS/network error. The next
  `mew work 139 --session --resume --allow-read .` preserved that failed model
  turn in working memory instead of losing the session.
- After retrying, mew searched for the relevant command paths, read the exact
  `cmd_work_close_session` window, and produced a concrete diagnosis:
  `cmd_work_close_session` printed `No active work session.` before checking
  `args.json`.
- The closed work-session resume preserved the implementation next step:
  update `src/mew/commands.py`, add paired coverage in
  `tests/test_work_session.py`, and decide whether nearby no-active mutators
  should be normalized too.

Observed mew weakness:

- I had started the resident session with read-only gates. The model correctly
  stopped after diagnosis, but could not make the edit or run verification.
  For coding work, mew needs either clearer read-only vs write-capable session
  intent or a smoother approval path for upgrading a session's gates.

Change shipped:

- Work-session mutator commands now return structured JSON on no-active-session
  paths when `--json` is present:
  `--close-session`, `--stop-session`, `--session-note`, `--steer`,
  `--queue-followup`, and `--interrupt-submit`.
- The JSON shape includes `work_session: null`, `error:
  no_active_work_session`, a message, task id when available, and start
  commands.

Validation:

- Focused no-active mutator test: `1 passed`.
- First related `tests.test_work_session`: `284 tests OK`.
- Ruff for touched files: pass.
- Live check: `./mew work 138 --close-session --json` now returns parseable
  no-active JSON.

Fresh review:

- A fresh `codex-ultra` review, intentionally ignoring mew state, failed the
  first patch. It correctly noticed that the same `mew work --json` surface also
  included `--approve-tool`, `--approve-all`, `--reject-tool`, and `--tool`
  no-active paths.
- Follow-up fix extended structured no-active JSON to those action paths and
  added paired test coverage.
- Second related `tests.test_work_session`: `285 tests OK`.
- Ruff and `git diff --check`: pass.
- Fresh `codex-ultra` re-review: PASS. It found no remaining same-surface
  no-active path that still emits plaintext when `--json` is set.

Judgment:

- Mew beat a fresh session on recovery from the failed model call and on
  carrying the exact diagnosis forward after the closed resident session.
- Fresh review beat mew on breadth: it caught same-surface misses that the
  original resident diagnosis did not cover.
- Mew did not beat a polished coding CLI on edit speed, because the session was
  intentionally read-only and I took over the patch.

#### B3: Read-Only Reentry To Write-Capable Continuation

Setup:

- Created task #140 with `mew task add --kind coding --json`.
- Started the resident session with write and verify gates:
  `mew work 140 --start-session --allow-read . --allow-write . --allow-verify
  --verify-command "uv run python -m unittest tests.test_work_session" --json`.
- Ran `mew work 140 --follow --quiet --auth auth.json --allow-read .
  --allow-write . --allow-verify --verify-command "uv run python -m unittest
  tests.test_work_session" --compact-live --max-steps 5`.

Observed mew advantage:

- With write/verify gates, mew did not stop at diagnosis. It inspected the
  reentry formatter and applied a real `edit_file` to `src/mew/commands.py`.
- The applied edit ran the configured verifier successfully and journaled the
  write plus verification in the work session.
- When it reached the max-step boundary before finishing the paired test/doc
  work, it preserved the exact pending follow-up in work-session memory.
- `mew work 140 --session --resume --allow-read .` made the pending paired-test
  work obvious enough to continue without reconstructing the task from scratch.

Observed mew weakness:

- I gave it a verifier for `tests.test_work_session`, but the actual paired test
  belonged in `tests.test_commands`. Mew trusted the supplied gate and called
  the work verified too early. The resident can execute gates, but the human or
  supervisor still has to choose a good one.
- The model initially guessed `tests/test_brief.py`; after reading the code path,
  the correct paired coverage was in `tests/test_commands.py`.

Change shipped:

- `mew work <task>` workbench reentry now includes the active work-session
  `resume.next_action`, so the immediate continuation command is visible beside
  working memory and notes.
- The workbench's bottom `Next action` now reuses the active work session's
  persisted defaults via `work_session_runtime_command`, preserving auth,
  read/write roots, verification gates, compact-live, quiet mode, and similar
  cockpit settings instead of falling back to `--allow-read .` only.

Validation:

- Focused command tests: `2 passed`.
- The same two focused tests were also run through `mew work 140 --tool
  run_tests`, preserving the verification in the work-session ledger.
- Related `tests.test_commands` + `tests.test_work_session`: `452 tests OK`.
- Ruff and `git diff --check`: pass.

Fresh review:

- Fresh `codex-ultra` initially failed the patch. It found that a session with
  non-gate defaults such as `compact_live` would lose `--allow-read .` and hit
  `missing_gates`, and that `next_action:` in Reentry was ambiguous beside the
  canonical bottom `Next action`.
- Follow-up fix added a workbench command helper with three cases: no defaults
  keep the old `--allow-read .` fallback, real gate defaults are reused exactly,
  and non-gate defaults get an injected read gate while preserving those
  defaults.
- The Reentry label is now `resume_next_action:`.
- Fresh `codex-ultra` re-review: PASS.

Judgment:

- Mew was better than a fresh session at preserving "what remains" after a
  partially completed edit. The resume bundle pointed directly at the missing
  paired test.
- Mew still needs better verifier selection discipline. A wrong verification
  gate can create false confidence even when the native tool loop works.
- Fresh review again improved breadth. It caught the non-gate default edge case
  before commit.
