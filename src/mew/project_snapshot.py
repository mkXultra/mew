from pathlib import Path

from .read_tools import inspect_dir, read_file


MAX_SNAPSHOT_ROOTS = 20
MAX_SNAPSHOT_FILES = 30
MAX_SNAPSHOT_SEARCHES = 10
MAX_SNAPSHOT_ENTRIES = 80
MAX_SNAPSHOT_TEXT = 500
MAX_SNAPSHOT_SCRIPTS = 20
MAX_SNAPSHOT_PACKAGE_TEXT = 200

PROJECT_TYPE_FILES = {
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "setup.py": "python",
    "package.json": "node",
    "pnpm-lock.yaml": "node",
    "package-lock.json": "node",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "jvm",
    "build.gradle": "jvm",
}

KEY_FILE_NAMES = {
    "README.md",
    "prd.md",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
}

KEY_DIR_NAMES = {
    "src",
    "tests",
    "docs",
    "scripts",
}
DEFAULT_REFRESH_FILES = (
    "README.md",
    "prd.md",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
)
DEFAULT_REFRESH_DIRS = ("src", "tests")


def _clip(text, limit=MAX_SNAPSHOT_TEXT):
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[:limit] + "\n... truncated ..."


def _ensure_snapshot(state):
    memory = state.setdefault("memory", {})
    deep = memory.setdefault("deep", {})
    snapshot = deep.setdefault("project_snapshot", {})
    snapshot.setdefault("updated_at", None)
    snapshot.setdefault("project_types", [])
    snapshot.setdefault("roots", [])
    snapshot.setdefault("files", [])
    snapshot.setdefault("searches", [])
    snapshot.setdefault("package", {})
    return snapshot


def _upsert_by_path(items, path, item, limit):
    path = str(path)
    remaining = [existing for existing in items if existing.get("path") != path]
    remaining.append(item)
    del remaining[:-limit]
    return remaining


def _merge_project_types(snapshot, project_types):
    existing = list(snapshot.get("project_types") or [])
    for project_type in project_types:
        if project_type and project_type not in existing:
            existing.append(project_type)
    snapshot["project_types"] = existing[-10:]


def _root_summary(entries):
    key_files = []
    key_dirs = []
    project_types = []
    compact_entries = []
    for entry in entries[:MAX_SNAPSHOT_ENTRIES]:
        name = entry.get("name") or ""
        entry_type = entry.get("type") or ""
        if not name:
            continue
        if entry_type == "file" and name in KEY_FILE_NAMES:
            key_files.append(name)
        if entry_type == "dir" and name in KEY_DIR_NAMES:
            key_dirs.append(name)
        project_type = PROJECT_TYPE_FILES.get(name)
        if project_type and project_type not in project_types:
            project_types.append(project_type)
        compact_entries.append(
            {
                "name": name,
                "type": entry_type,
                "size": entry.get("size"),
            }
        )
    return {
        "entries": compact_entries,
        "key_files": key_files,
        "key_dirs": key_dirs,
        "project_types": project_types,
    }


def _readme_summary(text):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    heading = ""
    for line in lines:
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            break
    if not heading and lines:
        heading = lines[0]
    return _clip(heading, 200)


def _strip_toml_string(value):
    stripped = value.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        return stripped[1:-1]
    if stripped.startswith("'") and stripped.endswith("'"):
        return stripped[1:-1]
    return stripped


def _bounded_package(package):
    if not isinstance(package, dict):
        return {}
    bounded = {}
    for key in ("name", "version", "description", "requires_python"):
        if package.get(key):
            bounded[key] = _clip(package.get(key), MAX_SNAPSHOT_PACKAGE_TEXT)
    scripts = package.get("scripts") or {}
    if isinstance(scripts, dict):
        bounded_scripts = {}
        for key, value in list(scripts.items())[:MAX_SNAPSHOT_SCRIPTS]:
            bounded_scripts[_clip(key, 80)] = _clip(value, MAX_SNAPSHOT_PACKAGE_TEXT)
        if bounded_scripts:
            bounded["scripts"] = bounded_scripts
    return bounded


def _parse_pyproject(text):
    package = {}
    scripts = {}
    section = ""
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.strip("[]")
            continue
        if "=" not in stripped:
            continue
        key, value = [part.strip() for part in stripped.split("=", 1)]
        if section == "project" and key in ("name", "version", "description", "requires-python"):
            package[key.replace("-", "_")] = _strip_toml_string(value)
        elif section == "project.scripts" and len(scripts) < MAX_SNAPSHOT_SCRIPTS:
            scripts[key] = _strip_toml_string(value)
    if scripts:
        package["scripts"] = scripts
    return _bounded_package(package)


def _python_file_summary(text):
    imports = []
    functions = []
    classes = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or line[:1].isspace():
            continue
        if stripped.startswith("import "):
            name = stripped[len("import ") :].split(",", 1)[0].strip().split(" ", 1)[0]
            if name and name not in imports:
                imports.append(name)
        elif stripped.startswith("from "):
            name = stripped[len("from ") :].split(" import ", 1)[0].strip()
            if name and name not in imports:
                imports.append(name)
        elif stripped.startswith("def "):
            name = stripped[len("def ") :].split("(", 1)[0].strip()
            if name and name not in functions:
                functions.append(name)
        elif stripped.startswith("class "):
            name = stripped[len("class ") :].split("(", 1)[0].split(":", 1)[0].strip()
            if name and name not in classes:
                classes.append(name)
    parts = []
    if imports:
        parts.append("imports=" + ", ".join(imports[:8]))
    if classes:
        parts.append("classes=" + ", ".join(classes[:8]))
    if functions:
        parts.append("functions=" + ", ".join(functions[:12]))
    return "; ".join(parts) or "python module"


def _file_summary(path, text):
    name = Path(path).name
    if name.lower().startswith("readme") or name == "prd.md":
        summary = _readme_summary(text)
        return {"kind": "readme", "summary": summary} if summary else {"kind": "readme"}
    if name == "pyproject.toml":
        package = _parse_pyproject(text)
        return {"kind": "pyproject", "package": package}
    if name.endswith(".py"):
        return {"kind": "python", "summary": _python_file_summary(text)}
    return {"kind": "file", "summary": _clip(text, 200)}


def update_project_snapshot_from_read_result(state, action_type, result, current_time):
    snapshot = _ensure_snapshot(state)
    snapshot["updated_at"] = current_time

    if action_type == "inspect_dir":
        path = result.get("path") or ""
        summary = _root_summary(result.get("entries") or [])
        item = {
            "path": path,
            "updated_at": current_time,
            "truncated": bool(result.get("truncated")),
            "entry_count": len(result.get("entries") or []),
            "key_files": summary["key_files"],
            "key_dirs": summary["key_dirs"],
            "entries": summary["entries"],
        }
        snapshot["roots"] = _upsert_by_path(snapshot.get("roots") or [], path, item, MAX_SNAPSHOT_ROOTS)
        _merge_project_types(snapshot, summary["project_types"])
        return snapshot

    if action_type == "read_file":
        path = result.get("path") or ""
        summary = _file_summary(path, result.get("text") or "")
        item = {
            "path": path,
            "updated_at": current_time,
            "size": result.get("size"),
            "truncated": bool(result.get("truncated")),
            **summary,
        }
        snapshot["files"] = _upsert_by_path(snapshot.get("files") or [], path, item, MAX_SNAPSHOT_FILES)
        if summary.get("kind") == "pyproject":
            package = summary.get("package") or {}
            snapshot["package"] = {**snapshot.get("package", {}), **package}
            _merge_project_types(snapshot, ["python"])
        return snapshot

    if action_type == "search_text":
        item = {
            "path": result.get("path") or "",
            "query": _clip(result.get("query"), 200),
            "updated_at": current_time,
            "match_count": len(result.get("matches") or []),
            "truncated": bool(result.get("truncated")),
        }
        searches = list(snapshot.get("searches") or [])
        searches.append(item)
        del searches[:-MAX_SNAPSHOT_SEARCHES]
        snapshot["searches"] = searches
        return snapshot

    return snapshot


def refresh_project_snapshot(
    state,
    path,
    allowed_read_roots,
    current_time,
    read_files=True,
    inspect_key_dirs=True,
):
    report = {
        "updated_at": current_time,
        "path": "",
        "inspected_dirs": [],
        "read_files": [],
        "errors": [],
    }
    root_result = inspect_dir(path or ".", allowed_read_roots, limit=200)
    report["path"] = root_result.get("path") or ""
    update_project_snapshot_from_read_result(state, "inspect_dir", root_result, current_time)
    report["inspected_dirs"].append(root_result.get("path"))

    root = Path(root_result.get("path") or ".")

    if read_files:
        for filename in DEFAULT_REFRESH_FILES:
            candidate = root / filename
            if not candidate.exists() or not candidate.is_file():
                continue
            try:
                file_result = read_file(str(candidate), allowed_read_roots, max_chars=12000)
            except ValueError as exc:
                report["errors"].append(str(exc))
                continue
            update_project_snapshot_from_read_result(state, "read_file", file_result, current_time)
            report["read_files"].append(file_result.get("path"))

    if inspect_key_dirs:
        for dirname in DEFAULT_REFRESH_DIRS:
            candidate = root / dirname
            if not candidate.exists() or not candidate.is_dir():
                continue
            try:
                dir_result = inspect_dir(str(candidate), allowed_read_roots, limit=80)
            except ValueError as exc:
                report["errors"].append(str(exc))
                continue
            update_project_snapshot_from_read_result(state, "inspect_dir", dir_result, current_time)
            report["inspected_dirs"].append(dir_result.get("path"))

    report["snapshot"] = snapshot_for_context(_ensure_snapshot(state))
    return report


def _file_for_context(file_item):
    item = {
        **file_item,
        "summary": _clip(file_item.get("summary"), 300),
    }
    if "package" in item:
        item["package"] = _bounded_package(item.get("package"))
    return item


def snapshot_for_context(snapshot):
    if not isinstance(snapshot, dict):
        return {}
    return {
        "updated_at": snapshot.get("updated_at"),
        "project_types": list(snapshot.get("project_types") or [])[-10:],
        "package": _bounded_package(snapshot.get("package")),
        "roots": [
            {
                **root,
                "entries": list(root.get("entries") or [])[:30],
            }
            for root in (snapshot.get("roots") or [])[-10:]
        ],
        "files": [_file_for_context(file_item) for file_item in (snapshot.get("files") or [])[-10:]],
        "searches": list(snapshot.get("searches") or [])[-5:],
    }


def format_project_snapshot(snapshot):
    if not isinstance(snapshot, dict) or not snapshot.get("updated_at"):
        return "project_snapshot: (empty)"
    lines = [
        f"project_snapshot_updated_at: {snapshot.get('updated_at')}",
        "project_types: " + (", ".join(snapshot.get("project_types") or []) or "(none)"),
    ]
    package = snapshot.get("package") or {}
    if package:
        package_parts = [f"{key}={value}" for key, value in package.items() if key != "scripts"]
        if package_parts:
            lines.append("package: " + ", ".join(package_parts))
        scripts = package.get("scripts") or {}
        if scripts:
            lines.append("scripts: " + ", ".join(sorted(scripts)))
    roots = snapshot.get("roots") or []
    if roots:
        lines.append("roots:")
        for root in roots[-5:]:
            lines.append(
                f"- {root.get('path')} entries={root.get('entry_count')} "
                f"key_dirs={root.get('key_dirs') or []} key_files={root.get('key_files') or []}"
            )
    files = snapshot.get("files") or []
    if files:
        lines.append("files:")
        for file_item in files[-5:]:
            details = file_item.get("summary") or file_item.get("kind") or ""
            lines.append(f"- {file_item.get('path')} {details}")
    return "\n".join(lines)


def format_snapshot_refresh_report(report):
    snapshot = report.get("snapshot") or {}
    lines = [
        f"snapshot_updated_at: {report.get('updated_at')}",
        f"path: {report.get('path')}",
        f"inspected_dirs: {len(report.get('inspected_dirs') or [])}",
        f"read_files: {len(report.get('read_files') or [])}",
    ]
    if report.get("errors"):
        lines.append("errors:")
        for error in report.get("errors") or []:
            lines.append(f"- {error}")
    lines.append("")
    lines.append(format_project_snapshot(snapshot))
    return "\n".join(lines)
