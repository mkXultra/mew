# Mew Side Projects for Real Dogfooding

This file preserves side-project ideas that mew can build as real dogfood.
These are not core roadmap milestones. They are independent projects that can
prove whether mew is useful as a passive AI coding companion without risking the
core execution layer.

## Dogfooding Rule

- Prefer projects that can live under `experiments/<name>` or another isolated
  directory.
- Avoid core changes unless the side project exposes a small, concrete friction.
- Each project should have a demo command, a short README, and a dogfood report.
- Use `mew code <task-id>` or `mew work --live` to let mew help choose, inspect,
  implement, verify, and summarize the work.
- If a project requires sensitive permissions, add explicit opt-in gates before
  implementation.

## Selection Criteria

- Passive-AI relevance: Does this prove mew can notice, remember, report, or act
  without constant prompting?
- Isolation: Can it be committed independently from core?
- Demo value: Can a human see the result quickly?
- Safety: Can it run locally without surprising the user?
- Learning value: Will it expose real mew cockpit/recovery/memory friction?

## Recommended First Picks

1. `mew-dream`: closest to passive self-improvement and low core risk.
2. `mew-journal`: directly tests whether mew can summarize days and preserve
   continuity.
3. `mew-morning-paper`: tests passive research and preference learning.
4. `mew-bond`: tests cross-task personality and self-memory.
5. `mew-desk`: high demo value, but more frontend/platform work.

## Project Cards

### P-01: mew-desk

Goal: A desktop resident pet that reflects mew state.

Scope:
- Menu bar or tray app.
- Small cat/mascot window with states such as `sleeping`, `thinking`,
  `typing`, and `alerting`.
- Poll or watch `.mew/state.json` and show a compact `mew focus` summary.

First dogfood slice:
- Build an isolated prototype under `experiments/mew-desk`.
- Read a static sample state file and render the current mood/status.

Why it matters:
- Makes mew visible as a resident presence.
- Strong demo value, but does not by itself prove passive autonomy.

Core risk: low if kept isolated.

### P-02: mew-journal

Goal: Morning and evening reports generated from mew state.

Status:
- First isolated prototype exists under `experiments/mew-journal`.
- Dogfood task #79 used work session #105 and `mew work --ai` planning to pick
  the smallest slice.
- The prototype generates one `.mew/journal/YYYY-MM-DD.md` file with Morning
  and Evening sections from tasks, done-task notes, open questions, active work
  sessions, and runtime effects.
- Latest validation: `uv run pytest -q experiments/mew-journal` passed with
  `5 passed`.

Scope:
- Write `.mew/journal/YYYY-MM-DD.md`.
- Morning: yesterday, today's top tasks, and one short mew note.
- Evening: progress, stuck points, open questions, and tomorrow hints.
- Optional Obsidian-friendly markdown output.

First dogfood slice:
- Generate one journal markdown file from existing tasks, work sessions, and
  runtime effects.

Why it matters:
- Tests whether mew can preserve continuity for humans and models.
- Good bridge from task-local memory to day-scale memory.

Core risk: low.

### P-03: mew-voice

Goal: Let mew speak a few carefully timed messages.

Scope:
- Pluggable TTS backend such as macOS `say`, OpenAI TTS, or ElevenLabs.
- Daily limit and quiet-hours gate.
- Never speak during detected focus mode unless explicitly allowed.

First dogfood slice:
- A local-only `say` prototype that reads the latest outbox item.

Why it matters:
- Gives mew presence, but can become annoying quickly.

Core risk: low if opt-in.

### P-04: mew-peek

Goal: Let mew occasionally inspect the screen and offer help when the user seems
stuck.

Scope:
- Explicit opt-in screen capture.
- Exclusion list for private apps/windows.
- Vision model summary with conservative intervention rules.

First dogfood slice:
- Mock screenshot analysis from saved images, not live screen capture.

Why it matters:
- Very strong passive-AI signal: mew can notice context without being asked.
- Privacy risk is high, so this should not be first.

Core risk: medium unless isolated and gated.

### P-05: mew-dream

Goal: Present overnight self-improvement as "dreams" that mew remembers.

Status:
- First isolated prototype exists under `experiments/mew-dream`.
- Dogfood task #75 added dream `## Learnings` output from explicit
  `learnings`/`changes`/`decisions` and recent done-task notes.
- Dogfood task #76 added active work-session continuity output.
- Latest validation: `uv run pytest -q` passed with `707 passed, 6 subtests
  passed`.

Scope:
- Write `.mew/dreams/YYYY-MM-DD.md`.
- Summarize what mew attempted, learned, changed, or decided not to change.
- Link to tasks, work sessions, commits, and verification output.

First dogfood slice:
- Build `experiments/mew-dream` as a markdown generator over existing mew state.

Why it matters:
- Closest side project to the passive self-improvement product story.
- Helps answer whether mew is becoming a resident entity rather than a command.

Core risk: low.

### P-06: mew-morning-paper

Goal: Overnight research digest tailored to the user's interests.

Status:
- First isolated prototype exists under `experiments/mew-morning-paper`.
- Dogfood task #81 used work session #107 and `mew work --ai` planning to pick
  the smallest slice.
- The prototype ranks a static feed JSON against local interest tags and writes
  `.mew/morning-paper/YYYY-MM-DD.md`.
- Latest validation: `uv run pytest -q experiments/mew-morning-paper` passed
  with `6 passed`.

Scope:
- Read configured feeds such as HN, RSS, GitHub trending, or arXiv.
- Score items against local interest tags.
- Write a morning markdown digest.

First dogfood slice:
- Use static fixture feeds and generate a ranked digest.

Why it matters:
- Tests passive observation and preference learning.

Core risk: low if network access is optional.

### P-07: mew-ghost

Goal: A lightweight companion that appears beside the editor or terminal.

Scope:
- Detect active app/window title with opt-in OS APIs.
- Show a small visual presence.
- Click to open `mew chat` or `mew code`.

First dogfood slice:
- Static local window prototype that does not require accessibility APIs.

Why it matters:
- Strong feeling of presence with less privacy risk than screen capture.

Core risk: low to medium.

### P-08: mew-bond

Goal: Give each mew instance a durable personality and relationship memory.

Status:
- First isolated prototype exists under `experiments/mew-bond`.
- Dogfood task #77 added a self-memory markdown generator that extracts durable
  traits, recent self learnings, and active work-session continuity cues from
  local state JSON.
- Dogfood task #78 added conservative durable-trait inference from repeated
  self learnings.
- Latest validation: `uv run pytest -q experiments/mew-bond` passed with
  `9 passed`.

Scope:
- Store personality parameters and successful interaction examples.
- Provide `mew whois` style identity output.
- Let mew remember what kind of help the user responds to.

First dogfood slice:
- Add an isolated prototype memory file and renderer, then later consider core
  integration.

Why it matters:
- Directly supports the question: "Would an AI want to be inside mew?"
- Builds cross-task self-memory, which is currently a product gap.

Core risk: medium if integrated too early.

### P-09: mew-meet

Goal: Let two opted-in mew instances exchange shareable summaries.

Scope:
- Explicit friend pairing.
- Share only allowlisted summaries.
- Full transparency log of sent and received data.

First dogfood slice:
- Local file-based exchange between two fake mew instances.

Why it matters:
- Interesting social/passive direction, but security and privacy costs are high.

Core risk: high. Defer.

### P-10: mew-mood

Goal: Make mew's internal state visible as mood.

Status:
- First isolated prototype exists under `experiments/mew-mood`.
- Dogfood task #80 used work session #106 and `mew work --ai` planning to pick
  the smallest slice.
- The prototype generates one `.mew/mood/YYYY-MM-DD.md` file with `energy`,
  `worry`, and `joy` scores plus reason lines and compact signals.
- Latest validation: `uv run pytest -q experiments/mew-mood` passed with
  `6 passed`.

Scope:
- Track simple axes such as `energy`, `worry`, and `joy`.
- Update from task completion, verification failures, blocked work, and user
  replies.
- Render mood in text first, then feed desktop/visual projects later.

First dogfood slice:
- Compute mood from existing state and print a small report.

Why it matters:
- Helps humans understand passive state without reading logs.
- Useful input for `mew-desk` and `mew-journal`.

Core risk: low.

### Integration: mew-passive-bundle

Goal: Compose generated daily reports into one passive reentry artifact.

Status:
- First isolated prototype exists under `experiments/mew-passive-bundle`.
- Dogfood task #82 used work session #108 and `mew work --ai` planning to pick
  the smallest integration pass.
- The prototype scans an output root for journal, mood, morning paper, dream,
  and self-memory reports for one date, then writes
  `.mew/passive-bundle/YYYY-MM-DD.md`.
- Latest validation: `uv run pytest -q experiments/mew-passive-bundle` passed
  with `3 passed`.

Why it matters:
- It tests whether the side-project artifacts can become a single daily cockpit
  object before any core promotion.
- It makes missing passive artifacts visible.

Core risk: low.

## Real Dogfooding Protocol

For any side project:

1. Create a coding task:

   ```bash
   ./mew task add "Prototype <project-name>" --kind coding --ready
   ```

2. Enter the cockpit:

   ```bash
   ./mew code <task-id>
   ```

3. Let mew inspect this file and choose the first slice:

   ```text
   /continue Read SIDE_PROJECTS.md and pick the smallest isolated side project
   slice that proves passive-AI value without touching core.
   ```

4. Keep the implementation isolated unless mew discovers a specific core
   friction that blocks the dogfood.

5. End with a report that answers:

   - What did mew build?
   - What did mew learn about itself?
   - What cockpit, memory, recovery, or passive-loop friction appeared?
   - Would this make an AI more willing to live inside mew?

## Current Bias

The next side project should probably be a tiny `mew-desk` static prototype or
a core promotion decision for the passive bundle.

Reason: `mew-dream`, `mew-bond`, `mew-journal`, `mew-mood`, and
`mew-morning-paper` now cover memory, self-continuity, daily continuity, passive
state visibility, and offline research ranking in isolated form.
`mew-passive-bundle` now proves they can be composed into one reentry artifact.
The next question is whether to make that bundle a core command or start a
non-core visual shell that reads it.
