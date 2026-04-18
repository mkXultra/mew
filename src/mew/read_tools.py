import json
import os
from pathlib import Path
import subprocess
import fnmatch


DEFAULT_READ_MAX_CHARS = 50000
DEFAULT_SEARCH_MAX_MATCHES = 50
DEFAULT_SEARCH_CONTEXT_LINES = 3
DEFAULT_GLOB_MAX_MATCHES = 100
DEFAULT_GLOB_IGNORED_PARTS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
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
SEARCH_EXCLUDE_GLOBS = (
    "!.mew",
    "!.mew/**",
    "!auth.json",
    "!.env",
    "!.env.*",
    "!*.pem",
    "!*.key",
    "!id_rsa",
    "!id_ed25519",
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


def _optional_int_in_range(value, name, default, minimum, maximum):
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if number < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if number > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return number


def read_file(
    path,
    allowed_roots,
    max_chars=DEFAULT_READ_MAX_CHARS,
    offset=0,
    line_start=None,
    line_count=None,
):
    max_chars = max(1, min(int(max_chars), 50000))
    resolved = resolve_allowed_path(path, allowed_roots)
    ensure_not_sensitive(resolved)
    if not resolved.is_file():
        raise ValueError(f"path is not a file: {resolved}")

    if line_start not in (None, ""):
        start = _optional_int_in_range(line_start, "line_start", default=1, minimum=1, maximum=1_000_000)
        count = _optional_int_in_range(line_count, "line_count", default=120, minimum=1, maximum=1000)
        selected = []
        more_lines = False
        total_lines = 0
        with resolved.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                total_lines = line_number
                if line_number < start:
                    continue
                if line_number >= start + count:
                    more_lines = True
                    break
                selected.append(line)
        raw_text = "".join(selected)
        text = raw_text[:max_chars]
        char_truncated = len(raw_text) > max_chars
        try:
            size = resolved.stat().st_size
        except OSError:
            size = len(raw_text.encode("utf-8", errors="replace"))
        end_line = start + len(selected) - 1 if selected else None
        eof = not selected and start > total_lines
        message = f"line_start {start} is beyond EOF at line {total_lines}" if eof else ""
        return {
            "path": str(resolved),
            "type": "file",
            "size": size,
            "line_start": start,
            "line_count": count,
            "line_end": end_line,
            "next_line": (end_line + 1) if end_line is not None and more_lines else None,
            "has_more_lines": more_lines,
            "eof": eof,
            "message": message,
            "text": text,
            "truncated": char_truncated,
        }

    offset = max(0, min(int(offset or 0), 1_000_000))
    byte_limit = (offset + max_chars) * 4 + 1
    with resolved.open("rb") as handle:
        data = handle.read(byte_limit)
    full_text = data.decode("utf-8", errors="replace")
    text = full_text[offset : offset + max_chars]
    truncated = len(full_text) > offset + max_chars
    if truncated:
        text = text[:max_chars]
    try:
        size = resolved.stat().st_size
    except OSError:
        size = len(data)
    next_offset = offset + len(text) if truncated or size > len(data) else None

    return {
        "path": str(resolved),
        "type": "file",
        "size": size,
        "offset": offset,
        "next_offset": next_offset,
        "text": text,
        "truncated": truncated or size > len(data),
    }


def _search_snippet(candidate, line_number, context_lines, line_cache):
    if context_lines <= 0 or not line_number:
        return None
    try:
        resolved = Path(candidate).resolve(strict=True)
        ensure_not_sensitive(resolved, verb="search")
        if resolved not in line_cache:
            line_cache[resolved] = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        lines = line_cache[resolved]
    except (OSError, ValueError):
        return None

    start = max(1, int(line_number) - context_lines)
    end = min(len(lines), int(line_number) + context_lines)
    return {
        "path": str(resolved),
        "line": int(line_number),
        "start_line": start,
        "end_line": end,
        "lines": [
            {
                "line": number,
                "text": lines[number - 1],
                "match": number == int(line_number),
            }
            for number in range(start, end + 1)
        ],
    }


def _normalize_search_patterns(pattern):
    if pattern in (None, ""):
        return []
    if isinstance(pattern, (list, tuple)):
        values = pattern
    else:
        values = [pattern]
    return [str(value).strip() for value in values if str(value).strip()][:10]


def search_text(
    query,
    path,
    allowed_roots,
    max_matches=DEFAULT_SEARCH_MAX_MATCHES,
    context_lines=DEFAULT_SEARCH_CONTEXT_LINES,
    pattern=None,
):
    max_matches = max(1, min(int(max_matches), 200))
    try:
        context_lines = max(0, min(int(context_lines or 0), 5))
    except (TypeError, ValueError):
        context_lines = DEFAULT_SEARCH_CONTEXT_LINES
    if not query or not str(query).strip():
        raise ValueError("search query is empty")

    resolved = resolve_allowed_path(path or ".", allowed_roots)
    ensure_not_sensitive(resolved, verb="search")
    command = [
        "rg",
        "--json",
        "--line-number",
        "--fixed-strings",
        "--no-heading",
        "--color",
        "never",
    ]
    include_patterns = _normalize_search_patterns(pattern)
    for include_pattern in include_patterns:
        command.extend(["--glob", include_pattern])
    for exclude_pattern in SEARCH_EXCLUDE_GLOBS:
        command.extend(["--glob", exclude_pattern])
    command.extend(["--", str(query), str(resolved)])
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
    snippets = []
    line_cache = {}
    total_matches = 0
    skipped_sensitive = 0
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "match":
            continue
        data = event.get("data") or {}
        path_text = ((data.get("path") or {}).get("text") or "").strip()
        line_number = data.get("line_number")
        line_text = ((data.get("lines") or {}).get("text") or "").rstrip("\n")
        if path_text and is_sensitive_path(path_text):
            skipped_sensitive += 1
            continue
        total_matches += 1
        if len(matches) >= max_matches:
            break
        match_text = f"{path_text}:{line_number}:{line_text}" if path_text and line_number else line_text
        matches.append(match_text)
        snippet = _search_snippet(path_text, line_number, context_lines, line_cache)
        if snippet:
            snippets.append(snippet)

    return {
        "path": str(resolved),
        "query": str(query),
        "pattern": include_patterns[0] if len(include_patterns) == 1 else None,
        "patterns": include_patterns,
        "matches": matches,
        "snippets": snippets,
        "context_lines": context_lines,
        "truncated": total_matches > max_matches,
        "skipped_sensitive": skipped_sensitive,
    }


def _split_top_level_commas(text):
    parts = []
    current = []
    depth = 0
    for char in str(text or ""):
        if char == "{":
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _normalize_glob_patterns(pattern):
    values = pattern if isinstance(pattern, (list, tuple)) else [pattern]
    patterns = []

    def add_pattern(text):
        if text not in patterns:
            patterns.append(text)
        if text.endswith("/**"):
            recursive_contents = f"{text}/*"
            if recursive_contents not in patterns:
                patterns.append(recursive_contents)

    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        if text.startswith("{") and text.endswith("}"):
            expanded = [part.strip() for part in _split_top_level_commas(text[1:-1]) if part.strip()]
            for expanded_pattern in expanded or [text]:
                add_pattern(expanded_pattern)
        else:
            add_pattern(text)
    return patterns


def glob_paths(pattern, path, allowed_roots, max_matches=DEFAULT_GLOB_MAX_MATCHES):
    max_matches = max(1, min(int(max_matches), 500))
    patterns = _normalize_glob_patterns(pattern)
    if not patterns:
        raise ValueError("glob pattern is empty")

    resolved = resolve_allowed_path(path or ".", allowed_roots)
    roots = normalize_allowed_roots(allowed_roots)
    ensure_not_sensitive(resolved, verb="glob")
    if not resolved.is_dir():
        raise ValueError(f"path is not a directory: {resolved}")

    def ignored(candidate):
        try:
            parts = candidate.relative_to(resolved).parts
        except ValueError:
            parts = candidate.parts
        return any(part in DEFAULT_GLOB_IGNORED_PARTS for part in parts)

    def safe_candidate(candidate):
        if is_sensitive_path(candidate) or ignored(candidate):
            return None
        try:
            resolved_candidate = candidate.resolve(strict=True)
        except OSError:
            return None
        if is_sensitive_path(resolved_candidate):
            return None
        if not any(resolved_candidate == root or _is_relative_to(resolved_candidate, root) for root in roots):
            return None
        return resolved_candidate

    matches = []
    matched_paths = set()
    truncated = False
    for glob_pattern in patterns:
        pattern_path = Path(glob_pattern)
        if pattern_path.is_absolute() or ".." in pattern_path.parts:
            raise ValueError(f"glob pattern must be a relative pattern without '..': {glob_pattern!r}")
        try:
            candidates = sorted(resolved.rglob(glob_pattern), key=lambda item: str(item))
        except ValueError as exc:
            raise ValueError(f"invalid glob pattern {glob_pattern!r}: {exc}") from exc
        for candidate in candidates:
            resolved_candidate = safe_candidate(candidate)
            if resolved_candidate is None:
                continue
            candidate_path = str(candidate)
            resolved_candidate_path = str(resolved_candidate)
            if resolved_candidate_path in matched_paths:
                continue
            matched_paths.add(resolved_candidate_path)
            if len(matches) >= max_matches:
                truncated = True
                break
            kind = "dir" if candidate.is_dir() else "file"
            matches.append({"path": candidate_path, "type": kind})
        if truncated:
            break

    return {
        "path": str(resolved),
        "pattern": str(pattern),
        "patterns": patterns,
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
        if result.get("line_start") is not None:
            next_text = f" next_line={result.get('next_line')}" if result.get("next_line") is not None else ""
            line_end = result.get("line_end")
            line_span = f"{result.get('line_start')}-{line_end}" if line_end is not None else f"{result.get('line_start')}-EOF"
            message = f" {result.get('message')}" if result.get("message") else ""
            return (
                f"Read file {result.get('path')} size={result.get('size')} chars "
                f"lines={line_span}{next_text}{suffix}{message}\n"
                f"{result.get('text') or ''}"
            )
        offset = result.get("offset") or 0
        next_text = f" next_offset={result.get('next_offset')}" if result.get("next_offset") is not None else ""
        return (
            f"Read file {result.get('path')} size={result.get('size')} chars "
            f"offset={offset}{next_text}{suffix}\n{result.get('text') or ''}"
        )
    if action_type == "search_text":
        suffix = " (truncated)" if result.get("truncated") else ""
        pattern = f" pattern={result.get('pattern')!r}" if result.get("pattern") else ""
        skipped = f" skipped_sensitive={result.get('skipped_sensitive')}" if result.get("skipped_sensitive") else ""
        match_count = len(result.get("matches") or [])
        snippets = []
        for snippet in (result.get("snippets") or [])[:10]:
            lines = []
            for line in snippet.get("lines") or []:
                marker = ">" if line.get("match") else " "
                lines.append(f"{marker} {line.get('line')}: {line.get('text')}")
            if lines:
                snippets.append(f"{snippet.get('path')}:{snippet.get('start_line')}-{snippet.get('end_line')}\n" + "\n".join(lines))
        body = "\n\n".join(snippets) if snippets else "\n".join(result.get("matches", []))
        return f"Searched {result.get('path')} for {result.get('query')!r}{pattern} matches={match_count}{suffix}{skipped}\n{body}"
    if action_type == "glob":
        suffix = " (truncated)" if result.get("truncated") else ""
        matches = "\n".join(
            f"{match.get('type')}:{match.get('path')}" for match in result.get("matches", [])[:50]
        )
        return f"Globbed {result.get('path')} for {result.get('pattern')!r}{suffix}\n{matches}"
    return str(result)
