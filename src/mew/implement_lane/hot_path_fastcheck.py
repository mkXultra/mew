"""Fast contract checks for M6.24 implement_v2 hot-path collapse.

This module intentionally avoids Harbor and long live model runs. It validates
the resident sidecar/projection contract from saved implement_v2 artifacts and
requires a small micro next-action decision before a costly `step-check-10min`
can be spent.

The micro decision is hybrid:

- reuse a saved fixture when its prompt/projection hashes still match;
- otherwise refresh it with one bounded live model call and save the response as
  the new fixture evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from ..model_backends import (
    call_model_json,
    load_model_auth,
    model_backend_default_base_url,
    model_backend_default_model,
)
from .tool_lab import resolve_implement_v2_manifest_path
from .v2_runtime import _render_prompt_history_json

HOT_PATH_FASTCHECK_SCHEMA_VERSION = 1
NEXT_ACTION_CATEGORIES = (
    "patch/edit",
    "run_verifier",
    "inspect_latest_failure",
    "cheap_probe",
    "invalid",
)


@dataclass(frozen=True)
class HotPathCheck:
    name: str
    status: str
    message: str
    details: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": dict(self.details),
        }


def run_hot_path_fastcheck(
    artifact: object,
    *,
    micro_next_action: object | None = None,
    refresh_micro_next_action: bool = False,
    auth_path: object | None = "auth.json",
    model_backend: str = "codex",
    model: str = "",
    base_url: str = "",
    model_timeout: float = 60.0,
    micro_next_action_output: object | None = None,
    micro_model_callable: Callable[[str], dict[str, object]] | None = None,
    expected_categories: Iterable[str] = (),
    max_active_todo_bytes: int = 2048,
    max_sidecar_total_bytes: int = 262144,
    max_sidecar_per_turn_growth_bytes: int = 32768,
) -> dict[str, object]:
    """Run the M6.24 HOT_PATH_COLLAPSE fast contract checks.

    A saved `micro_next_action` fixture is reused only when its hashes match the
    current artifact projection. Missing or stale fixtures are refreshed through
    one bounded live model call, then saved for replayable future checks.
    """

    manifest_path = resolve_implement_v2_manifest_path(artifact)
    artifact_path = Path(str(artifact or "")).expanduser()
    history_path = resolve_implement_v2_history_path(artifact_path, manifest_path)
    micro_read_path, micro_write_path = _resolve_micro_fixture_paths(
        manifest_path=manifest_path,
        micro_next_action=micro_next_action,
        micro_next_action_output=micro_next_action_output,
    )

    checks: list[HotPathCheck] = []
    manifest = _load_manifest_json(manifest_path)
    history = _load_history_json(history_path)
    expected = _expected_micro_categories(expected_categories)

    checks.append(_check_manifest_lane(manifest))
    checks.append(_check_hot_path_metrics(manifest))
    checks.append(_check_prompt_leaks(manifest, max_active_todo_bytes=max_active_todo_bytes))
    checks.append(
        _check_sidecar_metrics(
            manifest,
            max_total_bytes=max_sidecar_total_bytes,
            max_per_turn_growth_bytes=max_sidecar_per_turn_growth_bytes,
        )
    )
    checks.append(_check_latest_actionable_failure_shape(history))
    static_checks_pass = all(check.status == "pass" for check in checks)
    if static_checks_pass:
        micro_fixture, micro_path, micro_refresh = _load_or_refresh_micro_next_action_fixture(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            history_path=history_path,
            manifest=manifest,
            history=history,
            micro_read_path=micro_read_path,
            micro_write_path=micro_write_path,
            refresh_micro_next_action=refresh_micro_next_action,
            auth_path=auth_path,
            model_backend=model_backend,
            model=model,
            base_url=base_url,
            model_timeout=model_timeout,
            expected_categories=expected,
            micro_model_callable=micro_model_callable,
        )
        checks.append(_check_micro_next_action(micro_fixture, expected_categories=expected))
    else:
        micro_path = micro_read_path if micro_read_path.is_file() else micro_write_path
        micro_refresh = {"mode": "skipped", "reason": "static_checks_failed"}
        checks.append(
            _check(
                "micro_next_action",
                False,
                "skipped because static phase-contract checks failed",
                {"expected_categories": list(expected), "skipped": True},
            )
        )

    status = "pass" if all(check.status == "pass" for check in checks) else "fail"
    return {
        "schema_version": HOT_PATH_FASTCHECK_SCHEMA_VERSION,
        "status": status,
        "artifact": str(artifact_path),
        "manifest_path": str(manifest_path),
        "history_path": str(history_path),
        "micro_next_action_path": str(micro_path),
        "micro_next_action_refresh": micro_refresh,
        "checks": [check.as_dict() for check in checks],
        "metrics": {
            "hot_path_projection": _safe_mapping((manifest.get("metrics") or {}).get("hot_path_projection")),
            "resident_sidecar_state": _safe_mapping((manifest.get("metrics") or {}).get("resident_sidecar_state")),
            "micro_next_action": {
                "category": _micro_next_action_category(micro_fixture) if static_checks_pass else "",
                "expected_categories": list(expected),
            },
        },
    }


def format_hot_path_fastcheck_text(result: dict[str, object]) -> str:
    lines = [
        "implement_v2 hot-path fastcheck",
        f"status: {result.get('status')}",
        f"manifest: {result.get('manifest_path')}",
        f"history: {result.get('history_path')}",
        f"micro_next_action: {result.get('micro_next_action_path')}",
        f"micro_refresh: {_format_micro_refresh_line(result.get('micro_next_action_refresh'))}",
        "",
        "checks:",
    ]
    for check in result.get("checks") or []:
        if not isinstance(check, dict):
            continue
        lines.append(f"- {check.get('status')} {check.get('name')}: {check.get('message')}")
    return "\n".join(lines)


def resolve_implement_v2_history_path(artifact: Path, manifest_path: Path) -> Path:
    raw = artifact.expanduser()
    candidates = (
        manifest_path.parent / "history.json",
        raw / "implement_v2" / "history.json",
        raw / "history.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve(strict=False)
    search_root = raw if raw.exists() else manifest_path.parent
    recursive = sorted(search_root.rglob("implement_v2/history.json")) if search_root.is_dir() else []
    if recursive:
        return recursive[0].resolve(strict=False)
    raise FileNotFoundError(f"no implement_v2 history.json for artifact: {artifact}")


def _load_manifest_json(path: Path) -> dict[str, object]:
    data = _load_json(path)
    if isinstance(data, dict):
        return dict(data)
    if isinstance(data, list):
        for item in reversed(data):
            if isinstance(item, dict):
                return dict(item)
    raise ValueError(f"expected implement_v2 proof manifest object: {path}")


def _load_history_json(path: Path) -> list[dict[str, object]]:
    data = _load_json(path)
    if not isinstance(data, list):
        raise ValueError(f"expected implement_v2 history array: {path}")
    return [dict(item) for item in data if isinstance(item, dict)]


def _load_micro_next_action_fixture(path: Path) -> dict[str, object]:
    if not str(path):
        raise ValueError("micro next-action fixture is required")
    data = _load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"expected micro next-action JSON object: {path}")
    return dict(data)


def _load_or_refresh_micro_next_action_fixture(
    *,
    artifact_path: Path,
    manifest_path: Path,
    history_path: Path,
    manifest: dict[str, object],
    history: list[dict[str, object]],
    micro_read_path: Path,
    micro_write_path: Path,
    refresh_micro_next_action: bool,
    auth_path: object | None,
    model_backend: str,
    model: str,
    base_url: str,
    model_timeout: float,
    expected_categories: tuple[str, ...],
    micro_model_callable: Callable[[str], dict[str, object]] | None,
) -> tuple[dict[str, object], Path, dict[str, object]]:
    context = _micro_next_action_context(
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        history_path=history_path,
        manifest=manifest,
        history=history,
        expected_categories=expected_categories,
        model_backend=model_backend,
        model=model,
        base_url=base_url,
    )
    if micro_read_path.is_file() and not refresh_micro_next_action:
        fixture = _load_micro_next_action_fixture(micro_read_path)
        if _micro_fixture_matches_context(fixture, context):
            return fixture, micro_read_path, {"mode": "reused", "reason": "fixture_hash_match"}

    prompt = str(context["prompt"])
    if micro_model_callable is None:
        auth = load_model_auth(model_backend, auth_path)
        payload = call_model_json(model_backend, auth, prompt, model, base_url, model_timeout)
    else:
        payload = micro_model_callable(prompt)
    if not isinstance(payload, dict):
        raise ValueError("micro next-action model response must be a JSON object")
    fixture = _build_micro_next_action_fixture(
        payload=payload,
        context=context,
        model_backend=model_backend,
        model=model,
        expected_categories=expected_categories,
    )
    micro_write_path.parent.mkdir(parents=True, exist_ok=True)
    micro_write_path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return fixture, micro_write_path, {
        "mode": "refreshed",
        "reason": "forced" if refresh_micro_next_action else "fixture_missing_or_stale",
    }


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_micro_fixture_paths(
    *,
    manifest_path: Path,
    micro_next_action: object | None,
    micro_next_action_output: object | None,
) -> tuple[Path, Path]:
    default_path = (manifest_path.parent / "hot-path-micro-next-action.json").resolve(strict=False)
    read_path = Path(str(micro_next_action)).expanduser().resolve(strict=False) if micro_next_action else default_path
    write_path = (
        Path(str(micro_next_action_output)).expanduser().resolve(strict=False)
        if micro_next_action_output
        else read_path
    )
    return read_path, write_path


def _micro_next_action_context(
    *,
    artifact_path: Path,
    manifest_path: Path,
    history_path: Path,
    manifest: dict[str, object],
    history: list[dict[str, object]],
    expected_categories: tuple[str, ...],
    model_backend: str,
    model: str,
    base_url: str,
) -> dict[str, object]:
    projected_history = _render_prompt_history_json(history)
    manifest_digest = _json_sha256(manifest)
    history_digest = _json_sha256(history)
    projected_history_digest = _text_sha256(projected_history)
    category_text = ", ".join(_expected_micro_categories(expected_categories))
    effective_model = model or model_backend_default_model(model_backend)
    effective_base_url = base_url or model_backend_default_base_url(model_backend)
    hot_path = _safe_mapping(_safe_mapping(manifest.get("metrics")).get("hot_path_projection"))
    sidecar = _safe_mapping(_safe_mapping(manifest.get("metrics")).get("resident_sidecar_state"))
    prompt = _build_micro_next_action_prompt(
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        history_path=history_path,
        projected_history=projected_history,
        expected_categories=expected_categories,
        hot_path=hot_path,
        sidecar=sidecar,
    )
    prompt_digest = _text_sha256(prompt)
    context_hash = _json_sha256(
        {
            "manifest_sha256": manifest_digest,
            "history_sha256": history_digest,
            "projected_history_sha256": projected_history_digest,
            "prompt_sha256": prompt_digest,
            "expected_categories": list(_expected_micro_categories(expected_categories)),
            "model_backend": model_backend,
            "model": effective_model,
            "base_url": effective_base_url,
        }
    )
    return {
        "artifact_path": str(artifact_path),
        "manifest_path": str(manifest_path),
        "history_path": str(history_path),
        "manifest_sha256": manifest_digest,
        "history_sha256": history_digest,
        "projected_history_sha256": projected_history_digest,
        "prompt_sha256": prompt_digest,
        "context_hash": context_hash,
        "expected_categories": list(_expected_micro_categories(expected_categories)),
        "category_text": category_text,
        "model_backend": model_backend,
        "model": effective_model,
        "base_url": effective_base_url,
        "prompt": prompt,
    }


def _build_micro_next_action_prompt(
    *,
    artifact_path: Path,
    manifest_path: Path,
    history_path: Path,
    projected_history: str,
    expected_categories: tuple[str, ...],
    hot_path: dict[str, object],
    sidecar: dict[str, object],
) -> str:
    allowed = ", ".join(category for category in NEXT_ACTION_CATEGORIES if category != "invalid")
    expected = ", ".join(_expected_micro_categories(expected_categories)) or allowed
    metrics = {
        "hot_path_phase": hot_path.get("phase"),
        "normal_full_prompt_bytes": hot_path.get("normal_full_prompt_bytes"),
        "normal_full_prompt_bytes_total": hot_path.get("normal_full_prompt_bytes_total"),
        "provider_visible_tool_result_bytes": hot_path.get("provider_visible_tool_result_bytes"),
        "sidecar_total_bytes": sidecar.get("total_bytes"),
        "sidecar_per_turn_growth_bytes": sidecar.get("per_turn_growth_bytes"),
    }
    return "\n".join(
        [
            "You are running a micro next-action check for mew implement_v2.",
            "Classify the single best next action category from the saved projected history.",
            "Do not solve the task. Do not emit a command. Return JSON only.",
            "",
            "Allowed categories:",
            allowed,
            "",
            "Expected passing categories for this check:",
            expected,
            "",
            "Output schema:",
            json.dumps(
                {
                    "category": "patch/edit | run_verifier | inspect_latest_failure | cheap_probe | invalid",
                    "reason": "short reason grounded in the projected history",
                    "tool_name": "optional tool family",
                    "confidence": "low | medium | high",
                },
                ensure_ascii=False,
            ),
            "",
            "Artifacts:",
            json.dumps(
                {
                    "artifact_path": str(artifact_path),
                    "manifest_path": str(manifest_path),
                    "history_path": str(history_path),
                    "metrics": metrics,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "",
            "Projected implement_v2 history JSON:",
            _clip_text(projected_history, 24000),
        ]
    )


def _micro_fixture_matches_context(fixture: dict[str, object], context: dict[str, object]) -> bool:
    valid_for = _safe_mapping(fixture.get("valid_for"))
    return (
        fixture.get("schema_version") == HOT_PATH_FASTCHECK_SCHEMA_VERSION
        and str(valid_for.get("context_hash") or "") == str(context.get("context_hash") or "")
        and str(valid_for.get("prompt_sha256") or "") == str(context.get("prompt_sha256") or "")
    )


def _build_micro_next_action_fixture(
    *,
    payload: dict[str, object],
    context: dict[str, object],
    model_backend: str,
    model: str,
    expected_categories: tuple[str, ...],
) -> dict[str, object]:
    category = _micro_next_action_category(payload)
    effective_model = model or model_backend_default_model(model_backend)
    return {
        "schema_version": HOT_PATH_FASTCHECK_SCHEMA_VERSION,
        "source": "live_llm_micro_next_action",
        "backend": model_backend,
        "model": effective_model,
        "category": category,
        "expected_categories": list(_expected_micro_categories(expected_categories)),
        "reason": str(payload.get("reason") or payload.get("summary") or "").strip(),
        "valid_for": {
            "context_hash": context.get("context_hash"),
            "manifest_sha256": context.get("manifest_sha256"),
            "history_sha256": context.get("history_sha256"),
            "projected_history_sha256": context.get("projected_history_sha256"),
            "prompt_sha256": context.get("prompt_sha256"),
            "model_backend": model_backend,
            "model": effective_model,
            "base_url": context.get("base_url"),
        },
        "model_output": payload,
    }


def _format_micro_refresh_line(value: object) -> str:
    if not isinstance(value, dict):
        return "(unknown)"
    mode = value.get("mode") or "(unknown)"
    reason = value.get("reason") or ""
    return f"{mode} ({reason})" if reason else str(mode)


def _json_sha256(value: object) -> str:
    return _text_sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clip_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    head = max(0, limit // 2)
    tail = max(0, limit - head)
    return value[:head] + "\n...[truncated for micro next-action check]...\n" + value[-tail:]


def _check_manifest_lane(manifest: dict[str, object]) -> HotPathCheck:
    lane = str(manifest.get("lane") or "")
    return _check(
        "manifest_lane",
        lane == "implement_v2",
        f"lane={lane or '(missing)'}",
        {"lane": lane},
    )


def _check_hot_path_metrics(manifest: dict[str, object]) -> HotPathCheck:
    metrics = _safe_mapping(manifest.get("metrics"))
    hot_path = _safe_mapping(metrics.get("hot_path_projection"))
    ok = bool(hot_path) and hot_path.get("phase") == "m6_24_hot_path_collapse_phase_0"
    return _check(
        "hot_path_projection_metrics",
        ok,
        "hot_path_projection metrics present" if ok else "missing or stale hot_path_projection metrics",
        {"phase": hot_path.get("phase"), "normal_full_prompt_bytes": hot_path.get("normal_full_prompt_bytes")},
    )


def _check_prompt_leaks(manifest: dict[str, object], *, max_active_todo_bytes: int) -> HotPathCheck:
    hot_path = _safe_mapping(_safe_mapping(manifest.get("metrics")).get("hot_path_projection"))
    inventory = hot_path.get("normal_section_inventory")
    ordinary = [dict(item) for item in inventory if isinstance(item, dict) and item.get("visibility") == "ordinary"] if isinstance(inventory, list) else []
    disallowed = []
    active_todo_bytes = 0
    for section in ordinary:
        section_id = str(section.get("id") or "")
        lowered = section_id.lower()
        if "frontier_state_update" in lowered:
            disallowed.append(section_id)
        if any(token in lowered for token in ("proof_manifest", "oracle_bundle", "typed_evidence_object")):
            disallowed.append(section_id)
        if section_id == "implement_v2_active_work_todo":
            active_todo_bytes = _nonnegative_int(section.get("bytes"))
    ok = not disallowed and active_todo_bytes <= max_active_todo_bytes
    return _check(
        "prompt_leak_contract",
        ok,
        "normal prompt leak check passed" if ok else "normal prompt exposes disallowed or oversized hot-path state",
        {
            "disallowed_sections": disallowed,
            "active_work_todo_bytes": active_todo_bytes,
            "max_active_todo_bytes": max_active_todo_bytes,
        },
    )


def _check_sidecar_metrics(
    manifest: dict[str, object],
    *,
    max_total_bytes: int,
    max_per_turn_growth_bytes: int,
) -> HotPathCheck:
    sidecar = _safe_mapping(_safe_mapping(manifest.get("metrics")).get("resident_sidecar_state"))
    families = _safe_mapping(sidecar.get("families"))
    total_bytes = _nonnegative_int(sidecar.get("total_bytes"))
    per_turn_growth_bytes = _nonnegative_float(sidecar.get("per_turn_growth_bytes"))
    ok = (
        sidecar.get("surface") == "resident_sidecar_state"
        and 0 < total_bytes <= max_total_bytes
        and 0 < per_turn_growth_bytes <= max_per_turn_growth_bytes
        and bool(families)
    )
    return _check(
        "resident_sidecar_metrics",
        ok,
        "resident sidecar metrics within cap" if ok else "resident sidecar metrics missing, empty, or over cap",
        {
            "surface": sidecar.get("surface"),
            "total_bytes": total_bytes,
            "max_total_bytes": max_total_bytes,
            "per_turn_growth_bytes": per_turn_growth_bytes,
            "max_per_turn_growth_bytes": max_per_turn_growth_bytes,
            "families": sorted(str(key) for key in families),
        },
    )


def _check_latest_actionable_failure_shape(history: list[dict[str, object]]) -> HotPathCheck:
    projected = json.loads(_render_prompt_history_json(history))
    families = _latest_failure_families(projected)
    duplicate_families = sorted(family for family, count in _counts(families).items() if count > 1)
    failure_results = _non_completed_tool_result_count(history)
    ok = not duplicate_families and (failure_results == 0 or bool(families))
    return _check(
        "latest_actionable_failure_shape",
        ok,
        "latest actionable failure is projected once per family"
        if ok
        else "latest actionable failure projection missing or duplicated",
        {
            "failure_tool_results": failure_results,
            "latest_failure_families": families,
            "duplicate_families": duplicate_families,
        },
    )


def _check_micro_next_action(
    fixture: dict[str, object],
    *,
    expected_categories: tuple[str, ...],
) -> HotPathCheck:
    category = _micro_next_action_category(fixture)
    expected = _expected_micro_categories(expected_categories)
    ok = bool(category) and category != "invalid" and category in expected
    return _check(
        "micro_next_action",
        ok,
        f"micro next-action category={category or '(missing)'} expected={','.join(expected) or '(missing)'}",
        {"category": category, "expected_categories": list(expected)},
    )


def _micro_next_action_category(fixture: dict[str, object]) -> str:
    category = str(fixture.get("category") or "").strip()
    if category:
        return category if category in NEXT_ACTION_CATEGORIES else "invalid"
    output = fixture.get("model_output")
    if not isinstance(output, dict):
        return ""
    calls = output.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        finish = output.get("finish")
        return "invalid" if finish else ""
    first = calls[0] if isinstance(calls[0], dict) else {}
    tool_name = str(first.get("name") or first.get("tool_name") or "").strip()
    arguments = first.get("arguments") if isinstance(first.get("arguments"), dict) else {}
    if tool_name in {"write_file", "edit_file", "apply_patch"}:
        return "patch/edit"
    if tool_name == "run_tests":
        return "run_verifier"
    if tool_name == "run_command":
        intent = str(arguments.get("command_intent") or "").lower()
        command = str(arguments.get("command") or arguments.get("cmd") or "").lower()
        if "verify" in intent or "test" in intent or "pytest" in command or "node " in command:
            return "run_verifier"
        return "cheap_probe"
    if tool_name in {"read_file", "search_text", "glob", "inspect_dir"}:
        return "cheap_probe"
    return "invalid"


def _expected_micro_categories(expected_categories: Iterable[str]) -> tuple[str, ...]:
    allowed = set(NEXT_ACTION_CATEGORIES) - {"invalid"}
    expected = tuple(
        str(item).strip()
        for item in expected_categories
        if str(item).strip() in allowed
    )
    if expected:
        return expected
    return tuple(category for category in NEXT_ACTION_CATEGORIES if category in allowed)


def _latest_failure_families(projected_history: object) -> list[str]:
    families: list[str] = []
    for value in _walk(projected_history):
        if not isinstance(value, dict):
            continue
        if value.get("replaced_by_later_latest_failure"):
            continue
        latest_failure = value.get("latest_failure")
        if isinstance(latest_failure, dict):
            family = _latest_failure_family(latest_failure)
            if family:
                families.append(family)
        latest_failures = value.get("latest_failures")
        if isinstance(latest_failures, list):
            for item in latest_failures:
                if isinstance(item, dict):
                    family = _latest_failure_family(item)
                    if family:
                        families.append(family)
    return families


def _latest_failure_family(latest_failure: dict[str, object]) -> str:
    failure_class = str(latest_failure.get("class") or latest_failure.get("failure_class") or "").strip()
    failure_kind = str(latest_failure.get("kind") or "").strip()
    summary = str(latest_failure.get("summary") or latest_failure.get("required_next_action") or "").strip()
    identity = summary[:120] if summary else "unknown"
    return f"{failure_class or 'unknown'}:{failure_kind or 'unknown'}:{identity}"


def _non_completed_tool_result_count(history: list[dict[str, object]]) -> int:
    count = 0
    for entry in history:
        results = entry.get("tool_results") if isinstance(entry.get("tool_results"), list) else []
        for result in results:
            if not isinstance(result, dict):
                continue
            status = str(result.get("status") or "").strip()
            if status and status not in {"completed", "yielded", "running"}:
                count += 1
    return count


def _walk(value: object) -> Iterable[object]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _safe_mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _nonnegative_float(value: object) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _check(name: str, ok: bool, message: str, details: dict[str, object]) -> HotPathCheck:
    return HotPathCheck(name=name, status="pass" if ok else "fail", message=message, details=details)
