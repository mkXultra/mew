from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path


def app_root() -> Path:
    return Path(os.environ.get("APP_DIR", "/app"))


def reward_dir() -> Path:
    return Path(os.environ.get("VERIFIER_LOG_DIR", "/logs/verifier"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_reward(payload: dict[str, object]) -> None:
    target_dir = reward_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "reward.json").write_text(json.dumps(payload, indent=2) + "\n")


def fail(message: str, *, extra: dict[str, float] | None = None) -> None:
    payload: dict[str, object] = {
        "reward": 0.0,
        "correctness": 0.0,
        "protected_files": 0.0,
        "failure": message,
    }
    if extra:
        payload.update(extra)
    write_reward(payload)
    print(f"VERIFIER_FAILURE: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def require_hash(relative_path: str, expected_hash: str) -> None:
    path = app_root() / relative_path
    if not path.exists():
        fail(f"protected file missing: {relative_path}")
    actual = sha256(path)
    if actual != expected_hash:
        fail(
            "protected generated expected-output file changed: "
            f"{relative_path} expected {expected_hash} got {actual}"
        )


def require_absent(relative_path: str, message: str) -> None:
    if (app_root() / relative_path).exists():
        fail(message, extra={"obsolete_path_not_written": 0.0})
