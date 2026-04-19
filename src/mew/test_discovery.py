import ast
from pathlib import Path
import re


TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{2,}")
COMMON_HINT_TOKENS = {
    "and",
    "are",
    "assert",
    "class",
    "def",
    "edit",
    "false",
    "file",
    "for",
    "from",
    "import",
    "mew",
    "new",
    "none",
    "old",
    "path",
    "return",
    "self",
    "src",
    "test",
    "tests",
    "the",
    "true",
    "value",
    "with",
    "write",
}


def normalize_work_path(path):
    return str(path or "").strip().replace("\\", "/").lstrip("./")


def convention_test_path_for_mew_source(path):
    normalized = normalize_work_path(path)
    marker = "src/mew/"
    if marker not in normalized or not normalized.endswith(".py"):
        return ""
    stem = Path(normalized.rsplit("/", 1)[-1]).stem
    if not stem or stem == "__init__":
        return ""
    return f"tests/test_{stem}.py"


def source_module_for_path(path):
    normalized = normalize_work_path(path)
    if not normalized.endswith(".py"):
        return ""
    if normalized.startswith("src/"):
        module_path = normalized[len("src/") :]
    elif "/src/" in normalized:
        module_path = normalized.rsplit("/src/", 1)[-1]
    else:
        return ""
    if module_path.endswith("/__init__.py"):
        module_path = module_path[: -len("/__init__.py")]
    else:
        module_path = module_path[:-3]
    parts = [part for part in module_path.split("/") if part]
    if not parts:
        return ""
    return ".".join(parts)


def _path_from_root(root, path):
    candidate = Path(str(path or ""))
    if candidate.is_absolute():
        return candidate
    return Path(root) / normalize_work_path(path)


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _source_symbols(source_file):
    text = _read_text(source_file)
    if not text:
        return set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            names.add(node.name)
    return names


def _hint_tokens(text):
    tokens = set()
    for token in TOKEN_RE.findall(str(text or "").lower()):
        if token in COMMON_HINT_TOKENS:
            continue
        tokens.add(token)
    return tokens


def _module_import_score(text, module, symbols):
    if not module:
        return 0, []
    module_re = re.escape(module)
    score = 0
    reasons = []
    if re.search(rf"\bfrom\s+{module_re}\b", text) or re.search(rf"\bimport\s+{module_re}\b", text):
        score += 50
        reasons.append(f"imports {module}")
    for match in re.finditer(rf"\bfrom\s+{module_re}\s+import\s+([^\n#]+)", text):
        imported = set(TOKEN_RE.findall(match.group(1)))
        matched = sorted(imported & symbols)
        if matched:
            score += min(25, 5 * len(matched))
            reasons.append("imports symbols " + ", ".join(matched[:4]))
            break
    return score, reasons


def discover_tests_for_source(source_path, *, root=None, hint_text="", limit=5):
    """Return existing tests that likely cover a source file.

    Discovery is intentionally conservative: it returns existing test files
    only. Callers can still use convention_test_path_for_mew_source as a
    create-new-test fallback when no existing coverage is found.
    """
    root_path = Path(root or ".")
    tests_root = root_path / "tests"
    if not tests_root.is_dir():
        return []

    module = source_module_for_path(source_path)
    source_file = _path_from_root(root_path, source_path)
    symbols = _source_symbols(source_file)
    tokens = _hint_tokens(" ".join([str(source_path or ""), str(hint_text or "")]))
    convention = convention_test_path_for_mew_source(source_path)

    candidates = []
    for test_file in sorted(tests_root.rglob("*.py")):
        try:
            rel_path = test_file.relative_to(root_path).as_posix()
        except ValueError:
            rel_path = test_file.as_posix()
        text = _read_text(test_file)
        text_lower = text.lower()
        score = 0
        reasons = []
        structural_match = False

        if convention and rel_path == convention:
            score += 100
            reasons.append("convention path exists")
            structural_match = True

        import_score, import_reasons = _module_import_score(text, module, symbols)
        score += import_score
        reasons.extend(import_reasons)
        if import_score:
            structural_match = True

        if structural_match and tokens:
            token_score = 0
            path_lower = rel_path.lower()
            for token in tokens:
                if token in path_lower:
                    token_score += 8
                elif token in text_lower:
                    token_score += 2
            if token_score:
                score += min(40, token_score)
                reasons.append("matches edit/task tokens")

        if structural_match and score > 0:
            candidates.append({"path": rel_path, "score": score, "reason": "; ".join(reasons)})

    candidates.sort(key=lambda item: (-item["score"], item["path"]))
    return candidates[:limit]


def discover_test_paths_for_source(source_path, *, root=None, hint_text="", limit=5):
    return [candidate["path"] for candidate in discover_tests_for_source(source_path, root=root, hint_text=hint_text, limit=limit)]
