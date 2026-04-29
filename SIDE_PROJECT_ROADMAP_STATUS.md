# Mew Side Project Implementation Status

Last updated: 2026-04-29

This file is the compact operational dashboard for side-project implementation
dogfood. It is intentionally separate from `ROADMAP_STATUS.md`; the main
roadmap consumes side-project evidence through M6.13.2 and M6.16.

## Summary

| Milestone | Status | Current Meaning |
|---|---|---|
| SP0 Dogfood Harness Ready | `done` | Roadmap, status, `side-pj-mew-impl` skill, and M6.13.2 telemetry CLI are ready. |
| SP1 mew-companion-log Scaffold | `done` | Scaffold landed after issue #1 repair; mew-authored source, fixture, README, and tests pass. |
| SP2 Journal and Dream Reports | `done` | Morning, evening, and dream/learning fixture-driven outputs landed with focused tests. |
| SP3 Implementation-Lane Evidence Cohort | `done` | Five side-project attempts are recorded; failures are classified and rescue edits remain zero. |
| SP4 Optional Research Digest Slice | `done` | Static fixture research digest landed with deterministic ranking, README usage, stdout, and output-file tests. |
| SP5 Feed M6.16 | `done` | The side-project cohort is summarized into a measured M6.16 hardening recommendation and now includes the SP4 extension row. |
| SP6 Mew State Companion Export | `done` | State-brief mode landed clean: static mew-state-like fixture, README usage, stdout/output-file behavior, and focused tests are in place without live `.mew` access. |
| SP7 Multi-Fixture Companion Bundles | `done` | Bundle mode landed practical: static manifest, deterministic grouping/order, missing-fixture behavior, README usage, stdout/output-file proof, and focused tests are in place. |
| SP8 Multi-Day Companion Archive | `done` | Archive-index mode landed practical: static multi-day fixture, day/surface/next-action grouping, empty-day behavior, README usage, stdout/output-file proof, and focused tests are in place. |
| SP9 Issue and Dogfood Ledger Digest | `done` | Dogfood-digest mode landed practical: static dogfood rows, `[side-pj]` issue summaries, outcome/failure-class/rescue-edits grouping, README usage, stdout/output-file proof, and focused tests are in place. |
| SP10 Companion Export Contract | `done` | Export contract landed practical: local schema examples, documented markdown surfaces for every mode, README pointer, and all-mode output-file compatibility tests are in place. |
| SP11 Second Side-Project Gate | `done` | Gate landed practical: the recommendation is to pause new side-project work and feed SP6-SP10 evidence into core M6.16/M9/M11 before starting a second isolated side project. |
| SP12 mew-ghost macOS Shell Scaffold | `done` | Scaffold landed practical: isolated `experiments/mew-ghost` shell, permission-safe macOS probe contract, deterministic HTML/state rendering, dry-run `mew chat`/`mew code` intents, README usage, local report, and focused tests are in place. |
| SP13 mew-ghost Live macOS Probe Integration | `done` | Live probe integration landed practical: explicit `--live-active-window` opt-in, injectable `osascript` runner/provider, structured fallbacks, README usage, output proof, and hermetic tests are in place. |
| SP14 mew-ghost Presence Loop | `done` | Presence loop landed practical: deterministic idle/attentive/coding/waiting/blocked classification, bounded refresh snapshots, README refresh contract, output proof, and focused tests are in place. |
| SP15 mew-ghost Launcher Contract | `done` | Launcher contract landed practical: explicit `mew chat`/`mew code` commands, dry-run default state, `--execute-launchers` opt-in execution gate, injected-runner tests, README usage, local report, and focused proof are in place. |
| SP16 mew-ghost Watch Mode | `done` | Watch mode landed practical: foreground CLI JSONL records, bounded `--watch-count`, interruptible `--watch`, `--interval`, repeated HTML rewrites with freshness metadata, README usage, local report, and focused proof are in place. |
| SP17 mew-ghost Desk Bridge | `done` | Desk bridge landed practical: static `--desk-json` fixture loading, desk pet-state presence mapping, status/counts/details/primary_action rendering, dry-run primary_action intent, watch reload proof, README usage, local report, and focused tests are in place. |
| SP18 mew-ghost Live Desk Opt-In | `done` | Live desk opt-in landed practical: explicit `--live-desk`, no-shell repo-local desk command, timeout/fallback handling, fixture-only defaults, top-level real desk JSON normalization, README examples, local report, real live-desk proof, and focused tests are in place. |
| SP19 mew-wisp CLI-First Reset and HTML Removal | `deferred/partial` | Broad HTML removal is deferred after issue #18 closed, but SP19a task #20 landed an additive `--format human` terminal renderer with focused tests while preserving existing `html` and `state` outputs. |
| SP20 mew-wisp Watch TUI Experience | `done` | SP20a task #21 landed practical after fresh session #48 with `--model-timeout 300`: human watch/no-output prints terminal surfaces instead of JSONL, while state JSONL and HTML output behavior remain intact. |
| SP21 mew-wisp Form Layer | `done` | SP21a added `--form default`/`--form cat`; SP21b/SP21c used `read_image` on `cat.png`, then replaced the weak ASCII cat with a literal 22x24 `cat.png`-derived mask sprite and >=0.90 similarity test. SP21d/SP21e compacted the human HUD and hid diagnostics behind `--details`; SP21g centers the cat block in terminal output while preserving state/HTML/watch/live/launcher behavior. |
| SP22 mew-wisp Visual Polish | `done` | SP22a exposed issue #21 before landing product edits. SP22b landed visible identity. SP22c replaced loose HUD lines with a fixed-width ASCII resident panel. SP22d centered the panel with the cat form. SP22e/SP22f replaced raw diagnostics and stale ghost copy with resident-facing mew-wisp copy while preserving details gating, state/HTML/watch/live/launcher behavior, and no product-code rescue edits. |
| SP23 mew-wisp Speech Bubble | `done` | SP23a landed practical in task #38/session #67: human terminal output now renders an ASCII mew-wisp speech bubble between the cat/default form and resident HUD, with focused tests and zero product-code rescue edits. Issues #25/#26/#27 remain implementation-lane hardening evidence. |
| SP24 mew-wisp Mew Adapter Reconnect | `done` | SP24a/SP24b landed practical: the CLI-first human cat surface renders fixture snapshots, injected live desk provider output, and explicit repo-local `--live-desk` output through one opt-in adapter boundary, with visible fallback states and sanitized human details. |

## Active Focus

Active side-project focus: **SP24 mew-wisp Mew Adapter Reconnect is complete**.

Current target:

- treat `mew-wisp` as the canonical product name for the second side-project
  arc; `mew-ghost` remains historical context for SP12-SP18 and the current
  implementation path until a rename slice lands
- define the wisp as a terminal presence surface/body, not a fixed character;
  the visible character should be replaceable by future forms/skins
- build the CLI experience from fixtures first, then reconnect to explicit mew
  state once the terminal resident view is worth keeping on screen
- retire HTML/browser output from the forward product direction when the broad
  removal blocker is fixed; meanwhile use the additive `--format human` path as
  the forward terminal surface and keep deterministic state/JSON output for
  tests, proofs, and future adapters
- keep the current implementation isolated under `experiments/mew-ghost` until
  SP19 either renames the path or records why the path should remain historical
- SP19 task `#19` is blocked with no product edits landed; issue `#18` records
  the stale-hunk and batch tool-shape failure after sessions `#42` and `#43`,
  and was reopened after session `#44` still could not land broad HTML removal
  even after the issue was initially closed and latest `origin/main` was pulled;
  issue `#18` is now closed again and the side project advanced by splitting the
  terminal path into additive SP19a/SP20a/SP21a slices
- SP19a task `#20` landed practical: `--format human` renders terminal-first
  text for operator consoles, desk fixture status/action details are visible,
  focused tests cover the new surface, and existing `html`/`state` outputs stay
  intact while the broad SP19 removal remains deferred
- SP20a task `#21` landed practical after the blocked session `#47` was closed
  and retried in fresh session `#48` with `--model-timeout 300`; ledger row
  `25` preserves the pre-edit timeout failure, ledger row `26` records the
  successful human watch terminal surface, and issue `#19` was closed with the
  operational workaround evidence
- SP21a task `#22` landed practical: `--format human` now accepts `--form
  default` and `--form cat`, the cat form renders a state-varying ASCII cat for
  idle/coding/waiting/blocked-style presence, human watch with cat remains
  non-JSONL, and state/HTML/live/launcher behavior stayed unchanged
- SP21b task `#23` landed practical: mew used `read_image` on repo-root
  `cat.png` in sessions `#50`, `#51`, and `#52`; reviewer rejected the first
  slash-heavy line-art pass and the later cyber/block icon pass, then mew
  revised `--form cat` into a more literal `cat.png` coarse-grid sprite with
  pointed ears, square face/head, vertical eyes, square nose, slim standing
  body, two narrow legs/feet, and a large stepped curled right tail; ledger rows
  `28` and `29` record the reviewer-followup practical results with rescue
  edits `0`
- SP21c task `#24` landed practical: mew used `read_image` on repo-root
  `cat.png`, encoded a 22x24 `cat.png`-derived threshold mask, rendered `#`
  cells as `██` and `.` cells as spaces, moved state markers outside the
  silhouette, and added a focused cell-wise similarity test requiring `>=0.90`;
  the observed rendered-mask similarity is `1.0`, and ledger row `30` records
  the practical result with rescue edits `0`
- SP21d task `#25` landed practical: normal `--format human` and
  `--format human --form cat` now render a compact mew-wisp HUD with concise
  `hud`/`focus`/`signal`/`next` lines, while freshness, desk diagnostics,
  active-window reason, and launcher intents are opt-in behind `--details`;
  ledger row `31` records the practical result with rescue edits `0`
- SP21e task `#26` landed practical as reviewer polish: the cat HUD now keeps
  exactly one state marker outside the 22x24 silhouette, the focus separator is
  ASCII, and focused tests cover duplicate-marker regression and ASCII output;
  ledger row `32` records the practical result with rescue edits `0`
- SP21f task `#27` stopped before product edits when session `#56` replayed an
  invalid mixed read/write batch after retry guidance; issue `#20` records the
  implementation-lane problem, and ledger row `33` records the failed attempt
  with rescue edits `0`
- SP21g task `#28` landed practical from fresh session `#57`: normal
  `--format human --form cat` centers the 22x24 block-cell sprite, cat-state
  line, and post-silhouette state marker relative to terminal width, includes a
  deterministic width override/fallback for tests, preserves narrow-width
  output, and keeps compact HUD/details/state/HTML/watch/live/launcher behavior
  intact; ledger row `34` records the practical result with rescue edits `0`
- SP22a task `#29` stopped before product edits after a verifier rollback and
  model timeout; issue `#21` records the implementation-lane recovery problem,
  and ledger row `35` records the failed attempt with rescue edits `0`
- SP22b task `#30` landed practical from repaired session `#59`: normal human
  output now uses `mew-wisp compact resident HUD`, shows
  `resident: mew-wisp` instead of exposing `hud: mew-ghost`, renames the primary
  action line to `action`, keeps diagnostics behind `--details`, and preserves
  centered cat output, watch output, state/HTML/live/launcher behavior, and
  rescue edits `0`; ledger row `36` records the practical result
- SP22c task `#31` landed practical from session `#60`: normal human output now
  renders a fixed-width ASCII `mew-wisp resident HUD` panel with aligned labels
  and wrapped long focus/signal values under both default and cat forms, while
  preserving the 22x24 cat mask, cat centering, state marker semantics,
  `--details` diagnostics gating, watch output, state/HTML/live/launcher
  behavior, and product-code rescue edits `0`; ledger row `37` records the
  practical result, and issue `#22` records the recurring report-schema
  closeout gap
- SP22d task `#32` landed practical from session `#61`: the fixed-width
  resident HUD panel now centers to the same deterministic terminal-width
  override/fallback as the cat form, preserves narrow-width no-padding behavior,
  keeps the cat mask and state marker semantics unchanged, and keeps
  `--details`, watch, state/HTML/live/launcher behavior intact; ledger row `38`
  records the practical result with product-code rescue edits `0`
- SP22e task `#33` landed practical from session `#62`: normal cat human output
  now starts with centered resident-facing copy (`mew-wisp resident cat` and
  `resident state: ...`) instead of `terminal form: cat` / `cat state: ...`,
  while preserving the literal cat mask, centered panel, state marker semantics,
  `--details`, watch, state/HTML/live/launcher behavior, and product-code
  rescue edits `0`; ledger row `39` records the practical result, and issue
  `#24` records the historical-path report-name closeout follow-up
- SP22f task `#34` landed practical from session `#63`: normal cat human output
  now uses `resident marker: ...` instead of `state marker: ...`, and the sample
  fixture message now says `mew-wisp is keeping VS Code in view without screen
  capture` instead of `Ghost is watching...`; the focused verifier, cat mask
  similarity, centered layout, resident panel, `--details`, watch,
  state/HTML/live/launcher behavior, and product-code rescue edits `0` were
  preserved; ledger row `40` records the practical result
- SP23a task `#35` first attempt stopped after session `#64` reached focused
  verifier green (`40 passed`) but timed out during closeout with no product
  diff and no report persisted; ledger row `41` records the failed attempt with
  rescue edits `0`, issue `#25` records the green-verifier/no-durable-artifact
  closeout problem, and issue `#23` was updated with another macOS Objective-C
  fork warning recurrence
- SP23a task `#36` retry stopped after session `#65` reached focused verifier
  green (`40 passed`) but timed out into `awaiting_approval`; the recovery
  `approve-all` control then replayed stale pending hunks and left the worktree
  clean with no product diff, so ledger row `42` records the failed attempt
  with rescue edits `0` and issue `#25` was updated with the recovery-path
  evidence
- SP23a task `#37` retry stopped after session `#66` could not express the
  required paired source/test hunk patch: batch `edit_file_hunks` is unsupported
  while standalone `edit_file_hunks` can edit only one file; ledger row `43`
  records the failed attempt with rescue edits `0`, and issue `#26` records the
  reusable implementation-lane blocker
- SP23a task `#38` landed practical from session `#67`: mew-authored staged
  dry-run source/test patches added the CLI-only speech bubble, normalized the
  tests around bubble-before-HUD ordering, preserved state/HTML/watch/live/launcher
  behavior, and passed the focused verifier (`40 passed`). Ledger row `44`
  records the practical result with rescue edits `0`; issue `#27` records the
  verifier-rollback polish finding exposed during the attempt
- SP24a task `#39` landed practical from session `#68`: mew-authored focused
  test coverage proves `--format human --form cat` can render explicit
  live-desk-shaped provider status/action evidence through the existing opt-in
  injected `desk_provider` path, keeps freshness/details/active-window/launcher
  diagnostics gated behind `--details`, avoids static `--desk-json` proof, and
  preserves the focused verifier (`41 passed`). Ledger row `45` records the
  practical result with rescue edits `0`; issue `#28` records the dry-run/target
  steering miss, and issue `#17` records prior closeout `git_diff` read-root
  evidence. Both issues are closed after upstream fixes; reopen only if the
  same behavior recurs in the next work
- SP24b task `#40` landed practical from sessions `#69` and `#70`:
  mew-authored CLI/main tests prove `--live-desk --format human --form cat`
  reaches the terminal resident surface through injected `live_desk_runner`
  seams without spawning real mew in automation, without launcher execution,
  without `--desk-json`, and with diagnostics gated behind `--details`. mew
  also made live-desk fallback details visible in human output and sanitized the
  human counts line so real desk `raw_grouped_details` stays in machine-readable
  state but does not leak into the form layer. Focused verifier passed (`44
  passed`), and an explicit repo-local real `--live-desk` smoke wrote sanitized
  human output to `/tmp/mew-wisp-sp24b-human.txt`. Ledger row `46` records the
  practical result with rescue edits `0`
- `mew chat` and `mew code` are represented as explicit command arrays
- launcher state remains dry-run by default with `side_effects: "none"` and
  `execution.status: "dry_run"`
- direct launcher execution is gated behind explicit `--execute-launchers`;
  automated tests use an injected runner and do not spawn real `mew`
- SP16 watch mode is now present: `--watch-count` runs exact bounded
  foreground iterations, `--watch` runs until operator interrupt, `--interval`
  controls injected/testable sleeping, CLI watch emits one JSONL record per
  iteration, and the historical HTML watch proof is now a SP19 removal target
- SP17 desk bridge is now present: static `--desk-json` fixture loading maps
  `sleeping`/`thinking`/`typing`/`alerting` into separate desk-derived presence,
  renders desk status/counts/details/primary_action in CLI state and the
  historical HTML surface, and exposes desk `primary_action` as a
  non-executable dry-run command intent
- SP18 live desk opt-in is now present: explicit `--live-desk` runs repo-local
  `./mew desk --json` without shell execution, maps nested and current
  top-level desk JSON through the same desk status/count/action surface, reruns
  during watch only when opted in, and converts failures into structured desk
  states
- live macOS probing remains explicit through `--live-active-window`
- existing default and `--desk-json` behavior still should not read live `.mew`
  state or import `src/mew/**`; live desk reads are limited to explicit
  `--live-desk`
- preserve the bounded deterministic presence loop without background
  monitoring or hidden capture
- preserve structured fallback for missing `osascript`, non-macOS platforms,
  permission denial, empty probe results, malformed output, and timeouts
- focused verifier remains:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
- keep `mew-companion-log` stable as the local fixture-tested companion surface
  set for future product planning and contract checks
- route the already-fixed structural write-scope blocker as closed issue `#1`
  evidence, not an active side-project blocker
- route the originally repeated same-file write-batch ergonomics blocker as
  closed issue `#3` evidence; SP18 first stopped before product edits on this
  blocker, recorded in ledger row `19`
- route the large patch-shaping blockers as closed issues `#14` and `#15`
  evidence; SP18 retry after the `#3` fix still stopped before product edits,
  recorded in ledger row `20`
- route the repeated stale failed-approval cleanup pattern as closed issue
  `#10` evidence for M6.16 implementation-lane hardening
- route the report-schema closeout gap as closed issue `#11` evidence for
  M6.16 implementation-lane hardening; SP16 still needed operator report JSON
  normalization, recorded in ledger row `17`, and SP17 needed report-schema plus
  stale schema-version closeout follow-up, recorded in ledger row `18`
- route the stale schema/version closeout gap as closed issue `#13` evidence for
  M6.16 implementation-lane hardening; SP18 closed the stale schema/title
  surfaces in `mew-ghost`
- route the SP18 top-level real desk JSON verifier gap as closed issue `#16`
  evidence; SP18 repaired it before commit with injected-runner coverage and
  real `--live-desk` proof
- route the final side-project `git_status`/`git_diff` closeout scope failure as
  closed issue `#17` evidence for implementation-lane hardening
- route watch-mode verifier semantics as closed issue `#12` evidence; SP16
  operator review confirmed multiple CLI records and HTML rewrite behavior
- route repeated pre-edit SP20a model timeouts as closed issue `#19` evidence
  for implementation-lane hardening; the working operator pattern was closing
  the stale session and retrying fresh with `--model-timeout 300`
- route task #27/session #56 invalid mixed read/write batch replay as open
  issue `#20` evidence for implementation-lane hardening; the working operator
  pattern was to stop reusing the stale session and retry from fresh task #28
- route task #29/session #58 verifier-rollback timeout as open issue `#21`
  evidence for implementation-lane hardening; task #30 reduced scope and
  repaired residual test assertions without Codex product-code rescue edits
- route task #31/session #60 report-schema closeout recurrence as open issue
  `#22` evidence for implementation-lane hardening; product tests passed and
  the operator rewrote only the local report JSON into the canonical schema
- route repeated SP22c/SP22d macOS Objective-C fork crash logs during closeout
  as open issue `#23` evidence for implementation-lane hardening; both product
  attempts passed their focused verifiers, but the work loop emitted unsafe
  fork-after-runtime-initialization diagnostics
- route task #33/session #62 stale `side_project: mew-ghost` report naming as
  open issue `#24` evidence for implementation-lane hardening; the operator
  corrected only the local report to the canonical `mew-wisp` side-project name
  before ledger append
- route task #35/session #64 and task #36/session #65 verifier-green speech
  bubble attempts with no durable product diff as open issue `#25` evidence for
  implementation-lane hardening; the second attempt showed the pending approval
  recovery path can replay stale hunks and still leave no materialized patch
- route task #37/session #66 paired source/test hunk tool-shape blocker as open
  issue `#26` evidence for implementation-lane hardening; the next retry should
  use staged standalone source/test approvals with deferred verification rather
  than requiring a one-shot multi-file hunk batch
- route task #38/session #67 near-complete verifier rollback as open issue
  `#27` evidence for implementation-lane hardening; the working operator
  pattern was dry-run/pending patches followed by deferred verification so
  useful hunks were not discarded after one narrow assertion failure
- preserve the current operating model for any future side-project cohort:
  current-repo `./mew`, side-project target directory, Codex as
  operator/reviewer/verifier, and rescue edits explicitly tracked

## Evidence

- Core M6.13.2 telemetry CLI exists:
  `mew side-dogfood template`, `mew side-dogfood append`, and
  `mew side-dogfood report`.
- Default ledger:
  `proof-artifacts/side_project_dogfood_ledger.jsonl`.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP19a on 2026-04-28: `rows_total=24`, five `failed`, sixteen `practical`,
  three `clean`, `success_rate=0.792`, `structural_repairs_required=5`,
  `rescue_edits_total=0`, and `codex_product_code_rescue_edits=0`. Ledger row
  `23` records the post-issue-18-close SP19 retry failure, and row `24`
  records the additive SP19a terminal human renderer.
- `./mew side-dogfood append --input
  experiments/mew-ghost/.mew-dogfood/reports/21-sp20a-human-watch-model-timeout-blocked.json`
  appended ledger row `25`: outcome `failed`, failure class
  `sp20a_repeated_model_timeout_before_product_edits`, rescue edits `0`, issue
  `#19` opened.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP20a on 2026-04-28: `rows_total=26`, six `failed`, seventeen `practical`,
  three `clean`, `success_rate=0.769`, `structural_repairs_required=6`,
  `rescue_edits_total=0`, and `codex_product_code_rescue_edits=0`. Ledger row
  `26` records the practical fresh-session SP20a attempt with no rescue edits.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP21a on 2026-04-28: `rows_total=27`, six `failed`, eighteen `practical`,
  three `clean`, `success_rate=0.778`, `structural_repairs_required=6`,
  `rescue_edits_total=0`, and `codex_product_code_rescue_edits=0`. Ledger row
  `27` records the practical cat form layer with no rescue edits.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP21b on 2026-04-29: `rows_total=29`, six `failed`, twenty `practical`,
  three `clean`, `success_rate=0.793`, `structural_repairs_required=6`,
  `rescue_edits_total=0`, and `codex_product_code_rescue_edits=0`. Ledger rows
  `28` and `29` record the image-based pixel cat sprite follow-ups with failure
  classes `cat_sprite_line_art_reviewer_followup` and
  `cat_sprite_visual_similarity_reviewer_followup`.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP21c on 2026-04-29: `rows_total=30`, six `failed`, twenty-one `practical`,
  three `clean`, `success_rate=0.800`, `structural_repairs_required=6`,
  `rescue_edits_total=0`, and `codex_product_code_rescue_edits=0`. Ledger row
  `30` records the 22x24 mask-similarity slice with failure class
  `similarity_requirement_repair_after_initial_source_edit`.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP21d/SP21e on 2026-04-29: `rows_total=32`, six `failed`,
  twenty-three `practical`, three `clean`, `success_rate=0.812`,
  `structural_repairs_required=6`, `rescue_edits_total=0`, and
  `codex_product_code_rescue_edits=0`. Ledger rows `31` and `32` record the
  compact HUD and reviewer polish slices with no Codex product-code rescue
  edits.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP21f/SP21g on 2026-04-29: `rows_total=34`, seven `failed`,
  twenty-four `practical`, three `clean`, `success_rate=0.794`,
  `structural_repairs_required=7`, `rescue_edits_total=0`, and
  `codex_product_code_rescue_edits=0`. Ledger row `33` records the blocked
  session-replay failure behind issue `#20`; row `34` records the centered cat
  terminal form retry.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP22a/SP22b on 2026-04-29: `rows_total=36`, eight `failed`,
  twenty-five `practical`, three `clean`, `success_rate=0.778`,
  `structural_repairs_required=8`, `rescue_edits_total=0`, and
  `codex_product_code_rescue_edits=0`. Ledger row `35` records the SP22a
  timeout after verifier rollback behind issue `#21`; row `36` records the
  visible-identity/resident-HUD polish retry.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP22c on 2026-04-29: `rows_total=37`, eight `failed`, twenty-six
  `practical`, three `clean`, `success_rate=0.784`,
  `structural_repairs_required=8`, `rescue_edits_total=0`, and
  `codex_product_code_rescue_edits=0`. Ledger row `37` records the resident
  HUD panel polish with failure class
  `report_schema_closeout_gap_after_panel_polish`; issue `#22` records the
  recurring non-appendable report closeout gap.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP22d on 2026-04-29: `rows_total=38`, eight `failed`, twenty-seven
  `practical`, three `clean`, `success_rate=0.789`,
  `structural_repairs_required=8`, `rescue_edits_total=0`, and
  `codex_product_code_rescue_edits=0`. Ledger row `38` records the centered
  resident surface with failure class
  `source_panel_centering_helper_prefix_repair`.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP22e on 2026-04-29: `rows_total=39`, eight `failed`, twenty-eight
  `practical`, three `clean`, `success_rate=0.795`,
  `structural_repairs_required=8`, `rescue_edits_total=0`, and
  `codex_product_code_rescue_edits=0`. Ledger row `39` records the resident
  header-copy polish with failure class
  `report_side_project_stale_name_followup`; issue `#24` records the stale
  historical path/product-name closeout gap.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  SP22f on 2026-04-29: `rows_total=40`, eight `failed`, twenty-nine
  `practical`, three `clean`, `success_rate=0.800`,
  `structural_repairs_required=8`, `rescue_edits_total=0`, and
  `codex_product_code_rescue_edits=0`. Ledger row `40` records the bounded
  copy cleanup with failure class `copy_cleanup_bounded`.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  the first SP23a attempt on 2026-04-29: `rows_total=41`, nine `failed`,
  twenty-nine `practical`, three `clean`, `success_rate=0.780`,
  `structural_repairs_required=9`, `rescue_edits_total=0`, and
  `codex_product_code_rescue_edits=0`. Ledger row `41` records the failed
  speech-bubble closeout timeout with failure class
  `speech_bubble_closeout_timeout_after_verifier_pass_left_no_diff`.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  the second SP23a attempt on 2026-04-29: `rows_total=42`, ten `failed`,
  twenty-nine `practical`, three `clean`, `success_rate=0.762`,
  `structural_repairs_required=10`, `rescue_edits_total=0`, and
  `codex_product_code_rescue_edits=0`. Ledger row `42` records the failed
  pending-approval recovery with failure class
  `speech_bubble_pending_approval_stale_hunks_after_verifier_pass`.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  the third SP23a attempt on 2026-04-29: `rows_total=43`, eleven `failed`,
  twenty-nine `practical`, three `clean`, `success_rate=0.744`,
  `structural_repairs_required=11`, `rescue_edits_total=0`, and
  `codex_product_code_rescue_edits=0`. Ledger row `43` records the paired
  source/test hunk tool-shape blocker with failure class
  `speech_bubble_paired_multifile_hunks_blocked_by_batch_tool_schema`.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  the fourth SP23a attempt on 2026-04-29: `rows_total=44`, eleven `failed`,
  thirty `practical`, three `clean`, `success_rate=0.750`,
  `structural_repairs_required=11`, `rescue_edits_total=0`, and
  `codex_product_code_rescue_edits=0`. Ledger row `44` records the practical
  speech-bubble slice with failure class
  `speech_bubble_deferred_dry_run_workaround_after_verifier_rollback`; issue
  `#27` records the reusable verifier-rollback polish finding.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  the SP19 blocked attempt on 2026-04-28: `rows_total=22`, four `failed`,
  fifteen `practical`, three `clean`, `success_rate=0.818`,
  `structural_repairs_required=4`,
  `rescue_edits_total=0`, and `codex_product_code_rescue_edits=0`.
- `./mew side-dogfood report --json` returned a valid telemetry report after
  the SP18 completion on 2026-04-28: `rows_total=21`, three `failed`,
  fifteen `practical`, three `clean`, `success_rate=0.857`,
  `structural_repairs_required=3`,
  `rescue_edits_total=0`, and `codex_product_code_rescue_edits=0`.
- Product naming decision on 2026-04-28: the second side project should move
  forward as `mew-wisp`, because `pet` makes the resident AI feel owned and
  fixed while `wisp` names a terminal presence surface whose displayed form can
  change later. `mew-ghost` remains historical context for SP12-SP18.
- `./mew side-dogfood report --json` returned a valid telemetry report with
  twelve `mew-companion-log` rows on 2026-04-26: `rows_total=12`, one `failed`,
  eight `practical`, three `clean`, `success_rate=0.917`,
  `structural_repairs_required=1`, and `rescue_edits_total=0`.
- `side-pj-mew-impl` skill exists at
  `.codex/skills/side-pj-mew-impl/SKILL.md`.
- First side project selected: `mew-companion-log`.
- First side project rationale: medium-sized, local-first, fixture-testable,
  product-relevant, and unlikely to hide implementation-lane failures behind
  GUI/platform friction.
- Task `#1` / session `#1` first attempted the SP1 scaffold with Codex CLI as
  `operator` and mew as first implementer. After inspecting the empty target
  directory, mew twice stopped before writes with
  `write batch is limited to write/edit tools under tests/** and src/mew/**`
  `with at least one of each`, including a second attempt with
  `--model gpt-5.5` and explicit side-project scope steering.
- Failed-attempt local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/1-scaffold-write-scope-guard-blocked.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `1`;
  outcome `failed`, failure class
  `side_project_write_scope_guard_rejected_experiments_paths`.
- Problem issue closed:
  `https://github.com/mkXultra/mew/issues/1`.
- After issue `#1` closed and `origin/main` was pulled, task `#1` retried with
  `--model gpt-5.5`. Mew authored:
  `experiments/mew-companion-log/companion_log.py`,
  `fixtures/sample_session.json`, `tests/test_companion_log.py`, and
  `README.md`.
- Reviewer follow-ups were required only for README command accuracy:
  the stable verifier must include `--no-testmon`, and usage examples must use
  `UV_CACHE_DIR=.uv-cache uv run python` because plain `python` is unavailable
  in this environment. Mew authored both follow-up edits.
- Successful-attempt local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/1-scaffold-practical-after-write-scope-repair.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `2`;
  outcome `practical`, failure class
  `readme_command_polish_after_successful_scaffold`.
- Final verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `4 passed`.
- README usage commands were manually verified with
  `UV_CACHE_DIR=.uv-cache uv run python ...` for stdout and `--output`.
- Task `#2` / session `#4` added the first SP2 surface with Codex CLI as
  `operator` and mew as first implementer. Mew authored the fixture-driven
  `--mode morning-journal` renderer, updated fixture data, README usage, and
  snapshot-style tests under `experiments/mew-companion-log`.
- Morning journal local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/2-morning-journal-clean.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `3`;
  outcome `clean`, failure class `none_observed`, `rescue_edits=0`.
- Morning journal verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `6 passed`. The default report CLI, morning journal stdout, and
  morning journal `--output` path were also verified.
- Task `#3` / session `#5` added the second SP2 surface with Codex CLI as
  `operator` and mew as first implementer. Mew authored the fixture-driven
  `--mode evening-journal` renderer, updated fixture data, README usage, and
  snapshot-style tests under `experiments/mew-companion-log`.
- Evening journal local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/3-evening-journal-clean.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `4`;
  outcome `clean`, failure class `none_observed`, `rescue_edits=0`.
- Evening journal verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `8 passed`. The default report CLI, morning journal stdout, evening
  journal stdout, and evening journal `--output` path were also verified.
- Task `#4` / sessions `#6` and `#7` added the final SP2 dream/learning
  surface with Codex CLI as `operator` and mew as first implementer. Session
  `#6` authored the fixture-driven `--mode dream-learning` renderer, fixture
  data, README fixture description, and snapshot-style test under
  `experiments/mew-companion-log`.
- Reviewer follow-up was required because the first pass lacked a README Usage
  command for `--mode dream-learning` and a focused CLI stdout test for that
  mode. Session `#7` authored both follow-up edits.
- Dream/learning local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/4-dream-learning-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `5`;
  outcome `practical`, failure class
  `readme_cli_test_followup_after_dream_learning`, `rescue_edits=0`.
- Dream/learning verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `10 passed`. The default report CLI, morning journal stdout,
  evening journal stdout, dream/learning stdout, dream/learning `--output`
  path, and `git diff --check` were also verified.
- SP5 summary artifact:
  `docs/M6_16_SIDE_PROJECT_DOGFOOD_SUMMARY_2026-04-26.md`.
- SP5 conclusion: the first M6.16 slice should target implementation closeout
  completeness because practical rows were caused by missing README/CLI/test
  acceptance proof, while first-edit latency was acceptable and structural
  failure already routed through M6.14.
- Task `#5` / session `#8` added the optional SP4 static research digest with
  Codex CLI as `operator` and mew as first implementer. Mew authored the
  fixture-driven `--mode research-digest` renderer, deterministic ranking over
  static fixture entries, README usage and output-file notes, snapshot test,
  CLI stdout test, output-file test, and fixture shape assertions under
  `experiments/mew-companion-log`.
- A pre-edit operator follow-up was required because the first write batch
  proposed multiple edits to `README.md`; mew collapsed same-file hunks and
  authored the final patch without Codex product-code rescue.
- Research digest local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/5-research-digest-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `6`;
  outcome `practical`, failure class
  `same_file_write_batch_guard_followup_before_research_digest`,
  `rescue_edits=0`.
- Research digest verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `13 passed`. The default report CLI, morning journal stdout,
  evening journal stdout, dream/learning stdout, research digest stdout,
  research digest `--output` path, and `git diff --check` were also verified.
- Task `#6` / session `#9` added the SP6 mew state companion export with Codex
  CLI as `operator` and mew as first implementer. Mew authored the
  fixture-driven `--mode state-brief` renderer, static mew-state-like fixture,
  README usage/output-file examples, snapshot test, CLI stdout test,
  output-file test, and fixture shape assertions under
  `experiments/mew-companion-log`.
- Bundle local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/6-state-brief-clean.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `7`;
  outcome `clean`, failure class `none_observed`, `rescue_edits=0`.
- State brief verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `17 passed`. The default report CLI, morning journal stdout,
  evening journal stdout, dream/learning stdout, research digest stdout, state
  brief stdout, state brief `--output` path, `git diff --check`, and a scoped
  search for `src/mew` / live `.mew` coupling were also verified.
- Task `#7` / session `#10` added the SP7 multi-fixture companion bundle with
  Codex CLI as `operator` and mew as first implementer. Mew authored the
  fixture-driven `--mode bundle` renderer, static bundle manifest, README
  usage/output-file examples, snapshot test, CLI stdout test, output-file test,
  ordering/grouping assertions, missing-fixture behavior coverage, and fixture
  shape assertions under `experiments/mew-companion-log`.
- State brief local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/7-bundle-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `8`;
  outcome `practical`, failure class
  `same_file_write_batch_retry_timeout_after_bundle_verifier_failure`,
  `rescue_edits=0`.
- Bundle verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `22 passed`. Bundle stdout, bundle `--output`, default report
  stdout, state brief stdout, `git diff --check`, and a scoped no-core/no-live
  coupling search were also verified.
- Reusable polish issue opened:
  `https://github.com/mkXultra/mew/issues/4`.
- Task `#8` / sessions `#11` and `#12` added the SP8 multi-day companion
  archive index with Codex CLI as `operator` and mew as first implementer.
  Session `#11` reached the right archive-index implementation shape but the
  first verifier failed because a new stdout ordering assertion compared
  headings across different day sections. Mew chose a remember/checkpoint under
  high pressure, so Codex restarted a fresh mew session with the repair plan.
  Session `#12` authored the final `--mode archive-index` renderer, static
  archive fixture, README usage/output-file examples, snapshot test, CLI stdout
  test, output-file test, empty-day behavior coverage, and fixture shape
  assertions under `experiments/mew-companion-log`.
- Archive index local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/8-archive-index-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `9`;
  outcome `practical`, failure class
  `archive_index_cross_day_ordering_retry_after_verifier_failure`,
  `rescue_edits=0`.
- Archive index verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `26 passed`. Archive-index stdout, archive-index `--output`, bundle
  stdout, `git diff --check`, and a scoped no-core/no-live/no-crawl coupling
  search were also verified.
- Reusable polish issue opened:
  `https://github.com/mkXultra/mew/issues/5`.
- Task `#9` / sessions `#13` through `#17` added the SP9 issue and dogfood
  ledger digest with Codex CLI as `operator` and mew as first implementer.
  Session `#13` stopped before product edits after a duplicated-context edit
  failure and same-file write-batch wait, so Codex restarted fresh. Session
  `#14` authored the final `--mode dogfood-digest` renderer, static dogfood
  digest fixture, README usage/output-file examples, failure-class grouping
  tests, issue-link rendering tests, stdout/output-file tests, and fixture
  shape assertions under `experiments/mew-companion-log`. Reviewer follow-up in
  sessions `#15` through `#17` was required to preserve canonical
  `rescue_edits` semantics and align static issue summaries with real side-pj
  issue `#4` and `#5`.
- Dogfood digest local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/9-dogfood-digest-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `10`;
  outcome `practical`, failure class
  `dogfood_digest_ledger_semantics_repair_after_write_batch_retries`,
  `rescue_edits=0`.
- Dogfood digest verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `30 passed`. Dogfood-digest stdout, dogfood-digest `--output`,
  `git diff --check`, and a scoped no-core/no-live/no-network/no-crawl coupling
  search were also verified.
- Reusable polish issue opened:
  `https://github.com/mkXultra/mew/issues/6`.
- Task `#10` / sessions `#18` and `#19` added the SP10 companion export
  contract with Codex CLI as `operator` and mew as first implementer. Session
  `#18` authored `experiments/mew-companion-log/CONTRACT.md`, a README pointer,
  and an all-mode output-file compatibility test proving every documented mode
  renders and writes a markdown output file from a local fixture. Reviewer
  follow-up in session `#19` was required because the first contract documented
  the `dogfood-digest` heading as `# Companion Dogfood Digest:` while the
  renderer emits `# Dogfood Digest:`.
- Export contract local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/10-export-contract-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `11`;
  outcome `practical`, failure class
  `contract_heading_mismatch_reviewer_followup`, `rescue_edits=0`.
- Export contract verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `31 passed`. `git diff --check` and a scoped no-core/no-live/no-network/no-crawl
  coupling search were also verified.
- Reusable polish issue opened:
  `https://github.com/mkXultra/mew/issues/7`.
- Task `#11` / sessions `#20` through `#22` added the SP11 second side-project
  gate recommendation with Codex CLI as `operator` and mew as first implementer.
  Mew authored `experiments/mew-companion-log/SECOND_SIDE_PROJECT_GATE.md` and
  a local SP11 report. The gate compares SP6-SP10 ledger rows `7` through `11`,
  repeated failure classes, `rescue_edits=0`, first-edit latency, and issue
  queue outcomes. Reviewer follow-up was required to include SP7 issue `#4` in
  the issue queue comparison and to correct local report proof paths before
  ledger append.
- Second side-project gate local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/11-second-side-project-gate-recommendation.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `12`;
  outcome `practical`, failure class
  `second_side_project_gate_recommends_core_hardening_before_new_cohort`,
  `rescue_edits=0`.
- Gate recommendation:
  pause new side-project implementation and feed the first side-project cohort
  into core M6.16/M9/M11 before starting a second isolated side project.
- Gate verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py`
  returned `31 passed`. `git diff --check` was also verified.
- Task `#12` / sessions `#23` through `#25` opened the second side-project arc
  and added the SP12 mew-ghost macOS shell scaffold with Codex CLI as
  `operator` and mew as first implementer. Operator bookkeeping first opened
  SP12-SP15 in `SIDE_PROJECT_ROADMAP.md` and this status file. Session `#23`
  exposed setup friction because `experiments/mew-ghost` did not exist, then a
  model timeout; operator created the empty target directory and restarted with
  narrower guidance. Session `#24` authored the four-file scaffold under
  `experiments/mew-ghost`: README, `ghost.py`, static fixture, and focused
  tests. Mew repaired one focused verifier failure caused by a source-string
  assertion and reached `7 passed`. Session `#25` completed reviewer follow-up
  by changing README examples to
  `UV_CACHE_DIR=.uv-cache uv run python ...` and adding README usage coverage.
- mew-ghost SP12 local report:
  `experiments/mew-ghost/.mew-dogfood/reports/12-macos-shell-scaffold-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `13`;
  outcome `practical`, failure class
  `mew_ghost_scaffold_verifier_repair_and_readme_command_followup`,
  `rescue_edits=0`.
- mew-ghost SP12 verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
  returned `8 passed`. The state CLI, HTML `--output` path, rendered HTML
  content check, and `git diff --check` were also verified.
- Task `#13` / session `#26` added the SP13 explicit live macOS probe
  integration with Codex CLI as `operator` and mew as first implementer. The
  first resume attempt hit `HTTP 401 token_expired` with the default local
  auth before product edits; retrying with `--auth /Users/mk/.codex/auth.json`
  allowed the same session to continue. Mew authored the opt-in
  `--live-active-window` path, injectable `osascript` runner/provider,
  structured fallback reasons, README usage, and hermetic tests under
  `experiments/mew-ghost`.
- The first SP13 write batch failed the focused verifier because one stale test
  assertion still expected `mew-ghost.sp12.v1`; mew repaired in the same
  session and the corrected batch passed. Operator rejected three stale
  approvals from the failed batch after the corrected batch had already applied.
- mew-ghost SP13 local report:
  `experiments/mew-ghost/.mew-dogfood/reports/13-live-macos-probe-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `14`;
  outcome `practical`, failure class
  `stale_failed_approval_cleanup_after_live_probe_verifier_repair`,
  `rescue_edits=0`.
- mew-ghost SP13 verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
  returned `13 passed`. Default state CLI, explicit live opt-in state CLI,
  HTML `--output`, state `--output`, rendered HTML content checks,
  `git diff --check`, and scoped no-core/no-live-state coupling searches were
  also verified.
- Reusable polish issue opened:
  `https://github.com/mkXultra/mew/issues/10`.
- Task `#14` / session `#27` added the SP14 bounded presence loop with Codex
  CLI as `operator` and mew as first implementer. Mew authored deterministic
  presence classification for `idle`, `attentive`, `coding`, `waiting`, and
  `blocked`; bounded refresh snapshots; the rendered HTML presence section;
  README refresh-contract documentation; CLI `--refresh-count`; and hermetic
  tests under `experiments/mew-ghost`.
- Session `#27` first hit an invalid JSON model response before edits, then a
  source-only batch whose verifier failed because tests and README were not
  updated. After operator rejection, mew produced a complete source/tests/README
  batch; the first complete batch failed one expectation for Safari notes
  classification, then mew repaired it in the same session.
- Stale failed approvals remained after the corrected batch passed, repeating
  issue `#10`; the issue was updated with SP14 evidence.
- mew-ghost SP14 local report:
  `experiments/mew-ghost/.mew-dogfood/reports/14-presence-loop-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `15`;
  outcome `practical`, failure class
  `presence_loop_json_parse_source_only_and_stale_approval_repair`,
  `rescue_edits=0`.
- mew-ghost SP14 verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
  returned `15 passed`. Default state CLI with refresh count, explicit live
  opt-in state CLI, HTML `--output`, state `--output`, rendered HTML content
  checks, `git diff --check`, and scoped no-core/no-live-state coupling
  searches were also verified.
- Task `#15` / sessions `#28` through `#30` added the SP15 launcher contract
  with Codex CLI as `operator` and mew as first implementer. Mew authored
  explicit `mew chat` and `mew code` command intents, default dry-run execution
  metadata, the `--execute-launchers` opt-in gate, injected-runner tests that do
  not spawn real `mew`, README usage, and the SP15 local report under
  `experiments/mew-ghost`.
- Session `#28` produced the first launcher-contract batch, but verifier
  failure left stale pending approvals after SP14 schema expectations were not
  fully updated. Operator rejected the stale failed approvals and updated issue
  `#10` with SP15 recurrence evidence. Session `#29` completed the product
  implementation and verifier pass. Session `#30` rewrote only the local
  report into canonical side-dogfood schema after operator review found the
  first report was not appendable.
- mew-ghost SP15 local report:
  `experiments/mew-ghost/.mew-dogfood/reports/15-launcher-contract-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `16`;
  outcome `practical`, failure class
  `launcher_contract_retry_and_report_schema_followup`, `rescue_edits=0`.
- mew-ghost SP15 verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
  returned `16 passed`. `git diff --check`, dry-run state output, HTML output,
  rendered HTML content checks, explicit live-probe fallback output, and
  temporary side-dogfood ledger append validation were also verified. Real
  `--execute-launchers` execution remains intentionally outside automated
  verification and requires local operator opt-in.
- Task `#16` / session `#35` added the SP16 foreground watch mode with Codex
  CLI as `operator` and mew as first implementer. After all side-pj issues were
  closed and latest `origin/main` was pulled, mew authored the true watch-mode
  product patch: `--watch-count` exact bounded iterations, interruptible
  `--watch`, `--interval`, injectable sleeper/clock, one JSONL CLI record per
  iteration, repeated HTML `--output` rewrites with freshness metadata, and
  README usage. Launcher execution remains dry-run unless
  `--execute-launchers` is explicitly supplied, and live macOS probing remains
  gated by `--live-active-window`.
- Session `#35` first failed with overlapping `ghost.py` edit hunks; after
  operator steering, mew recovered with a full-file write proposal and the
  focused verifier passed. Mew then twice wrote noncanonical report JSON; the
  operator normalized only the local evidence report into the canonical
  side-dogfood schema. No operator product-code rescue edits were made.
- mew-ghost SP16 local report:
  `experiments/mew-ghost/.mew-dogfood/reports/16-watch-mode-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `17`;
  outcome `practical`, failure class
  `watch_mode_report_schema_repair_after_overlapping_hunk_retry`,
  `rescue_edits=0`.
- mew-ghost SP16 verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
  returned `19 passed`. `git diff --check`, CLI JSONL watch proof, HTML
  rewrite/freshness proof, and temporary side-dogfood ledger append validation
  also passed. Real macOS Accessibility behavior and real launcher subprocess
  execution remain intentionally outside automated verification and require
  explicit local operator opt-in.
- Task `#17` / session `#36` added the SP17 desk bridge with Codex CLI as
  `operator` and mew as first implementer. Mew authored static `--desk-json`
  fixture loading, desk pet-state mapping, CLI/HTML status/counts/details and
  primary_action rendering, non-executable desk primary_action intent, watch
  reload behavior, README usage, focused tests, and local report evidence under
  `experiments/mew-ghost`.
- Reviewer follow-up session `#37` corrected stale prior-slice SP16/sp16
  schema/docstring/HTML/test wording after the desk bridge changed the state
  shape. No operator product-code rescue edits were made.
- mew-ghost SP17 local report:
  `experiments/mew-ghost/.mew-dogfood/reports/17-desk-bridge-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `18`;
  outcome `practical`, failure class
  `schema_version_closeout_followup_after_report_schema_repair`,
  `rescue_edits=0`.
- Problem issue opened:
  `https://github.com/mkXultra/mew/issues/13`.
- mew-ghost SP17 verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
  returned `23 passed`. `git diff --check`, static desk state output, bounded
  HTML watch output, stale `SP16|sp16` audit, and temporary side-dogfood ledger
  append validation also passed.
- Task `#18` / sessions `#38` and `#39` attempted SP18 live desk opt-in with
  Codex CLI as `operator` and mew as first implementer. Session `#38` stopped
  before product edits after repeated Codex Web API disconnects. Session `#39`
  generated a substantial source/tests/README/report patch, but the first
  `ghost.py` edit failed because one hunk matched two locations; after focused
  steering, the loop repeatedly returned write-batch collapse guidance instead
  of applying a corrected single-file edit/write.
- No product files were changed and no operator product-code rescue edits were
  made. The existing write-batch ergonomics issue `#3` was reopened instead of
  creating a duplicate.
- mew-ghost SP18 blocked local report:
  `experiments/mew-ghost/.mew-dogfood/reports/18-live-desk-opt-in-blocked.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `19`;
  outcome `failed`, failure class
  `same_file_write_batch_guard_recurrence_before_sp18_edit`,
  `rescue_edits=0`, `repair_required=true`.
- Problem issue reopened:
  `https://github.com/mkXultra/mew/issues/3`.
- Task `#18` / session `#40` retried SP18 after issue `#3` was closed by
  `14b670a` and merged into `side/r2`. Mew reached edit planning, but the
  source-only dry-run failed the focused verifier because paired tests/docs were
  not updated yet. A complete source/tests/README/report batch then failed
  because one `ghost.py` hunk matched two locations. After steering, the next
  complete batch failed because `ghost.py` hunks overlapped. The operator opened
  issue `#14` for the remaining hunk-shaping failure.
- Mew was then steered to avoid `edit_file_hunks` for `ghost.py` and use
  full-file `write_file`; it stopped with an exact blocker that the complete
  three-file `write_file` JSON batch was too large/risky to emit safely. The
  operator opened issue `#15` for the large write-file patch-shaping limit.
- No product files were changed and no operator product-code rescue edits were
  made in session `#40`.
- mew-ghost SP18 retry blocked local report:
  `experiments/mew-ghost/.mew-dogfood/reports/18-live-desk-opt-in-blocked-after-write-shape-limit.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `20`;
  outcome `failed`, failure class
  `large_patch_write_shape_limit_after_hunk_repair`, `rescue_edits=0`,
  `repair_required=true`.
- Problem issues opened:
  `https://github.com/mkXultra/mew/issues/14` and
  `https://github.com/mkXultra/mew/issues/15`.
- After issues `#14` and `#15` closed, task `#18` resumed in sessions `#40`
  and `#41` with Codex CLI as `operator` and mew as first implementer. Mew
  authored explicit `--live-desk` support under `experiments/mew-ghost`, kept
  default and `--desk-json` paths deterministic and non-live, added injected
  runner/provider tests, updated README terminal/HTML examples, and wrote the
  practical report.
- Reviewer follow-ups were required before commit. First, issue `#13` was still
  visible because the SP18 state shape initially kept stale SP17 schema/title
  strings; mew updated `SCHEMA_VERSION`, HTML title, parser description, and
  test expectations to SP18 while preserving fixture labels. Second, real
  `--live-desk` proof exposed issue `#16`: current top-level
  `./mew desk --json` payloads with `pet_state`/`focus` normalized to
  `unknown` because tests only covered nested fixture-like desk payloads. Mew
  repaired the normalizer and added injected coverage for the current top-level
  shape. A final live primary-action wording polish was also mew-authored.
- No operator product-code rescue edits were made. The operator only updated
  the report evidence after real live-desk proof and opened issue `#17` for the
  recurring final `git_status`/`git_diff` allow-read closeout failure.
- mew-ghost SP18 practical local report:
  `experiments/mew-ghost/.mew-dogfood/reports/18-live-desk-opt-in-practical.json`.
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `21`;
  outcome `practical`, failure class
  `sp18_live_desk_retry_after_prior_blocked_attempts`, `rescue_edits=0`,
  `repair_required=false`.
- SP18 verification passed:
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
  returned `28 passed`. `git diff --check`, real state output
  `UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --live-desk --output /tmp/mew-ghost-live-state.json`,
  and bounded real HTML watch
  `UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format html --output /tmp/mew-ghost-live-desk.html --live-desk --watch-count 2 --interval 0`
  also passed.

## Missing Proof

- SP1 through SP11 are closed for the first `mew-companion-log` cohort.
- SP12 is closed for the second `mew-ghost` cohort.
- SP13 is closed for the second `mew-ghost` cohort.
- SP14 is closed for the second `mew-ghost` cohort.
- SP15 is closed for the second `mew-ghost` cohort.
- SP16 is closed for the second `mew-ghost` cohort.
- SP17 is closed for the second `mew-ghost` cohort.
- SP18 is closed for the second `mew-ghost` cohort.
- SP19 broad HTML removal remains deferred/partial: task `#19` / sessions `#42`
  and `#43` did not land product edits, issue `#18` is closed, and the forward
  terminal path advanced through additive SP19a-SP21e slices instead.
- SP20 is closed: foreground human watch now prints terminal surfaces instead
  of JSONL when `--format human` is selected.
- SP21 is closed: swappable `default`/`cat` forms, the `cat.png`-derived
  sprite, compact HUD, `--details` diagnostics, and focused regression tests
  are in place.
- SP22 is closed: the fixture-first terminal surface now has a centered cat
  form, resident-facing copy, and fixed-width HUD panel.
- SP23 is closed: the fixture-first terminal surface now has an ASCII speech
  bubble before the resident HUD, focused tests, and terminal proof output.
- SP24 is closed: reconnecting the CLI-first wisp to explicit live mew desk
  output now has injected-provider, CLI/main injected-runner, fallback, sanitized
  human-details, and real repo-local smoke proof.
- Real local execution of `--execute-launchers` is intentionally unverified by
  automation because it would spawn `mew chat` and `mew code`; the opt-in gate
  is covered by injected-runner tests and dry-run output proof.
- Real macOS Accessibility behavior for `--live-active-window` remains
  intentionally unverified by automation; structured fallback and injected
  provider paths are covered.
- Issue `#13` was resolved for `mew-ghost` by the SP18 schema/title closeout.
- Issue `#16` was resolved before commit by adding top-level real desk JSON
  normalization coverage and proof.
- Issue `#17` was resolved after the SP18 closeout-scope finding was recorded
  and closed upstream.
- Issue `#18` is closed and retained as evidence for the SP19 broad HTML
  removal blocker; the side project continued by splitting terminal-first work
  into smaller mew-first slices.

## Next Action

Choose the next side-project move:

1. define the next side-project milestone before starting more mew-wisp work;
   SP24 currently closes the planned side-project roadmap
2. keep state/JSON output as the machine-readable proof path while preserving
   the text-based human terminal speech bubble
3. preserve the old `mew-ghost` name only where it is historical evidence for
   SP12-SP18 or the pre-rename implementation path
4. keep broad live-state coupling deferred; SP24 should reconnect through one
   small adapter boundary rather than turning mew-wisp into a hidden monitor
5. before any new mew coding operation, run the repo-root sync rule from
   `/Users/mk/dev/personal-pj/mew_side_pj`

## Non-Goals

- do not implement outside the isolated second side-project path for the
  `mew-wisp` arc; until SP19 decides the path rename, that path is still
  `experiments/mew-ghost`
- do not treat Codex CLI implementation as mew-first autonomy credit
- do treat Codex CLI operating mew as `operator`, not `implementer`
- do not make GitHub issues for normal progress; create one `[side-pj]` issue
  only when mew cannot implement after bounded operator steering or a real
  problem needs main-side action, or when a reusable M6.16 polish finding is
  visible in the ledger
- do not change core mew unless the side project exposes a classified M6.14
  repair blocker or a later M6.16 measured hardening slice
- do not read live `.mew` state, import `src/mew/**`, use screen capture,
  keystroke monitoring, TTS, network-heavy services, background monitoring, or
  native packaging in the `mew-wisp` arc
- do not continue investing in browser/HTML output for `mew-wisp`; terminal
  and state/JSON outputs are the intended surfaces
- do not make the visible character a fixed identity; keep forms/skins
  replaceable
