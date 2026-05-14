"""Provider-visible affordance gates for implement_v2.

This module is intentionally policy-only. It defines the static contract that
fastcheck and provider-request inventory tests use before later phases change
prompt text, tool descriptions, or tool-output shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Mapping

AFFORDANCE_VISIBILITY_SCHEMA_VERSION = 1

CANONICAL_FORBIDDEN_PROVIDER_VISIBLE_FIELDS: tuple[str, ...] = (
    "next_action",
    "next_action_policy",
    "next_action_contract",
    "required_next",
    "required_next_kind",
    "required_next_action",
    "required_next_evidence_refs",
    "required_next_probe",
    "suggested_next_action",
    "recommended_next_action",
    "first_write_due",
    "first_write_due_entry_turn",
    "first_write_due_overrun",
    "first_write_grace_probe_calls",
    "first_write_probe_threshold",
    "first_write_turn_threshold",
    "max_additional_probe_turns",
    "prewrite_probe_plateau",
    "WorkFrame",
    "workframe",
    "workframe_projection",
    "prompt_visible_workframe",
    "persisted_lane_state",
    "lane_local_state",
    "active_work_todo",
    "hard_runtime_frontier",
    "frontier",
    "frontier_state",
    "frontier_state_update",
    "model_authored_frontier",
    "model_authored_proof",
    "model_authored_todo",
    "proof",
    "proof_state",
    "repair_history",
    "todo",
    "history_json",
    "tool_calls",
)

MODEL_AUTHORED_PROVIDER_VISIBLE_FIELDS: tuple[str, ...] = (
    "active_work_todo",
    "frontier",
    "frontier_state",
    "frontier_state_update",
    "hard_runtime_frontier",
    "model_authored_frontier",
    "model_authored_proof",
    "model_authored_todo",
    "proof",
    "proof_state",
    "repair_history",
    "todo",
)

GENERIC_TEXT_FORBIDDEN_FIELDS = frozenset({"proof", "todo", "frontier", "workframe"})
AFFORDANCE_VISIBILITY_CAPS_FIXTURE = "tests/fixtures/implement_v2_affordance_visibility_caps.json"

DEFAULT_AFFORDANCE_VISIBILITY_CAPS: dict[str, object] = {
    "schema_version": AFFORDANCE_VISIBILITY_SCHEMA_VERSION,
    "compact_sidecar_digest": {
        "target_bytes": 4096,
        "hard_red_bytes": 6144,
        "top_level_keys": 16,
        "latest_tool_cards": 6,
        "latest_evidence_refs": 12,
    },
    "compact_sidecar_digest_latest_tool_summary": {
        "target_chars": 160,
        "hard_red_chars": 240,
        "output_refs": 2,
        "evidence_refs": 2,
    },
    "provider_visible_tool_output_card": {
        "target_bytes": 4096,
        "hard_red_bytes": 6144,
        "status_line_chars": 240,
        "refs": 12,
    },
    "search_text_visible_card": {
        "target_bytes": 4096,
        "hard_red_bytes": 6144,
        "matches": 8,
        "excerpt_chars": 180,
    },
    "read_file_visible_card": {
        "target_bytes": 4096,
        "hard_red_bytes": 6144,
        "excerpt_lines": 160,
        "line_chars": 220,
    },
    "run_command_visible_card": {
        "target_bytes": 4096,
        "hard_red_bytes": 6144,
        "latest_failure_chars": 1200,
        "stdout_tail_chars": 1200,
        "stderr_tail_chars": 1200,
        "live_transcript_text_chars": 12000,
    },
    "mutation_visible_card": {
        "target_bytes": 2048,
        "hard_red_bytes": 4096,
        "changed_paths": 12,
        "hunk_diffstat_chars": 1000,
    },
}

_STRUCTURAL_FIELD_SET = frozenset(CANONICAL_FORBIDDEN_PROVIDER_VISIBLE_FIELDS)
_PLAIN_TEXT_FIELD_SET = frozenset(
    field for field in CANONICAL_FORBIDDEN_PROVIDER_VISIBLE_FIELDS if field not in GENERIC_TEXT_FORBIDDEN_FIELDS
)
_GENERIC_RENDERED_PATTERNS = {
    field: re.compile(
        rf'(?i)(["\']{re.escape(field)}["\']\s*:|\b{re.escape(field)}\s*[:=]|<\s*{re.escape(field)}\s*>|^#+\s*{re.escape(field)}\b)',
        re.MULTILINE,
    )
    for field in GENERIC_TEXT_FORBIDDEN_FIELDS
}


def load_affordance_visibility_caps_fixture(*, repo_root: object = ".") -> dict[str, object]:
    path = Path(repo_root) / AFFORDANCE_VISIBILITY_CAPS_FIXTURE
    return json.loads(path.read_text(encoding="utf-8"))


def caps_fixture_matches_default(value: Mapping[str, object]) -> bool:
    return _normalize_json(value) == _normalize_json(DEFAULT_AFFORDANCE_VISIBILITY_CAPS)


def json_size_bytes(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))


def scan_forbidden_provider_visible(value: object, *, surface: str = "provider_visible") -> list[dict[str, object]]:
    """Return canonical provider-visible field leaks in a JSON-like or text value.

    Structural keys fail exactly. Plain text fails for explicit steering field
    names; generic words such as "proof" fail only as rendered keys/headers so
    ordinary prose can still quote user code or errors without false positives.
    """

    violations: list[dict[str, object]] = []

    def visit(item: object, path: tuple[str, ...]) -> None:
        if isinstance(item, Mapping):
            for raw_key, raw_value in item.items():
                key = str(raw_key)
                next_path = (*path, key)
                if key in _STRUCTURAL_FIELD_SET:
                    violations.append(
                        {
                            "surface": surface,
                            "field": key,
                            "path": ".".join(next_path),
                            "kind": "field_key",
                        }
                    )
                visit(raw_value, next_path)
            return
        if isinstance(item, (list, tuple)):
            for index, raw_value in enumerate(item):
                visit(raw_value, (*path, str(index)))
            return
        if isinstance(item, str):
            for field in sorted(_PLAIN_TEXT_FIELD_SET, key=len, reverse=True):
                if field in item:
                    violations.append(
                        {
                            "surface": surface,
                            "field": field,
                            "path": ".".join(path),
                            "kind": "text_marker",
                        }
                    )
            for field, pattern in _GENERIC_RENDERED_PATTERNS.items():
                if pattern.search(item):
                    violations.append(
                        {
                            "surface": surface,
                            "field": field,
                            "path": ".".join(path),
                            "kind": "rendered_generic_marker",
                        }
                    )

    visit(value, ())
    return _dedupe_violations(violations)


def fields_from_forbidden_violations(violations: Iterable[Mapping[str, object]]) -> list[str]:
    return sorted({str(item.get("field") or "") for item in violations if str(item.get("field") or "")})


def _dedupe_violations(violations: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str, str, str]] = set()
    result: list[dict[str, object]] = []
    for violation in violations:
        key = (
            str(violation.get("surface") or ""),
            str(violation.get("field") or ""),
            str(violation.get("path") or ""),
            str(violation.get("kind") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(violation))
    return result


def _normalize_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
