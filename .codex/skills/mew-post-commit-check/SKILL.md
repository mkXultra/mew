---
name: mew-post-commit-check
description: Decide what to do immediately after a git commit in the mew repo. Use when a commit just landed and you must choose whether to report to the user or continue working under a long-session output gate.
---

# Mew Post-Commit Check

After a commit, do only this:

1. Confirm state:
   - `git status --short`
   - `./mew context --load --json`
2. If a long-session output gate is active and its report condition has not fired, **do not send any user-visible message**. Save a checkpoint only if needed, then continue working.
3. Otherwise, report the commit hash, current worktree state, and the next concrete action.
