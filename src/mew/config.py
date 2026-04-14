from pathlib import Path


STATE_VERSION = 7
STATE_DIR = Path(".mew")
STATE_FILE = STATE_DIR / "state.json"
ARCHIVE_DIR = STATE_DIR / "archive"
LOG_FILE = STATE_DIR / "runtime.md"
LOCK_FILE = STATE_DIR / "runtime.lock"
STATE_LOCK_FILE = STATE_DIR / "state.lock"
AGENT_RUN_DIR = STATE_DIR / "agent-runs"
GUIDANCE_FILE = STATE_DIR / "guidance.md"
POLICY_FILE = STATE_DIR / "policy.md"
SELF_FILE = STATE_DIR / "self.md"
DESIRES_FILE = STATE_DIR / "desires.md"
MAX_RECENT_EVENTS = 20
DEFAULT_INTERVAL_SECONDS = 300.0
DEFAULT_TASK_TIMEOUT_SECONDS = 120.0
DEFAULT_ATTACH_POLL_INTERVAL_SECONDS = 0.5
MAX_COMMAND_OUTPUT_CHARS = 4000
DEFAULT_CODEX_WEB_BASE_URL = "https://chatgpt.com/backend-api/codex"
DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_AUTH_PATHS = (Path("auth.json"), Path.home() / ".codex" / "auth.json")
