from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from typing import Any

from .config import STATE_DIR
from .timeutil import now_iso


MEMORY_SCOPES = ("private", "team")
MEMORY_TYPES = ("user", "feedback", "project", "reference", "unknown")
CODING_MEMORY_KINDS = (
    "reviewer-steering",
    "failure-shield",
    "file-pair",
    "task-template",
    "reasoning-trace",
)
FRONTMATTER_DELIMITER = "+++"
MAX_DESCRIPTION_CHARS = 240
VETO_LOG_FILENAME = "vetoes.jsonl"


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    scope: str
    memory_type: str
    memory_kind: str
    name: str
    description: str
    body: str
    created_at: str
    approved: bool = False
    why: str = ""
    how_to_apply: str = ""
    rationale: str = ""
    symptom: str = ""
    root_cause: str = ""
    fix: str = ""
    stop_rule: str = ""
    source_path: str = ""
    test_path: str = ""
    structural_evidence: str = ""
    focused_test_green: bool = False
    path: Path | None = None


class FileMemoryBackend:
    def __init__(self, base_dir: Path | str = ".") -> None:
        self.base_dir = Path(base_dir)
        self.root = self.base_dir / STATE_DIR / "memory"

    def write(
        self,
        body: str,
        *,
        scope: str = "private",
        memory_type: str = "project",
        memory_kind: str = "",
        name: str = "",
        description: str = "",
        created_at: str | None = None,
        approved: bool = False,
        why: str = "",
        how_to_apply: str = "",
        rationale: str = "",
        symptom: str = "",
        root_cause: str = "",
        fix: str = "",
        stop_rule: str = "",
        source_path: str = "",
        test_path: str = "",
        structural_evidence: str = "",
        focused_test_green: bool = False,
    ) -> MemoryEntry:
        scope = normalize_scope(scope)
        memory_type = normalize_memory_type(memory_type)
        memory_kind = normalize_memory_kind(memory_kind, memory_type=memory_type)
        body = str(body or "").strip()
        if not body:
            raise ValueError("memory body must not be empty")
        (
            approved,
            why,
            how_to_apply,
            rationale,
            symptom,
            root_cause,
            fix,
            stop_rule,
            source_path,
            test_path,
            structural_evidence,
            focused_test_green,
        ) = validate_write_gate(
            memory_type=memory_type,
            memory_kind=memory_kind,
            approved=approved,
            why=why,
            how_to_apply=how_to_apply,
            rationale=rationale,
            symptom=symptom,
            root_cause=root_cause,
            fix=fix,
            stop_rule=stop_rule,
            source_path=source_path,
            test_path=test_path,
            structural_evidence=structural_evidence,
            focused_test_green=focused_test_green,
        )
        created_at = created_at or now_iso()
        name = normalize_text(name) or first_line(body) or "Untitled memory"
        description = clip_description(description or first_line(body))
        directory = self.root / scope / memory_type
        directory.mkdir(parents=True, exist_ok=True)
        path = unique_memory_path(directory, created_at, name)
        memory_id = path.relative_to(self.root).with_suffix("").as_posix()
        entry = MemoryEntry(
            id=memory_id,
            scope=scope,
            memory_type=memory_type,
            memory_kind=memory_kind,
            name=name,
            description=description,
            body=body,
            created_at=created_at,
            approved=approved,
            why=why,
            how_to_apply=how_to_apply,
            rationale=rationale,
            symptom=symptom,
            root_cause=root_cause,
            fix=fix,
            stop_rule=stop_rule,
            source_path=source_path,
            test_path=test_path,
            structural_evidence=structural_evidence,
            focused_test_green=focused_test_green,
            path=path,
        )
        path.write_text(render_memory_entry(entry), encoding="utf-8")
        return entry

    def entries(self) -> list[MemoryEntry]:
        if not self.root.exists():
            return []
        entries: list[MemoryEntry] = []
        for path in sorted(self.root.glob("*/*/*.md")):
            if not path.is_file():
                continue
            entry = read_memory_entry(path, root=self.root)
            if entry:
                entries.append(entry)
        return entries

    def _veto_log_path(self) -> Path:
        return self.base_dir / STATE_DIR / "durable" / VETO_LOG_FILENAME

    def veto_log_entries(self) -> list[dict[str, str]]:
        path = self._veto_log_path()
        if not path.exists():
            return []
        entries: list[dict[str, str]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            entry_id = normalize_text(payload.get("entry_id"))
            reason = normalize_text(payload.get("reason"))
            created_at = normalize_text(payload.get("created_at"))
            if not entry_id or not reason:
                continue
            entries.append(
                {
                    "entry_id": entry_id,
                    "reason": reason,
                    "created_at": created_at,
                }
            )
        return entries

    def latest_vetoes(self) -> dict[str, dict[str, str]]:
        latest: dict[str, dict[str, str]] = {}
        for payload in self.veto_log_entries():
            latest[payload["entry_id"]] = payload
        return latest

    def veto(
        self,
        entry_id: str,
        *,
        reason: str,
    ) -> dict[str, str]:
        entry = self.get(entry_id, include_vetoed=True)
        if not entry:
            raise ValueError(f"typed memory not found: {entry_id}")
        reason = normalize_text(reason)
        if not reason:
            raise ValueError("veto reason must not be empty")
        payload = {
            "entry_id": entry.id,
            "reason": reason,
            "created_at": now_iso(),
        }
        path = self._veto_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload

    def filtered_entries(
        self,
        *,
        scope: str | None = None,
        memory_type: str | None = None,
        memory_kind: str | None = None,
        include_vetoed: bool = False,
    ) -> list[MemoryEntry]:
        scope = normalize_scope(scope) if scope else None
        memory_type = normalize_memory_type(memory_type) if memory_type else None
        memory_kind = normalize_memory_kind(memory_kind, memory_type=memory_type) if memory_kind else None
        vetoes = {} if include_vetoed else self.latest_vetoes()
        entries = []
        for entry in self.entries():
            if scope and entry.scope != scope:
                continue
            if memory_type and entry.memory_type != memory_type:
                continue
            if memory_kind and entry.memory_kind != memory_kind:
                continue
            if not include_vetoed and entry.id in vetoes:
                continue
            entries.append(entry)
        entries.sort(key=lambda item: ((item.created_at or ""), item.id), reverse=True)
        return entries

    def get(
        self,
        entry_id: str,
        *,
        scope: str | None = None,
        memory_type: str | None = None,
        memory_kind: str | None = None,
        include_vetoed: bool = False,
    ) -> MemoryEntry | None:
        wanted = normalize_text(entry_id)
        if not wanted:
            return None
        for entry in self.filtered_entries(
            scope=scope,
            memory_type=memory_type,
            memory_kind=memory_kind,
            include_vetoed=include_vetoed,
        ):
            if entry.id == wanted:
                return entry
        return None

    def recall(
        self,
        query: str,
        *,
        scope: str | None = None,
        memory_type: str | None = None,
        memory_kind: str | None = None,
        limit: int = 5,
    ) -> list[MemoryEntry]:
        limit = max(0, int(limit or 0))
        if limit <= 0:
            return []
        matches = []
        for entry in self.filtered_entries(scope=scope, memory_type=memory_type, memory_kind=memory_kind):
            if memory_entry_matches(entry, query):
                matches.append(entry)
        return matches[:limit]


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def normalize_scope(value: str | None) -> str:
    normalized = normalize_text(value).casefold()
    if normalized not in MEMORY_SCOPES:
        raise ValueError(f"memory scope must be one of: {', '.join(MEMORY_SCOPES)}")
    return normalized


def normalize_memory_type(value: str | None) -> str:
    normalized = normalize_text(value).casefold()
    if normalized not in MEMORY_TYPES:
        raise ValueError(f"memory type must be one of: {', '.join(MEMORY_TYPES)}")
    return normalized


def normalize_memory_kind(value: str | None, *, memory_type: str | None = None) -> str:
    normalized = normalize_text(value).casefold()
    if not normalized:
        return ""
    normalized_type = normalize_memory_type(memory_type) if memory_type else None
    if normalized_type and normalized_type != "project":
        raise ValueError("coding memory kinds require --type project")
    if normalized not in CODING_MEMORY_KINDS:
        raise ValueError(f"memory kind must be one of: {', '.join(CODING_MEMORY_KINDS)}")
    if normalized == "reasoning-trace":
        raise ValueError("reasoning-trace is schema-only until Phase 2")
    return normalized


def validate_write_gate(
    *,
    memory_type: str,
    memory_kind: str,
    approved: bool = False,
    why: str = "",
    how_to_apply: str = "",
    rationale: str = "",
    symptom: str = "",
    root_cause: str = "",
    fix: str = "",
    stop_rule: str = "",
    source_path: str = "",
    test_path: str = "",
    structural_evidence: str = "",
    focused_test_green: bool = False,
) -> tuple[bool, str, str, str, str, str, str, str, str, str, str, bool]:
    normalized_why = normalize_text(why)
    normalized_how = normalize_text(how_to_apply)
    normalized_rationale = normalize_text(rationale)
    normalized_symptom = normalize_text(symptom)
    normalized_root_cause = normalize_text(root_cause)
    normalized_fix = normalize_text(fix)
    normalized_stop_rule = normalize_text(stop_rule)
    normalized_source_path = normalize_text(source_path)
    normalized_test_path = normalize_text(test_path)
    normalized_structural_evidence = normalize_text(structural_evidence)
    if memory_type != "project" or not memory_kind:
        return (
            bool(approved),
            normalized_why,
            normalized_how,
            normalized_rationale,
            normalized_symptom,
            normalized_root_cause,
            normalized_fix,
            normalized_stop_rule,
            normalized_source_path,
            normalized_test_path,
            normalized_structural_evidence,
            bool(focused_test_green),
        )
    if memory_kind == "reviewer-steering":
        if not approved:
            raise ValueError("reviewer-steering writes require --approved")
        if not normalized_why:
            raise ValueError("reviewer-steering writes require --why")
        if not normalized_how:
            raise ValueError("reviewer-steering writes require --how-to-apply")
    if memory_kind == "failure-shield":
        if not approved:
            raise ValueError("failure-shield writes require --approved")
        if not normalized_symptom:
            raise ValueError("failure-shield writes require --symptom")
        if not normalized_root_cause:
            raise ValueError("failure-shield writes require --root-cause")
        if not normalized_fix:
            raise ValueError("failure-shield writes require --fix")
        if not normalized_stop_rule:
            raise ValueError("failure-shield writes require --stop-rule")
    if memory_kind == "task-template":
        if not approved:
            raise ValueError("task-template writes require --approved")
        if not normalized_rationale:
            raise ValueError("task-template writes require --rationale")
    if memory_kind == "file-pair":
        if not normalized_source_path:
            raise ValueError("file-pair writes require --source-path")
        if not normalized_test_path:
            raise ValueError("file-pair writes require --test-path")
        if not normalized_structural_evidence:
            raise ValueError("file-pair writes require --structural-evidence")
        if not focused_test_green:
            raise ValueError("file-pair writes require --focused-test-green")
    return (
        bool(approved),
        normalized_why,
        normalized_how,
        normalized_rationale,
        normalized_symptom,
        normalized_root_cause,
        normalized_fix,
        normalized_stop_rule,
        normalized_source_path,
        normalized_test_path,
        normalized_structural_evidence,
        bool(focused_test_green),
    )


def first_line(value: str) -> str:
    for line in str(value or "").splitlines():
        text = normalize_text(line)
        if text:
            return text
    return ""


def clip_description(value: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    text = normalize_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", normalize_text(value).casefold()).strip("-")
    return slug or "memory"


def timestamp_slug(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "", str(value or "")) or "memory"


def unique_memory_path(directory: Path, created_at: str, name: str) -> Path:
    stem = f"{timestamp_slug(created_at)}-{slugify(name)}"
    path = directory / f"{stem}.md"
    index = 2
    while path.exists():
        path = directory / f"{stem}-{index}.md"
        index += 1
    return path


def quote_frontmatter(value: str) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def parse_frontmatter_value(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return ""
        return str(parsed) if isinstance(parsed, str) else ""
    return value.strip()


def render_memory_entry(entry: MemoryEntry) -> str:
    fields = {
        "id": entry.id,
        "scope": entry.scope,
        "type": entry.memory_type,
        "kind": entry.memory_kind,
        "name": entry.name,
        "description": entry.description,
        "created_at": entry.created_at,
    }
    if entry.approved:
        fields["approved"] = "true"
    if entry.why:
        fields["why"] = entry.why
    if entry.how_to_apply:
        fields["how_to_apply"] = entry.how_to_apply
    if entry.rationale:
        fields["rationale"] = entry.rationale
    if entry.symptom:
        fields["symptom"] = entry.symptom
    if entry.root_cause:
        fields["root_cause"] = entry.root_cause
    if entry.fix:
        fields["fix"] = entry.fix
    if entry.stop_rule:
        fields["stop_rule"] = entry.stop_rule
    if entry.source_path:
        fields["source_path"] = entry.source_path
    if entry.test_path:
        fields["test_path"] = entry.test_path
    if entry.structural_evidence:
        fields["structural_evidence"] = entry.structural_evidence
    if entry.focused_test_green:
        fields["focused_test_green"] = "true"
    lines = [FRONTMATTER_DELIMITER]
    for key, value in fields.items():
        lines.append(f"{key} = {quote_frontmatter(value)}")
    lines.extend([FRONTMATTER_DELIMITER, "", entry.body.strip(), ""])
    return "\n".join(lines)


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}, text.strip()
    metadata: dict[str, str] = {}
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            end_index = index
            break
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            metadata[key] = parse_frontmatter_value(value)
    if end_index is None:
        return {}, text.strip()
    return metadata, "\n".join(lines[end_index + 1 :]).strip()


def read_memory_entry(path: Path, *, root: Path | None = None) -> MemoryEntry | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    metadata, body = split_frontmatter(text)
    try:
        scope = normalize_scope(metadata.get("scope") or path.parent.parent.name)
    except ValueError:
        scope = "private"
    try:
        memory_type = normalize_memory_type(metadata.get("type") or path.parent.name)
    except ValueError:
        memory_type = "unknown"
    try:
        memory_kind = normalize_memory_kind(metadata.get("kind"), memory_type=memory_type)
    except ValueError:
        memory_kind = ""
    name = normalize_text(metadata.get("name")) or path.stem
    description = clip_description(metadata.get("description") or first_line(body))
    created_at = normalize_text(metadata.get("created_at"))
    approved = normalize_text(metadata.get("approved")).casefold() in {"true", "yes", "1"}
    why = normalize_text(metadata.get("why"))
    how_to_apply = normalize_text(metadata.get("how_to_apply"))
    rationale = normalize_text(metadata.get("rationale"))
    symptom = normalize_text(metadata.get("symptom"))
    root_cause = normalize_text(metadata.get("root_cause"))
    fix = normalize_text(metadata.get("fix"))
    stop_rule = normalize_text(metadata.get("stop_rule"))
    source_path = normalize_text(metadata.get("source_path"))
    test_path = normalize_text(metadata.get("test_path"))
    structural_evidence = normalize_text(metadata.get("structural_evidence"))
    focused_test_green = normalize_text(metadata.get("focused_test_green")).casefold() in {"true", "yes", "1"}
    if root:
        memory_id = normalize_text(metadata.get("id")) or path.relative_to(root).with_suffix("").as_posix()
    else:
        memory_id = normalize_text(metadata.get("id")) or path.with_suffix("").as_posix()
    return MemoryEntry(
        id=memory_id,
        scope=scope,
        memory_type=memory_type,
        memory_kind=memory_kind,
        name=name,
        description=description,
        body=body,
        created_at=created_at,
        approved=approved,
        why=why,
        how_to_apply=how_to_apply,
        rationale=rationale,
        symptom=symptom,
        root_cause=root_cause,
        fix=fix,
        stop_rule=stop_rule,
        source_path=source_path,
        test_path=test_path,
        structural_evidence=structural_evidence,
        focused_test_green=focused_test_green,
        path=path,
    )


def memory_entry_matches(entry: MemoryEntry, query: str) -> bool:
    needle = normalize_text(query).casefold()
    if not needle:
        return False
    haystack = " ".join(
        [
            entry.name,
            entry.description,
            entry.body,
            entry.scope,
            entry.memory_type,
            entry.memory_kind,
            entry.why,
            entry.how_to_apply,
            entry.rationale,
            entry.symptom,
            entry.root_cause,
            entry.fix,
            entry.stop_rule,
            entry.source_path,
            entry.test_path,
            entry.structural_evidence,
            "true" if entry.focused_test_green else "",
        ]
    ).casefold()
    if needle in haystack:
        return True
    terms = [term for term in needle.split() if term]
    return bool(terms) and all(term in haystack for term in terms)


def entry_to_dict(entry: MemoryEntry, *, veto: dict[str, str] | None = None) -> dict[str, Any]:
    data = {
        "id": entry.id,
        "scope": entry.scope,
        "memory_scope": entry.scope,
        "type": entry.memory_type,
        "memory_type": entry.memory_type,
        "memory_kind": entry.memory_kind,
        "key": entry.name,
        "name": entry.name,
        "description": entry.description,
        "text": entry.body,
        "created_at": entry.created_at,
        "storage": "file",
        "vetoed": bool(veto),
        "approved": entry.approved,
        "why": entry.why,
        "how_to_apply": entry.how_to_apply,
        "rationale": entry.rationale,
        "symptom": entry.symptom,
        "root_cause": entry.root_cause,
        "fix": entry.fix,
        "stop_rule": entry.stop_rule,
        "source_path": entry.source_path,
        "test_path": entry.test_path,
        "structural_evidence": entry.structural_evidence,
        "focused_test_green": entry.focused_test_green,
    }
    if entry.path:
        data["path"] = str(entry.path)
    if veto:
        data["veto"] = dict(veto)
        data["veto_reason"] = veto.get("reason") or ""
        data["vetoed_at"] = veto.get("created_at") or ""
    return data
