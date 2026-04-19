# Fresh CLI References

This directory is for local-only symlinks to mature AI CLI implementations.
Use these references when borrowing interaction, recovery, session, or command
surface ideas for mew.

The symlinks are intentionally ignored by git because they point to machine-local
checkout paths:

- `claude-code` -> `/Users/mk/dev/tech_check/claude-code`
- `codex` -> `/Users/mk/dev/tech_check/codex`

Do not vendor code from these projects into mew. Prefer extracting product and
architecture lessons, then implement mew-native behavior in `src/`.
