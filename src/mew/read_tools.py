import os
from pathlib import Path
import subprocess
import fnmatch


DEFAULT_READ_MAX_CHARS = 50000
DEFAULT_SEARCH_MAX_MATCHES = 50
DEFAULT_GLOB_MAX_MATCHES = 100
SENSITIVE_GLOBS = (
    ".mew",
    "auth.json",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_ed25519",
)


def _is_relative_to(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def normalize_allowed_roots(allowed_roots):
    roots = []
    for root in allowed_roots or []:
        path = Path(root).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        try:
            roots.append(path.resolve(strict=True))
        except OSError:
            continue
    return roots


def is_sensitive_path(path):
    return any(
        fnmatch.fnmatch(part, pattern)
        for part in Path(path).parts
        for pattern in SENSITIVE_GLOBS
    )


def ensure_not_sensitive(path, verb="inspect"):
    if is_sensitive_path(path):
        raise ValueError(f"refusing to {verb} sensitive path: {path}")


def resolve_allowed_path(path, allowed_roots):
    roots = normalize_allowed_roots(allowed_roots)
    if not roots:
        raise ValueError("read-only inspection is disabled; pass --allow-read PATH")

    candidate = Path(path or ".").expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"path does not exist: {candidate}") from exc

    for root in roots:
        if resolved == root or _is_relative_to(resolved, root):
            return resolved
    allowed = ", ".join(str(root) for root in roots)
    raise ValueError(f"path is outside allowed read roots: {resolved}; allowed={allowed}")


def inspect_dir(path, allowed_roots, limit=50):
    limit = max(1, min(int(limit), 200))
    resolved = resolve_allowed_path(path, allowed_roots)
    ensure_not_sensitive(resolved)
    if not resolved.is_dir():
        raise ValueError(f"path is not a directory: {resolved}")

    entries = []
    for entry in sorted(resolved.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if len(entries) >= limit:
            break
        if is_sensitive_path(entry):
            continue
        try:
            stat = entry.stat()
            size = stat.st_size
        except OSError:
            size = None
        kind = "dir" if entry.is_dir() else "file"
        entries.append({"name": entry.name, "type": kind, "size": size})

    return {
        "path": str(resolved),
        "type": "directory",
        "entries": entries,
        "truncated": len(entries) >= limit,
    }


def read_file(path, allowed_roots, max_chars=DEFAULT_READ_MAX_CHARS):
    max_chars = max(1, min(int(max_chars), 50000))
    resolved = resolve_allowed_path(path, allowed_roots)
    ensure_not_sensitive(resolved)
    if not resolved.is_file():
        raise ValueError(f"path is not a file: {resolved}")

    byte_limit = max_chars * 4 + 1
    with resolved.open("rb") as handle:
        data = handle.read(byte_limit)
    text = data.decode("utf-8", errors="replace")
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    try:
        size = resolved.stat().st_size
    except OSError:
        size = len(data)

    return {
        "path": str(resolved),
        "type": "file",
        "size": size,
        "text": text,
        "truncated": truncated or size > len(data),
    }


def search_text(query, path, allowed_roots, max_matches=DEFAULT_SEARCH_MAX_MATCHES):
    max_matches = max(1, min(int(max_matches), 200))
    if not query or not str(query).strip():
        raise ValueError("search query is empty")

    resolved = resolve_allowed_path(path or ".", allowed_roots)
    ensure_not_sensitive(resolved, verb="search")
    command = [
        "rg",
        "--line-number",
        "--fixed-strings",
        "--no-heading",
        "--color",
        "never",
        "--glob",
        "!.mew",
        "--glob",
        "!.mew/**",
        "--glob",
        "!auth.json",
        "--glob",
        "!.env",
        "--glob",
        "!.env.*",
        "--glob",
        "!*.pem",
        "--glob",
        "!*.key",
        "--glob",
        "!id_rsa",
        "--glob",
        "!id_ed25519",
        str(query),
        str(resolved),
    ]
    env = os.environ.copy()
    env["LC_ALL"] = env.get("LC_ALL") or "C.UTF-8"
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            shell=False,
            timeout=15,
            env=env,
        )
    except FileNotFoundError as exc:
        raise ValueError("rg is required for search_text but was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("search timed out") from exc

    if result.returncode not in (0, 1):
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f"search failed: {detail}")

    matches = []
    for line in result.stdout.splitlines():
        if len(matches) >= max_matches:
            break
        matches.append(line)

    return {
        "path": str(resolved),
        "query": str(query),
        "matches": matches,
        "truncated": len(result.stdout.splitlines()) > max_matches,
    }


def glob_paths(pattern, path, allowed_roots, max_matches=DEFAULT_GLOB_MAX_MATCHES):
    max_matches = max(1, min(int(max_matches), 500))
    if not pattern or not str(pattern).strip():
        raise ValueError("glob pattern is empty")

    resolved = resolve_allowed_path(path or ".", allowed_roots)
    ensure_not_sensitive(resolved, verb="glob")
    if not resolved.is_dir():
        raise ValueError(f"path is not a directory: {resolved}")

    matches = []
    for candidate in sorted(resolved.rglob(str(pattern)), key=lambda item: str(item)):
        if is_sensitive_path(candidate):
            continue
        if len(matches) >= max_matches:
            break
        kind = "dir" if candidate.is_dir() else "file"
        matches.append({"path": str(candidate), "type": kind})

    truncated = False
    if len(matches) >= max_matches:
        matched_paths = {match["path"] for match in matches}
        for candidate in resolved.rglob(str(pattern)):
            if is_sensitive_path(candidate):
                continue
            if str(candidate) not in matched_paths:
                truncated = True
                break

    return {
        "path": str(resolved),
        "pattern": str(pattern),
        "matches": matches,
        "truncated": truncated,
    }


def summarize_read_result(action_type, result):
    if action_type == "inspect_dir":
        entries = result.get("entries", [])
        names = ", ".join(f"{entry['type']}:{entry['name']}" for entry in entries[:20])
        suffix = " (truncated)" if result.get("truncated") else ""
        return f"Inspected directory {result.get('path')}: {names}{suffix}"
    if action_type == "read_file":
        suffix = " (truncated)" if result.get("truncated") else ""
        return f"Read file {result.get('path')} size={result.get('size')} chars{suffix}\n{result.get('text') or ''}"
    if action_type == "search_text":
        suffix = " (truncated)" if result.get("truncated") else ""
        matches = "\n".join(result.get("matches", []))
        return f"Searched {result.get('path')} for {result.get('query')!r}{suffix}\n{matches}"
    if action_type == "glob":
        suffix = " (truncated)" if result.get("truncated") else ""
        matches = "\n".join(
            f"{match.get('type')}:{match.get('path')}" for match in result.get("matches", [])[:50]
        )
        return f"Globbed {result.get('path')} for {result.get('pattern')!r}{suffix}\n{matches}"
    return str(result)
