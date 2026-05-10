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
import re
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
from .workframe import (
    WORKFRAME_RED_MAX_BYTES,
    WorkFrameInputs,
    canonical_json,
    canonicalize_workframe_inputs,
    workframe_output_hash,
)
from .workframe_variants import reduce_workframe_with_variant

HOT_PATH_FASTCHECK_SCHEMA_VERSION = 1
DEFAULT_HOT_PATH_BASELINE_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "M6_24_HOT_PATH_PHASE0_BASELINE.json"
)
PHASE0_GREEN_TOTAL_RATIO = 1.10
PHASE0_YELLOW_TOTAL_RATIO = 1.25
PHASE0_RED_PER_TURN_GROWTH_RATIO = 1.50
NEXT_ACTION_CATEGORIES = (
    "patch/edit",
    "run_verifier",
    "inspect_latest_failure",
    "cheap_probe",
    "finish_with_evidence",
    "blocked",
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
    baseline: object | None = None,
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
    baseline_data = _load_baseline_json(baseline)
    expected = _expected_micro_categories(expected_categories)

    checks.append(_check_manifest_lane(manifest))
    checks.append(_check_hot_path_metrics(manifest))
    workframe_bundle = _load_workframe_bundle(artifact_path=artifact_path, manifest_path=manifest_path, manifest=manifest)
    checks.append(_check_prompt_leaks(manifest, workframe_bundle=workframe_bundle, max_active_todo_bytes=max_active_todo_bytes))
    checks.append(_check_workframe_replay(workframe_bundle, manifest))
    checks.append(_check_workframe_invariants(workframe_bundle))
    checks.append(_check_workframe_evidence_refs(workframe_bundle))
    checks.append(_check_workframe_reentry_stability(workframe_bundle))
    checks.append(_check_legacy_projection_rejected(history))
    checks.append(
        _check_sidecar_metrics(
            manifest,
            baseline=baseline_data,
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
            workframe_bundle=workframe_bundle,
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
            "workframe": _safe_mapping((manifest.get("metrics") or {}).get("workframe")),
            "baseline": baseline_data,
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


def _load_baseline_json(path: object | None) -> dict[str, object]:
    if path is None or str(path).strip() == "":
        return {}
    baseline_path = Path(str(path)).expanduser().resolve(strict=False)
    if not baseline_path.is_file():
        raise FileNotFoundError(f"hot-path baseline JSON not found: {baseline_path}")
    data = _load_json(baseline_path)
    if not isinstance(data, dict):
        raise ValueError(f"expected hot-path baseline JSON object: {baseline_path}")
    return dict(data)


def _load_history_json(path: Path) -> list[dict[str, object]]:
    data = _load_json(path)
    if not isinstance(data, list):
        raise ValueError(f"expected implement_v2 history array: {path}")
    return [dict(item) for item in data if isinstance(item, dict)]


def _load_workframe_bundle(
    *,
    artifact_path: Path,
    manifest_path: Path,
    manifest: dict[str, object],
) -> dict[str, object]:
    bundle_dir = _resolve_workframe_bundle_dir(
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    if bundle_dir is None:
        return {
            "bundle_dir": "",
            "missing": True,
            "missing_files": [
                "reducer_inputs.json",
                "reducer_output.workframe.json",
                "invariant_report.json",
                "prompt_visible_workframe.json",
                "prompt_render_inventory.json",
            ],
        }
    files = {
        "reducer_inputs": bundle_dir / "reducer_inputs.json",
        "reducer_output": bundle_dir / "reducer_output.workframe.json",
        "invariant_report": bundle_dir / "invariant_report.json",
        "prompt_visible_workframe": bundle_dir / "prompt_visible_workframe.json",
        "prompt_render_inventory": bundle_dir / "prompt_render_inventory.json",
        "workframe_cursor": bundle_dir / "workframe_cursor.json",
        "reentry_fixture": bundle_dir / "reentry_fixture.json",
    }
    loaded: dict[str, object] = {"bundle_dir": str(bundle_dir), "missing": False, "files": {key: str(path) for key, path in files.items()}}
    missing: list[str] = []
    for key, path in files.items():
        if not path.is_file():
            if key in {"workframe_cursor", "reentry_fixture"}:
                continue
            missing.append(path.name)
            continue
        loaded[key] = _load_json(path)
    loaded["missing_files"] = missing
    return loaded


def _resolve_workframe_bundle_dir(
    *,
    artifact_path: Path,
    manifest_path: Path,
    manifest: dict[str, object],
) -> Path | None:
    workframe_metrics = _safe_mapping(_safe_mapping(manifest.get("metrics")).get("workframe"))
    bundle_root = str(workframe_metrics.get("bundle_root") or "").strip()
    if bundle_root:
        candidate = (manifest_path.parent / bundle_root).resolve(strict=False)
        return candidate if candidate.is_dir() else candidate
    if (artifact_path / "reducer_inputs.json").is_file():
        return artifact_path.resolve(strict=False)
    if (manifest_path.parent / "reducer_inputs.json").is_file():
        return manifest_path.parent.resolve(strict=False)
    roots = [
        manifest_path.parent / "workframes",
        artifact_path / "implement_v2" / "workframes",
        artifact_path / "workframes",
    ]
    candidates: list[Path] = []
    for root in roots:
        if root.is_dir():
            candidates.extend(path for path in root.iterdir() if (path / "reducer_inputs.json").is_file())
    if candidates:
        return sorted(candidates, key=lambda path: path.name)[-1].resolve(strict=False)
    return None


def _workframe_inputs_from_mapping(value: object) -> WorkFrameInputs | None:
    data = _safe_mapping(value)
    raw = _safe_mapping(data.get("workframe_inputs")) or data
    if not raw:
        return None
    return WorkFrameInputs(
        attempt_id=str(raw.get("attempt_id") or ""),
        turn_id=str(raw.get("turn_id") or ""),
        task_id=str(raw.get("task_id") or ""),
        objective=str(raw.get("objective") or ""),
        success_contract_ref=str(raw.get("success_contract_ref") or ""),
        constraints=tuple(str(item) for item in raw.get("constraints") or () if str(item)),
        sidecar_events=tuple(dict(item) for item in raw.get("sidecar_events") or () if isinstance(item, dict)),
        prompt_inventory=tuple(dict(item) for item in raw.get("prompt_inventory") or () if isinstance(item, dict)),
        baseline_metrics=_safe_mapping(raw.get("baseline_metrics")),
        previous_workframe_hash=str(raw.get("previous_workframe_hash") or ""),
        workspace_root=str(raw.get("workspace_root") or ""),
        artifact_root=str(raw.get("artifact_root") or ""),
        schema_version=_nonnegative_int(raw.get("schema_version")) or 1,
    )


def _workframe_bundle_prompt_inventory(bundle: dict[str, object]) -> list[dict[str, object]]:
    inventory = _safe_mapping(bundle.get("prompt_render_inventory"))
    sections = inventory.get("sections")
    return [dict(item) for item in sections if isinstance(item, dict)] if isinstance(sections, list) else []


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
    workframe_bundle: dict[str, object],
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
        workframe_bundle=workframe_bundle,
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
    workframe_bundle: dict[str, object],
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
    workframe_output = _safe_mapping(workframe_bundle.get("reducer_output"))
    prompt_visible_workframe = _safe_mapping(workframe_bundle.get("prompt_visible_workframe"))
    workframe_output_digest = _json_sha256(workframe_output)
    prompt_visible_digest = _json_sha256(prompt_visible_workframe)
    workframe_trace = _safe_mapping(workframe_output.get("trace"))
    prompt = _build_micro_next_action_prompt(
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        history_path=history_path,
        projected_history=projected_history,
        expected_categories=expected_categories,
        hot_path=hot_path,
        sidecar=sidecar,
        workframe_output=workframe_output,
        prompt_visible_workframe=prompt_visible_workframe,
    )
    prompt_digest = _text_sha256(prompt)
    context_hash = _json_sha256(
        {
            "manifest_sha256": manifest_digest,
            "history_sha256": history_digest,
            "projected_history_sha256": projected_history_digest,
            "prompt_sha256": prompt_digest,
            "expected_categories": list(_expected_micro_categories(expected_categories)),
            "workframe_output_sha256": workframe_output_digest,
            "prompt_visible_workframe_sha256": prompt_visible_digest,
            "workframe_input_hash": workframe_trace.get("input_hash"),
            "workframe_output_hash": workframe_trace.get("output_hash"),
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
        "workframe_output_sha256": workframe_output_digest,
        "prompt_visible_workframe_sha256": prompt_visible_digest,
        "workframe_input_hash": workframe_trace.get("input_hash"),
        "workframe_output_hash": workframe_trace.get("output_hash"),
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
    workframe_output: dict[str, object],
    prompt_visible_workframe: dict[str, object],
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
                    "category": "patch/edit | run_verifier | inspect_latest_failure | cheap_probe | finish_with_evidence | blocked | invalid",
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
            "Current WorkFrame JSON:",
            _clip_text(json.dumps(prompt_visible_workframe or {"workframe": workframe_output}, ensure_ascii=False, sort_keys=True), 12000),
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
            "workframe_output_sha256": context.get("workframe_output_sha256"),
            "prompt_visible_workframe_sha256": context.get("prompt_visible_workframe_sha256"),
            "workframe_input_hash": context.get("workframe_input_hash"),
            "workframe_output_hash": context.get("workframe_output_hash"),
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
    workframe = _safe_mapping(metrics.get("workframe"))
    phase = str(hot_path.get("phase") or "")
    ok = bool(hot_path) and phase.startswith("m6_24_workframe_redesign_phase_")
    return _check(
        "hot_path_projection_metrics",
        ok,
        "hot_path_projection metrics present" if ok else "missing or stale hot_path_projection metrics",
        {
            "phase": phase,
            "normal_full_prompt_bytes": hot_path.get("normal_full_prompt_bytes"),
            "workframe_phase": workframe.get("phase"),
            "workframe_output_hash": workframe.get("output_hash"),
        },
    )


def _check_prompt_leaks(
    manifest: dict[str, object],
    *,
    workframe_bundle: dict[str, object],
    max_active_todo_bytes: int,
) -> HotPathCheck:
    hot_path = _safe_mapping(_safe_mapping(manifest.get("metrics")).get("hot_path_projection"))
    bundle_inventory = _workframe_bundle_prompt_inventory(workframe_bundle)
    inventory = bundle_inventory or hot_path.get("normal_section_inventory")
    ordinary = (
        [dict(item) for item in inventory if isinstance(item, dict) and item.get("visibility") == "ordinary"]
        if isinstance(inventory, list)
        else []
    )
    disallowed = []
    active_todo_bytes = 0
    workframe_sections = []
    for section in ordinary:
        section_id = str(section.get("id") or "")
        lowered = section_id.lower()
        if any(
            token in lowered
            for token in (
                "frontier_state_update",
                "active_work_todo",
                "hard_runtime_frontier",
                "repair_history",
                "proof_manifest",
                "oracle_bundle",
                "typed_evidence_object",
                "execution_contract_object",
            )
        ):
            disallowed.append(section_id)
        if section_id == "implement_v2_workframe":
            workframe_sections.append(section)
        if section_id == "implement_v2_active_work_todo":
            active_todo_bytes = _nonnegative_int(section.get("bytes"))
    prompt_visible = _safe_mapping(workframe_bundle.get("prompt_visible_workframe"))
    visible_text = json.dumps(prompt_visible, ensure_ascii=False, sort_keys=True)
    visible_leaks = [
        token
        for token in (
            "frontier_state_update",
            "implement_v2_active_work_todo",
            "lane_hard_runtime_frontier",
            "proof_manifest",
            "oracle_bundle",
            "typed_evidence_object",
            "execution_contract_object",
            '"execution_contract"',
            '"oracle_bundle"',
        )
        if token in visible_text
    ]
    ok = (
        len(workframe_sections) == 1
        and not disallowed
        and not visible_leaks
        and active_todo_bytes <= max_active_todo_bytes
    )
    return _check(
        "prompt_leak_contract",
        ok,
        "normal prompt exposes exactly one WorkFrame and no legacy projection"
        if ok
        else "normal prompt exposes disallowed, duplicated, or oversized hot-path state",
        {
            "disallowed_sections": disallowed,
            "workframe_section_count": len(workframe_sections),
            "visible_leaks": visible_leaks,
            "active_work_todo_bytes": active_todo_bytes,
            "max_active_todo_bytes": max_active_todo_bytes,
        },
    )


def _check_sidecar_metrics(
    manifest: dict[str, object],
    *,
    baseline: dict[str, object],
    max_total_bytes: int,
    max_per_turn_growth_bytes: int,
) -> HotPathCheck:
    sidecar = _safe_mapping(_safe_mapping(manifest.get("metrics")).get("resident_sidecar_state"))
    families = _safe_mapping(sidecar.get("families"))
    total_bytes = _nonnegative_int(sidecar.get("total_bytes"))
    per_turn_growth_bytes = _nonnegative_float(sidecar.get("per_turn_growth_bytes"))
    cap_source = "absolute"
    baseline_sidecar = _baseline_sidecar_metrics(baseline)
    total_band = ""
    per_turn_growth_band = ""
    baseline_missing = bool(baseline) and not baseline_sidecar
    if baseline_sidecar:
        cap_source = "phase0_baseline"
        baseline_total_bytes = _nonnegative_int(baseline_sidecar.get("total_bytes"))
        baseline_growth_bytes = _nonnegative_float(baseline_sidecar.get("per_turn_growth_bytes"))
        max_total_bytes = max(1, int(round(baseline_total_bytes * PHASE0_YELLOW_TOTAL_RATIO)))
        max_per_turn_growth_bytes = max(1, int(round(baseline_growth_bytes * PHASE0_RED_PER_TURN_GROWTH_RATIO)))
        total_band = _ratio_band(
            total_bytes,
            baseline_total_bytes,
            green=PHASE0_GREEN_TOTAL_RATIO,
            yellow=PHASE0_YELLOW_TOTAL_RATIO,
        )
        per_turn_growth_band = _ratio_band(
            per_turn_growth_bytes,
            baseline_growth_bytes,
            green=1.0,
            yellow=PHASE0_RED_PER_TURN_GROWTH_RATIO,
        )
    ok = (
        sidecar.get("surface") == "resident_sidecar_state"
        and not baseline_missing
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
            "cap_source": cap_source,
            "baseline_total_bytes": _nonnegative_int(baseline_sidecar.get("total_bytes")) if baseline_sidecar else 0,
            "baseline_per_turn_growth_bytes": (
                _nonnegative_float(baseline_sidecar.get("per_turn_growth_bytes")) if baseline_sidecar else 0.0
            ),
            "total_band": total_band,
            "per_turn_growth_band": per_turn_growth_band,
            "baseline_missing": baseline_missing,
        },
    )


def _check_workframe_replay(bundle: dict[str, object], manifest: dict[str, object] | None = None) -> HotPathCheck:
    missing = [str(item) for item in bundle.get("missing_files") or () if str(item)]
    if bundle.get("missing") or missing:
        return _check(
            "workframe_replay",
            False,
            "missing WorkFrame replay bundle",
            {"bundle_dir": bundle.get("bundle_dir"), "missing_files": missing},
        )
    inputs = _workframe_inputs_from_mapping(bundle.get("reducer_inputs"))
    if inputs is None:
        return _check("workframe_replay", False, "invalid reducer_inputs.json", {"bundle_dir": bundle.get("bundle_dir")})
    stored_inputs = _safe_mapping(bundle.get("reducer_inputs"))
    workframe_variant = str(
        stored_inputs.get("workframe_variant")
        or _safe_mapping(_safe_mapping((manifest or {}).get("metrics")).get("workframe")).get("variant")
        or "current"
    )
    stored_canonical = _safe_mapping(stored_inputs.get("canonical"))
    canonical = canonicalize_workframe_inputs(inputs)
    workframe, report = reduce_workframe_with_variant(inputs, variant=workframe_variant)
    stored_output = _safe_mapping(bundle.get("reducer_output"))
    recomputed_output = workframe.as_dict()
    stored_report = _safe_mapping(bundle.get("invariant_report"))
    manifest_workframe = _safe_mapping(_safe_mapping((manifest or {}).get("metrics")).get("workframe"))
    manifest_input_hash = str(manifest_workframe.get("input_hash") or "")
    manifest_output_hash = str(manifest_workframe.get("output_hash") or "")
    ok = (
        bool(stored_canonical)
        and stored_canonical == canonical
        and stored_output == recomputed_output
        and _safe_mapping(stored_output.get("trace")).get("output_hash") == workframe_output_hash(workframe)
        and bool(manifest_input_hash)
        and bool(manifest_output_hash)
        and manifest_input_hash == workframe.trace.input_hash
        and manifest_output_hash == workframe.trace.output_hash
        and stored_report.get("status") == report.status
    )
    return _check(
        "workframe_replay",
        ok,
        "saved WorkFrame replay matches reducer" if ok else "saved WorkFrame replay does not match reducer",
        {
            "bundle_dir": bundle.get("bundle_dir"),
            "workframe_variant": workframe_variant,
            "stored_input_hash": _safe_mapping(stored_output.get("trace")).get("input_hash"),
            "recomputed_input_hash": workframe.trace.input_hash,
            "stored_output_hash": _safe_mapping(stored_output.get("trace")).get("output_hash"),
            "recomputed_output_hash": workframe.trace.output_hash,
            "manifest_input_hash": manifest_input_hash,
            "manifest_output_hash": manifest_output_hash,
            "manifest_input_hash_present": bool(manifest_input_hash),
            "manifest_output_hash_present": bool(manifest_output_hash),
            "manifest_input_hash_matches": manifest_input_hash == workframe.trace.input_hash,
            "manifest_output_hash_matches": manifest_output_hash == workframe.trace.output_hash,
            "canonical_present": bool(stored_canonical),
            "canonical_matches": stored_canonical == canonical,
            "output_matches": stored_output == recomputed_output,
            "stored_invariant_status": stored_report.get("status"),
            "recomputed_invariant_status": report.status,
        },
    )


def _check_workframe_invariants(bundle: dict[str, object]) -> HotPathCheck:
    output = _safe_mapping(bundle.get("reducer_output"))
    report = _safe_mapping(bundle.get("invariant_report"))
    serialized_bytes = len(canonical_json(output).encode("utf-8")) if output else 0
    ok = bool(output) and report.get("status") == "pass" and 0 < serialized_bytes <= WORKFRAME_RED_MAX_BYTES
    return _check(
        "workframe_invariants",
        ok,
        "WorkFrame invariants pass" if ok else "WorkFrame invariants fail or frame exceeds cap",
        {
            "status": report.get("status"),
            "failed": report.get("failed") if isinstance(report.get("failed"), list) else [],
            "bytes": serialized_bytes,
            "red_cap": WORKFRAME_RED_MAX_BYTES,
            "current_phase": output.get("current_phase"),
        },
    )


def _check_workframe_evidence_refs(bundle: dict[str, object]) -> HotPathCheck:
    output = _safe_mapping(bundle.get("reducer_output"))
    inputs = _workframe_inputs_from_mapping(bundle.get("reducer_inputs"))
    resolver = _workframe_resolvable_refs(inputs)
    unresolved: list[str] = []
    replay_model_fetchable: list[str] = []
    for ref in _workframe_output_refs(output):
        if ref.startswith("replay:"):
            replay_model_fetchable.append(ref) if _ref_is_model_fetchable(ref) else None
            continue
        if ref not in resolver:
            unresolved.append(ref)
    ok = not unresolved and not replay_model_fetchable
    return _check(
        "workframe_evidence_ref_policy",
        ok,
        "WorkFrame evidence refs resolve to sidecar/typed facts"
        if ok
        else "WorkFrame evidence refs are unresolved or replay-fetchable",
        {
            "unresolved": sorted(set(unresolved)),
            "replay_model_fetchable": sorted(set(replay_model_fetchable)),
            "resolver_count": len(resolver),
        },
    )


def _check_workframe_reentry_stability(bundle: dict[str, object]) -> HotPathCheck:
    fixture = _safe_mapping(bundle.get("reentry_fixture"))
    if not fixture:
        return _check(
            "workframe_reentry_stability",
            True,
            "no reentry fixture present; stability check skipped",
            {"skipped": True},
        )
    before = _safe_mapping(fixture.get("before") or fixture.get("pre_resume"))
    after = _safe_mapping(fixture.get("after") or fixture.get("post_resume"))
    before_required = _safe_mapping(before.get("required_next"))
    after_required = _safe_mapping(after.get("required_next"))
    before_forbidden = before.get("forbidden_next") if isinstance(before.get("forbidden_next"), list) else []
    after_forbidden = after.get("forbidden_next") if isinstance(after.get("forbidden_next"), list) else []
    semantic_changed = bool(fixture.get("semantic_event_changed"))
    ok = semantic_changed or (before_required == after_required and before_forbidden == after_forbidden)
    return _check(
        "workframe_reentry_stability",
        ok,
        "reentry preserved required_next/forbidden_next"
        if ok
        else "reentry drifted required_next/forbidden_next without semantic event",
        {
            "semantic_event_changed": semantic_changed,
            "required_next_matches": before_required == after_required,
            "forbidden_next_matches": before_forbidden == after_forbidden,
        },
    )


def _check_legacy_projection_rejected(history: list[dict[str, object]]) -> HotPathCheck:
    leaked: list[dict[str, object]] = []
    rejected = 0
    for entry in history:
        for value in _walk(entry):
            if not isinstance(value, dict):
                continue
            if "frontier_state_update" in value:
                leaked.append({"turn": entry.get("turn"), "field": "frontier_state_update"})
            if value.get("class") == "legacy_projection_field_rejected":
                rejected += 1
            if value.get("class") == "legacy_projection_field_ignored":
                leaked.append({"turn": entry.get("turn"), "field": "legacy_projection_field_ignored"})
    ok = not leaked
    return _check(
        "legacy_projection_field_rejected",
        ok,
        "no legacy model projection fields reached saved history"
        if ok
        else "legacy model projection fields were ignored or leaked instead of hard-rejected",
        {"leaked": leaked, "rejected_events": rejected},
    )


def _workframe_resolvable_refs(inputs: WorkFrameInputs | None) -> set[str]:
    refs: set[str] = set()
    if inputs is None:
        return refs
    if inputs.success_contract_ref:
        refs.add(inputs.success_contract_ref)
    for event in inputs.sidecar_events:
        refs.update(_resolvable_refs_from_event(event))
    return refs


def _resolvable_refs_from_event(event: dict[str, object]) -> set[str]:
    refs: set[str] = set()
    for value in _walk(event):
        if not isinstance(value, dict):
            continue
        for key in (
            "event_id",
            "event_ref",
            "evidence_ref",
            "evidence_id",
            "command_run_id",
            "typed_evidence_id",
            "id",
            "ref",
            "contract_id",
            "finish_gate_id",
            "oracle_bundle_id",
            "output_ref",
        ):
            ref = str(value.get(key) or "").strip()
            if ref:
                refs.add(ref)
        for key in ("evidence_refs", "required_evidence_refs", "missing_obligations", "required_obligations", "oracle_obligations"):
            refs.update(_refs_from_ref_list(value.get(key)))
        for key in ("execution_contract", "execution_contract_normalized", "finish_gate", "oracle_bundle", "typed_acceptance"):
            refs.update(_refs_from_nested_mapping(value.get(key)))
    return refs


def _refs_from_nested_mapping(value: object) -> set[str]:
    refs: set[str] = set()
    if not isinstance(value, dict):
        return refs
    for key in ("id", "ref", "evidence_id", "contract_id", "finish_gate_id", "oracle_bundle_id"):
        ref = str(value.get(key) or "").strip()
        if ref:
            refs.add(ref)
    for key in ("evidence_refs", "required_evidence_refs", "missing_obligations", "required_obligations", "oracle_obligations"):
        refs.update(_refs_from_ref_list(value.get(key)))
    digest = value.get("digest") if isinstance(value.get("digest"), dict) else {}
    refs.update(_refs_from_ref_list(digest.get("missing_obligations")))
    return refs


def _refs_from_ref_list(value: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, str) and value.strip():
        refs.add(value.strip())
    elif isinstance(value, dict):
        refs.update(_refs_from_nested_mapping(value))
    elif isinstance(value, (list, tuple)):
        for item in value:
            refs.update(_refs_from_ref_list(item))
    return refs


def _workframe_output_refs(output: dict[str, object]) -> set[str]:
    refs: set[str] = set()
    for value in _walk(output):
        if not isinstance(value, dict):
            continue
        for key in ("evidence_refs", "required_evidence_refs", "missing_obligations"):
            raw = value.get(key)
            if isinstance(raw, list):
                refs.update(str(item) for item in raw if str(item))
        for key in ("source_ref", "latest_mutation_ref", "last_strict_verifier_ref", "configured_verifier_ref"):
            ref = str(value.get(key) or "").strip()
            if ref:
                refs.add(ref)
    return refs


def _ref_is_model_fetchable(ref: str) -> bool:
    return ref.startswith(("tool:", "out:", "sidecar:", "ev:", "cmd:", "contract:", "oracle:"))


def _baseline_sidecar_metrics(baseline: dict[str, object]) -> dict[str, object]:
    metrics = _safe_mapping(baseline.get("metrics"))
    sidecar = _safe_mapping(metrics.get("resident_sidecar_state"))
    if sidecar:
        return sidecar
    return _safe_mapping(baseline.get("resident_sidecar_state"))


def _check_latest_actionable_failure_shape(history: list[dict[str, object]]) -> HotPathCheck:
    projected = json.loads(_render_prompt_history_json(history))
    families = _latest_failure_families(projected)
    duplicate_families = sorted(family for family, count in _counts(families).items() if count > 1)
    generic_runtime_failures = _generic_runtime_failure_summaries(projected)
    failure_results = _non_completed_tool_result_count(history)
    ok = not duplicate_families and not generic_runtime_failures and (failure_results == 0 or bool(families))
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
            "generic_runtime_failures": generic_runtime_failures,
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
        if isinstance(finish, dict):
            outcome = str(finish.get("outcome") or "").strip().lower()
            if outcome in {"completed", "task_complete", "done", "success"}:
                return "finish_with_evidence"
            if outcome in {"blocked", "failed"}:
                return "blocked"
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
            family = _latest_failure_family(latest_failure, context=value)
            if family:
                families.append(family)
        latest_failures = value.get("latest_failures")
        if isinstance(latest_failures, list):
            for item in latest_failures:
                if isinstance(item, dict):
                    family = _latest_failure_family(item, context=value)
                    if family:
                        families.append(family)
    return families


def _latest_failure_family(latest_failure: dict[str, object], *, context: dict[str, object] | None = None) -> str:
    failure_class = str(latest_failure.get("class") or latest_failure.get("failure_class") or "").strip()
    failure_kind = str(latest_failure.get("kind") or "").strip()
    provider_identity = str(latest_failure.get("provider_family_identity") or "").strip()
    artifact_identity = provider_identity or _latest_failure_artifact_identity(latest_failure, context=context)
    if artifact_identity:
        identity = artifact_identity
    else:
        summary = str(latest_failure.get("summary") or latest_failure.get("required_next_action") or "").strip()
        identity = f"summary:{summary[:120]}" if summary else "unknown"
    return f"{failure_class or 'unknown'}:{failure_kind or 'unknown'}:{identity}"


def _latest_failure_artifact_identity(
    latest_failure: dict[str, object],
    *,
    context: dict[str, object] | None = None,
) -> str:
    for source in (context, latest_failure):
        if not isinstance(source, dict):
            continue
        digest = source.get("execution_evidence_digest")
        if isinstance(digest, dict):
            artifact_misses = digest.get("artifact_miss")
            if isinstance(artifact_misses, list):
                for artifact in artifact_misses:
                    if not isinstance(artifact, dict):
                        continue
                    artifact_id = str(artifact.get("artifact_id") or "").strip()
                    path = str(artifact.get("path") or "").strip()
                    if artifact_id or path:
                        return f"artifact:{artifact_id}:{path}"
        artifact_evidence = source.get("artifact_evidence")
        if isinstance(artifact_evidence, list):
            for artifact in artifact_evidence:
                if not isinstance(artifact, dict):
                    continue
                if artifact.get("status") in {"passed", "completed"} or artifact.get("blocking") is False:
                    continue
                artifact_id = str(artifact.get("artifact_id") or "").strip()
                path = str(artifact.get("path") or "").strip()
                if artifact_id or path:
                    return f"artifact:{artifact_id}:{path}"
    path = str(latest_failure.get("path") or "").strip()
    return f"path:{path}" if path else ""


def _generic_runtime_failure_summaries(projected_history: object) -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    for value in _walk(projected_history):
        if not isinstance(value, dict):
            continue
        for latest_failure in _iter_latest_failure_dicts(value):
            failure_class = str(latest_failure.get("class") or latest_failure.get("failure_class") or "").strip()
            summary = str(latest_failure.get("summary") or "").strip().lower()
            if failure_class == "runtime_failure" and _is_generic_runtime_failure_summary(summary):
                failures.append(
                    {
                        "class": failure_class,
                        "kind": str(latest_failure.get("kind") or ""),
                        "summary": str(latest_failure.get("summary") or ""),
                    }
                )
    return failures


def _is_generic_runtime_failure_summary(summary: str) -> bool:
    text = summary.strip().lower()
    return bool(
        text in {"exit code 1", "command failed", "failed", "killed", "interrupted"}
        or re.fullmatch(r"exit code \d+", text)
        or re.fullmatch(r"tool run .* ended with killed", text)
        or re.fullmatch(r"tool run .* ended with interrupted", text)
    )


def _iter_latest_failure_dicts(value: dict[str, object]) -> Iterable[dict[str, object]]:
    latest_failure = value.get("latest_failure")
    if isinstance(latest_failure, dict):
        yield latest_failure
    latest_failures = value.get("latest_failures")
    if isinstance(latest_failures, list):
        for item in latest_failures:
            if isinstance(item, dict):
                yield item


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
    elif isinstance(value, (list, tuple)):
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


def _ratio_band(value: float, baseline: float, *, green: float, yellow: float) -> str:
    if baseline <= 0:
        return ""
    ratio = value / baseline
    if ratio <= green:
        return "green"
    if ratio <= yellow:
        return "yellow"
    return "red"


def _check(name: str, ok: bool, message: str, details: dict[str, object]) -> HotPathCheck:
    return HotPathCheck(name=name, status="pass" if ok else "fail", message=message, details=details)
