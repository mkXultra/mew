Output "docs/assets/demo_short.gif"

Set FontSize 16
Set Width 1280
Set Height 720
Set Shell "bash"
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms
Set PlaybackSpeed 1.0

# ---- Hidden setup: small memory/reentry workspace ----
Hide
Type "mkdir -p /tmp/mew-demo-short docs/assets"
Enter
Type "ln -sfn $(pwd -P) /tmp/mew"
Enter
Type "cd /tmp/mew-demo-short && rm -rf .mew"
Enter
Type "export UV_PROJECT_ENVIRONMENT=/tmp/mew-demo-short/.uv-project-env"
Enter
Type "export PS1='~ $ '"
Enter
Type "alias mew='UV_CACHE_DIR=/tmp/mew-demo-short/.uv-cache uv run --quiet --project /tmp/mew --locked mew'"
Enter
Type "mew task add --kind coding --ready --priority high 'Continue resident AI work' >/dev/null"
Enter
Type "mew memory --add 'Prefer concise output and concrete next actions.' --type feedback --scope private --name 'Concise output' >/dev/null"
Enter
Type "mew memory --add 'This workspace values recovery, auditability, and reproducible verification.' --type project --scope private --name 'resident AI proof' >/dev/null"
Enter
Type "clear"
Enter
Show

# ---- Scene 1: Active memory ----
Type "# mew keeps scoped memory ready for the next model turn."
Enter
Sleep 1800ms
Type "mew memory --active --task-id 1"
Enter
Sleep 6500ms

# ---- Scene 2: Reentry command ----
Type "clear"
Enter
Type "# The next session starts from state, not from a human rebrief."
Enter
Sleep 1800ms
Type "mew work 1 --start-session --allow-read . >/dev/null"
Enter
Type "mew work 1 --session --resume --allow-read ."
Enter
Sleep 6000ms

# ---- Outro ----
Type "clear"
Enter
Type "# mew - durable state for resident AI."
Enter
Sleep 1500ms
Type "# see README and the Application Evidence Index"
Enter
Sleep 2500ms
