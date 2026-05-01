Output "/Users/mk/dev/personal-pj/mew_side_pj/docs/assets/demo_primary.gif"

Set FontSize 16
Set Width 1280
Set Height 720
Set Shell "bash"
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms
Set PlaybackSpeed 1.0

# ---- Hidden setup: fresh local workspace with one interrupted task ----
Hide
Type "mkdir -p /tmp/mew-demo-work/tests /Users/mk/dev/personal-pj/mew_side_pj/docs/assets"
Enter
Type "cd /tmp/mew-demo-work && rm -rf .mew add_numbers.py tests/test_add_numbers.py"
Enter
Type "export UV_PROJECT_ENVIRONMENT=/tmp/mew-demo-work/.uv-project-env"
Enter
Type "export PS1='~ $ '"
Enter
Type "alias mew='UV_CACHE_DIR=/tmp/mew-demo-work/.uv-cache uv run --quiet --project /Users/mk/dev/personal-pj/mew_side_pj --locked mew'"
Enter
Type "printf 'def add_numbers(a, b):\n    return abs(a) + abs(b)\n' > add_numbers.py"
Enter
Type "printf 'from add_numbers import add_numbers\n\n\ndef test_add_numbers_handles_negatives():\n    assert add_numbers(-2, -3) == -5\n' > tests/test_add_numbers.py"
Enter
Type "mew task add --kind coding --ready --priority high --description 'Fix add_numbers and preserve the failed verifier context across interruption.' --notes 'Interrupted after reading tests/test_add_numbers.py and seeing the failing verifier.' 'Fix add_numbers for negative inputs' >/dev/null"
Enter
Type "mew memory --add 'Prefer concise output and show the next recovery action first.' --type feedback --scope private --name 'Concise reentry' >/dev/null"
Enter
Type "mew memory --add 'This demo project uses pytest; tests live in tests/.' --type project --scope private --name 'pytest convention' >/dev/null"
Enter
Type "mew work 1 --start-session --allow-read . --allow-verify --verify-command 'python -m pytest -q' >/dev/null 2>&1"
Enter
Type "mew work 1 --tool read_file --path tests/test_add_numbers.py --allow-read . --json >/dev/null"
Enter
Type "mew work 1 --tool run_tests --command 'python -m pytest -q' --allow-verify --json >/dev/null 2>&1 || true"
Enter
Type "mew work 1 --session-note 'operator interrupted here: resume should preserve test target, failure context, and next action' >/dev/null"
Enter
Type "clear"
Enter
Show

# ---- Scene 1: Product framing ----
Type "# mew is a durable-state runtime for resident AI."
Enter
Sleep 1600ms
Type "# The point is not a fresh CLI turn. The point is resuming after interruption."
Enter
Sleep 2200ms
Type "clear"
Enter

# ---- Scene 2: Work session resume ----
Type "mew work 1 --session --resume --allow-read ."
Enter
Sleep 6500ms
Type "# Resume carries task state, working memory, active memory, verifier context, and next action."
Enter
Sleep 3000ms
Type "clear"
Enter

# ---- Scene 3: Audit trail ----
Type "# The trail is inspectable, not hidden inside a model transcript."
Enter
Sleep 1200ms
Type "mew work 1 --session --timeline"
Enter
Sleep 5000ms
Type "mew work 1 --session --tests"
Enter
Sleep 4500ms
Type "# A reviewer can inspect what mew read, what failed, and why the next turn knows it."
Enter
Sleep 3200ms
Type "clear"
Enter

# ---- Scene 4: Public benchmark evidence ----
Type "# The same discipline is used for public Terminal-Bench gap artifacts."
Enter
Sleep 1500ms
Type "cd /Users/mk/dev/personal-pj/mew_side_pj"
Enter
Type "sed -n '1,28p' docs/M6_24_GAP_BASELINE_2026-04-29.md"
Enter
Sleep 7000ms
Type "wc -l proof-artifacts/m6_24_gap_ledger.jsonl"
Enter
Sleep 1800ms
Type "jq -r '[.record_type,.gap_reason,.status]|@tsv' proof-artifacts/m6_24_gap_ledger.jsonl | head -5"
Enter
Sleep 4500ms
Type "jq -r '.evidence[]?' proof-artifacts/m6_24_gap_ledger.jsonl | grep '^proof-artifacts/terminal-bench' | head -3"
Enter
Sleep 5000ms

# ---- Outro ----
Type "clear"
Enter
Type "# mew: resident AI that remembers, recovers, and leaves evidence."
Enter
Sleep 1600ms
Type "# github.com/mkXultra/mew"
Enter
Sleep 2800ms
