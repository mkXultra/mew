"""Side-project dogfood telemetry for implementation-lane calibration."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

DEFAULT_LEDGER_PATH = Path("proof-artifacts/side_project_dogfood_ledger.jsonl")
SCHEMA_VERSION = 1

CODEX_CLI_ROLES = frozenset(
    {
        "reviewer",
        "operator",
        "comparator",
        "verifier",
        "fallback",
        "implementer",
        "none",
    }
)

OUTCOMES = frozenset({"clean", "practical", "partial", "failed"})

REQUIRED_FIELDS = (
    "task_id",
    "session_id",
    "side_project",
    "branch_or_worktree",
    "task_summary",
    "task_kind",
    "codex_cli_used_as",
    "first_edit_latency",
    "read_turns_before_edit",
    "files_changed",
    "tests_run",
    "reviewer_rejections",
    "verifier_failures",
    "rescue_edits",
    "outcome",
    "failure_class",
    "repair_required",
    "proof_artifacts",
    "commit",
)


@dataclass(frozen=True)
class SideProjectDogfoodRow:
    line_number: int
    data: Mapping[str, Any]

    @property
    def row_ref(self) -> str:
        value = self.data.get("row_ref") or self.data.get("id")
        if value not in (None, ""):
            return str(value)
        return str(self.line_number)

    def field(self, name: str, default: Any = None) -> Any:
        return self.data.get(name, default)

    def text_field(self, name: str) -> str:
        value = self.field(name, "")
        if value is None:
            return ""
        return str(value)


def dogfood_record_template() -> dict[str, Any]:
    """Return the canonical v0 JSON payload shape for a side-project attempt."""

    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": 0,
        "session_id": 0,
        "side_project": "mew-companion-log",
        "branch_or_worktree": "../mew-side-companion",
        "task_summary": "Implement one bounded side-project slice.",
        "task_kind": "coding",
        "codex_cli_used_as": "operator",
        "first_edit_latency": None,
        "read_turns_before_edit": None,
        "files_changed": [],
        "tests_run": [],
        "reviewer_rejections": 0,
        "verifier_failures": 0,
        "rescue_edits": 0,
        "outcome": "partial",
        "failure_class": "none_observed",
        "repair_required": False,
        "proof_artifacts": [],
        "commit": "",
        "notes": "",
    }


def _coerce_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if number < 0:
        raise ValueError(f"{field} must be non-negative")
    return number


def _coerce_optional_number(value: Any, *, field: str) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number or null")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number or null") from exc
    if number < 0:
        raise ValueError(f"{field} must be non-negative")
    return round(number, 3)


def _coerce_string_list(value: Any, *, field: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return [str(item) for item in value if str(item).strip()]


def normalize_side_project_dogfood_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one side-project dogfood record."""

    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        raise ValueError("missing required side-project dogfood field(s): " + ", ".join(missing))

    codex_cli_used_as = str(record.get("codex_cli_used_as") or "").strip()
    if codex_cli_used_as not in CODEX_CLI_ROLES:
        allowed = ", ".join(sorted(CODEX_CLI_ROLES))
        raise ValueError(f"codex_cli_used_as must be one of: {allowed}")

    outcome = str(record.get("outcome") or "").strip()
    if outcome not in OUTCOMES:
        allowed = ", ".join(sorted(OUTCOMES))
        raise ValueError(f"outcome must be one of: {allowed}")

    normalized = dict(record)
    normalized["schema_version"] = _coerce_int(record.get("schema_version", SCHEMA_VERSION), field="schema_version")
    normalized["task_id"] = _coerce_int(record.get("task_id"), field="task_id")
    normalized["session_id"] = _coerce_int(record.get("session_id"), field="session_id")
    normalized["side_project"] = str(record.get("side_project") or "").strip()
    normalized["branch_or_worktree"] = str(record.get("branch_or_worktree") or "").strip()
    normalized["task_summary"] = str(record.get("task_summary") or "").strip()
    normalized["task_kind"] = str(record.get("task_kind") or "").strip()
    normalized["codex_cli_used_as"] = codex_cli_used_as
    normalized["first_edit_latency"] = _coerce_optional_number(
        record.get("first_edit_latency"),
        field="first_edit_latency",
    )
    normalized["read_turns_before_edit"] = _coerce_optional_number(
        record.get("read_turns_before_edit"),
        field="read_turns_before_edit",
    )
    normalized["files_changed"] = _coerce_string_list(record.get("files_changed"), field="files_changed")
    normalized["tests_run"] = _coerce_string_list(record.get("tests_run"), field="tests_run")
    normalized["reviewer_rejections"] = _coerce_int(record.get("reviewer_rejections"), field="reviewer_rejections")
    normalized["verifier_failures"] = _coerce_int(record.get("verifier_failures"), field="verifier_failures")
    normalized["rescue_edits"] = _coerce_int(record.get("rescue_edits"), field="rescue_edits")
    normalized["outcome"] = outcome
    normalized["failure_class"] = str(record.get("failure_class") or "").strip()
    normalized["repair_required"] = bool(record.get("repair_required"))
    normalized["proof_artifacts"] = _coerce_string_list(record.get("proof_artifacts"), field="proof_artifacts")
    normalized["commit"] = str(record.get("commit") or "").strip()
    normalized["notes"] = str(record.get("notes") or "").strip()

    for field in ("side_project", "branch_or_worktree", "task_summary", "task_kind", "failure_class"):
        if not normalized[field]:
            raise ValueError(f"{field} must not be empty")
    return normalized


def iter_side_project_dogfood_ledger(path: str | Path = DEFAULT_LEDGER_PATH) -> Iterator[SideProjectDogfoodRow]:
    ledger_path = Path(path)
    if not ledger_path.exists():
        return
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:  # pragma: no cover - exact msg from json
                raise ValueError(f"invalid JSON on {ledger_path}:{line_number}: {exc.msg}") from exc
            if not isinstance(payload, Mapping):
                raise ValueError(f"expected object on {ledger_path}:{line_number}")
            yield SideProjectDogfoodRow(
                line_number=line_number,
                data=normalize_side_project_dogfood_record(payload),
            )


def load_side_project_dogfood_ledger(path: str | Path = DEFAULT_LEDGER_PATH) -> list[SideProjectDogfoodRow]:
    return list(iter_side_project_dogfood_ledger(path))


def append_side_project_dogfood_record(
    record: Mapping[str, Any],
    *,
    path: str | Path = DEFAULT_LEDGER_PATH,
) -> SideProjectDogfoodRow:
    normalized = normalize_side_project_dogfood_record(record)
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    line_number = 1
    if ledger_path.exists():
        with ledger_path.open("r", encoding="utf-8") as handle:
            line_number = sum(1 for line in handle if line.strip()) + 1
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized, ensure_ascii=False, sort_keys=True) + "\n")
    return SideProjectDogfoodRow(line_number=line_number, data=normalized)


def _average(values: Iterable[float | int | None]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 3)


def summarize_side_project_dogfood(
    *,
    path: str | Path = DEFAULT_LEDGER_PATH,
    limit: int = 10,
) -> dict[str, Any]:
    rows = load_side_project_dogfood_ledger(path)
    recent = rows[-limit:]
    total = len(rows)
    clean_or_practical = sum(1 for row in rows if row.text_field("outcome") in {"clean", "practical"})
    failures = [row for row in rows if row.text_field("outcome") == "failed"]
    return {
        "kind": "side_project_dogfood",
        "schema_version": SCHEMA_VERSION,
        "ledger_path": str(Path(path)),
        "rows_total": total,
        "limit": limit,
        "gate": {
            "clean_or_practical": clean_or_practical,
            "success_rate": round(clean_or_practical / total, 3) if total else None,
            "failed": len(failures),
            "structural_repairs_required": sum(1 for row in rows if bool(row.field("repair_required"))),
            "rescue_edits_total": sum(_coerce_int(row.field("rescue_edits", 0), field="rescue_edits") for row in rows),
            "codex_product_code_rescue_edits": sum(
                _coerce_int(row.field("rescue_edits", 0), field="rescue_edits") for row in rows
            ),
        },
        "counts": {
            "side_project": dict(Counter(row.text_field("side_project") for row in rows)),
            "outcome": dict(Counter(row.text_field("outcome") for row in rows)),
            "failure_class": dict(Counter(row.text_field("failure_class") for row in rows)),
            "codex_cli_used_as": dict(Counter(row.text_field("codex_cli_used_as") for row in rows)),
        },
        "latency": {
            "first_edit_latency_avg": _average(row.field("first_edit_latency") for row in rows),
            "read_turns_before_edit_avg": _average(row.field("read_turns_before_edit") for row in rows),
        },
        "attempts": [
            {
                "row_ref": row.row_ref,
                "task_id": row.field("task_id"),
                "session_id": row.field("session_id"),
                "side_project": row.text_field("side_project"),
                "branch_or_worktree": row.text_field("branch_or_worktree"),
                "codex_cli_used_as": row.text_field("codex_cli_used_as"),
                "outcome": row.text_field("outcome"),
                "failure_class": row.text_field("failure_class"),
                "rescue_edits": row.field("rescue_edits"),
                "repair_required": bool(row.field("repair_required")),
                "commit": row.text_field("commit"),
            }
            for row in recent
        ],
    }


def format_side_project_dogfood_report(summary: Mapping[str, Any]) -> str:
    gate = summary.get("gate") or {}
    counts = summary.get("counts") or {}
    latency = summary.get("latency") or {}
    lines = [
        "Side-project dogfood telemetry",
        f"ledger: {summary.get('ledger_path')}",
        (
            "gate: "
            f"{gate.get('clean_or_practical')}/{summary.get('rows_total')} "
            f"clean_or_practical success_rate={gate.get('success_rate')} "
            f"failed={gate.get('failed')} rescue_edits_total={gate.get('rescue_edits_total')} "
            f"structural_repairs_required={gate.get('structural_repairs_required')}"
        ),
        (
            "field semantics: rescue_edits is a numeric Codex product-code rescue count; "
            "exclude operator steering, reviewer rejection, verifier follow-up, or generic repair"
        ),
        (
            "latency: "
            f"first_edit_avg={latency.get('first_edit_latency_avg')} "
            f"read_turns_before_edit_avg={latency.get('read_turns_before_edit_avg')}"
        ),
    ]
    for label in ("side_project", "outcome", "failure_class", "codex_cli_used_as"):
        values = counts.get(label) or {}
        if values:
            bits = [f"{key}={value}" for key, value in sorted(values.items())]
            lines.append(f"{label}: " + " ".join(bits))
    lines.append("attempts:")
    for attempt in summary.get("attempts") or []:
        lines.append(
            "- "
            f"#{attempt.get('task_id')} session=#{attempt.get('session_id')} "
            f"{attempt.get('side_project')} role={attempt.get('codex_cli_used_as')} "
            f"outcome={attempt.get('outcome')} failure={attempt.get('failure_class')} "
            f"rescue_edits={attempt.get('rescue_edits')} repair={attempt.get('repair_required')} "
            f"commit={attempt.get('commit') or '-'}"
        )
    return "\n".join(lines)
