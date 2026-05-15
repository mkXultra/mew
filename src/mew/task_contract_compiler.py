"""LLM-backed task contract compiler for implement_v2.

The compiler turns a raw task record into a typed contract that finish gating
can consume without growing task-specific string heuristics.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping


TASK_CONTRACT_COMPILER_SCHEMA_VERSION = 1
TASK_CONTRACT_COMPILER_PROMPT_VERSION = "2026-05-15.default-on-v1"
TASK_CONTRACT_COMPILER_TYPED_STATUSES = frozenset({"compiled", "typed_fallback"})

_ARTIFACT_KINDS = {
    "file",
    "directory",
    "stdout",
    "stderr",
    "json",
    "image",
    "binary",
    "executable",
    "report",
    "log",
}
_ARTIFACT_FRESHNESS = {
    "exists_before_or_after",
    "created_after_run_start",
    "modified_after_run_start",
    "modified_after_previous_check",
}


def build_task_contract_compiler_prompt(task_contract: Mapping[str, Any]) -> str:
    """Return the model prompt for compiling a raw task contract."""

    payload = _compact_json(dict(task_contract))
    schema = {
        "schema_version": TASK_CONTRACT_COMPILER_SCHEMA_VERSION,
        "goal": "single sentence user-visible goal",
        "objective": "verbatim or compact task objective",
        "completion_criteria": ["criterion that must be true at finish"],
        "expected_artifacts": [
            {
                "id": "artifact id",
                "kind": "file|directory|stdout|stderr|json|image|binary|executable|report|log",
                "path": "path if the task requires a concrete file",
                "required": True,
                "freshness": "exists_before_or_after|created_after_run_start|modified_after_run_start|modified_after_previous_check",
                "checks": [{"type": "exists"}, {"type": "non_empty"}],
            }
        ],
        "verifier": {
            "command": "explicit final verifier command, if the task provides one",
            "must_pass": True,
        },
        "source_requirements": [{"path": "source path that must be inspected or edited"}],
        "unknowns": ["ambiguity that should not be guessed"],
    }
    return (
        "Compile this raw mew task contract into typed completion requirements.\n"
        "Return JSON only. Do not include markdown. Do not invent artifacts that the task does not require.\n"
        "Prefer structural obligations over natural-language acceptance text. If an artifact is produced by a "
        "final verifier run, use freshness=created_after_run_start or modified_after_run_start.\n"
        "If the raw contract already contains an explicit verify_command, preserve it in verifier.command.\n\n"
        "Output schema example:\n"
        f"{_compact_json(schema)}\n\n"
        "Raw task contract:\n"
        f"{payload}"
    )


def compile_task_contract_with_model(
    task_contract: Mapping[str, Any],
    *,
    model_backend: str,
    model_auth: Mapping[str, Any],
    model: str,
    base_url: str,
    timeout: float,
    call_json: Callable[..., object],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile and apply a task contract using the provided JSON model call."""

    prompt = build_task_contract_compiler_prompt(task_contract)
    raw_response = call_json(model_backend, model_auth, prompt, model, base_url, timeout)
    compiled = normalize_compiled_task_contract(raw_response)
    updated = apply_compiled_task_contract(task_contract, compiled)
    report = {
        "status": "compiled",
        "schema_version": TASK_CONTRACT_COMPILER_SCHEMA_VERSION,
        "prompt_version": TASK_CONTRACT_COMPILER_PROMPT_VERSION,
        "model_backend": model_backend,
        "model": model,
        "expected_artifact_count": len(updated.get("expected_artifacts") or []),
        "completion_criteria_count": len(updated.get("completion_criteria") or []),
    }
    return updated, report


def apply_compiled_task_contract(
    task_contract: Mapping[str, Any],
    compiled_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply a normalized compiled contract to the raw implement_v2 task contract."""

    base = dict(task_contract)
    compiled = normalize_compiled_task_contract(compiled_contract)
    legacy_constraints = base.get("acceptance_constraints")
    if legacy_constraints:
        base["legacy_acceptance_constraints"] = list(legacy_constraints) if isinstance(legacy_constraints, list) else legacy_constraints
    base["acceptance_constraints"] = []
    base["acceptance_mode"] = "typed_task_contract"
    base["legacy_string_gate_mode"] = "disabled_by_task_contract_compiler"
    if compiled.get("goal"):
        base["goal"] = compiled["goal"]
    if compiled.get("objective"):
        base["objective"] = compiled["objective"]
    if compiled.get("completion_criteria"):
        base["completion_criteria"] = list(compiled["completion_criteria"])
    if compiled.get("source_requirements"):
        base["source_requirements"] = [dict(item) for item in compiled["source_requirements"]]
    if compiled.get("expected_artifacts"):
        base["expected_artifacts"] = [dict(item) for item in compiled["expected_artifacts"]]
    verifier = compiled.get("verifier")
    if isinstance(verifier, dict):
        command = str(verifier.get("command") or "").strip()
        explicit_command = str(base.get("verify_command") or "").strip()
        if explicit_command:
            compiled.setdefault("verifier", {})["command"] = explicit_command
            compiled.setdefault("verifier", {})["must_pass"] = True
        elif command:
            base["verify_command"] = command
    base["compiled_task_contract"] = dict(compiled)
    base["task_contract_compiler"] = {
        "status": "compiled",
        "schema_version": TASK_CONTRACT_COMPILER_SCHEMA_VERSION,
        "prompt_version": TASK_CONTRACT_COMPILER_PROMPT_VERSION,
    }
    return base


def task_contract_compiler_failure_contract(
    task_contract: Mapping[str, Any],
    *,
    error: object,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a typed fallback contract and metrics for compiler failures.

    The default path must not silently return to legacy string gates. If the
    compiler call fails, keep implement_v2 on typed task-contract semantics with
    the explicit raw verifier and a conservative natural-language criterion.
    Operators can still opt into the old path with task_contract_compiler=legacy.
    """

    fallback = normalize_compiled_task_contract(
        {
            "goal": task_contract.get("title") or task_contract.get("description") or "",
            "objective": task_contract.get("description") or task_contract.get("title") or "",
            "completion_criteria": task_contract.get("acceptance_constraints") or task_contract.get("description") or [],
            "verifier": {
                "command": task_contract.get("verify_command") or "",
                "must_pass": bool(task_contract.get("verify_command")),
            },
            "expected_artifacts": [],
            "source_requirements": [],
            "unknowns": ["task_contract_compiler model call failed; legacy string gates remain disabled"],
        }
    )
    updated = apply_compiled_task_contract(task_contract, fallback)
    updated["task_contract_compiler"] = {
        "status": "typed_fallback",
        "schema_version": TASK_CONTRACT_COMPILER_SCHEMA_VERSION,
        "prompt_version": TASK_CONTRACT_COMPILER_PROMPT_VERSION,
        "error": str(error or ""),
    }
    updated["compiled_task_contract"]["fallback_reason"] = "compiler_failed"
    return updated, {
        "status": "typed_fallback",
        "schema_version": TASK_CONTRACT_COMPILER_SCHEMA_VERSION,
        "prompt_version": TASK_CONTRACT_COMPILER_PROMPT_VERSION,
        "error": str(error or ""),
    }


def normalize_compiled_task_contract(value: object) -> dict[str, Any]:
    """Normalize model output into the stable task-contract compiler schema."""

    raw = _mapping(value)
    if isinstance(raw.get("task_contract"), Mapping):
        raw = _mapping(raw.get("task_contract"))
    if isinstance(raw.get("compiled_task_contract"), Mapping):
        raw = _mapping(raw.get("compiled_task_contract"))
    verifier = _mapping(raw.get("verifier"))
    verify_command = str(raw.get("verify_command") or verifier.get("command") or "").strip()
    normalized_verifier = {
        "command": verify_command,
        "must_pass": bool(verifier.get("must_pass", True)),
    }
    return {
        "schema_version": TASK_CONTRACT_COMPILER_SCHEMA_VERSION,
        "prompt_version": TASK_CONTRACT_COMPILER_PROMPT_VERSION,
        "goal": _clean_text(raw.get("goal")),
        "objective": _clean_text(raw.get("objective") or raw.get("description")),
        "completion_criteria": _clean_text_list(
            raw.get("completion_criteria") or raw.get("acceptance_criteria") or raw.get("criteria")
        ),
        "expected_artifacts": _normalize_expected_artifacts(raw.get("expected_artifacts")),
        "verifier": normalized_verifier,
        "source_requirements": _normalize_source_requirements(raw.get("source_requirements")),
        "unknowns": _clean_text_list(raw.get("unknowns")),
    }


def task_contract_compiler_is_compiled(task_contract: Mapping[str, Any] | None) -> bool:
    raw = _mapping(task_contract)
    compiler = _mapping(raw.get("task_contract_compiler"))
    return str(compiler.get("status") or "").strip().casefold() in TASK_CONTRACT_COMPILER_TYPED_STATUSES


def _normalize_expected_artifacts(value: object) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for index, item in enumerate(_list(value), start=1):
        raw = _mapping(item)
        path = _clean_text(raw.get("path") or _mapping(raw.get("target")).get("path"))
        stream = _clean_text(raw.get("stream") or _mapping(raw.get("target")).get("stream"))
        artifact_id = _clean_text(raw.get("id") or path or stream or f"artifact:{index}")
        kind = _clean_text(raw.get("kind")).casefold()
        if kind == "glob" or _path_has_glob_magic(path):
            if bool(raw.get("required", True)):
                artifacts.append(_unsupported_expected_artifact(raw, artifact_id=artifact_id, reason="glob_artifact_unsupported"))
            continue
        if kind not in _ARTIFACT_KINDS:
            kind = stream if stream in {"stdout", "stderr"} else "file"
        freshness = _clean_text(raw.get("freshness")).casefold()
        if freshness not in _ARTIFACT_FRESHNESS:
            freshness = "modified_after_run_start" if path and bool(raw.get("required", True)) else "exists_before_or_after"
        checks = _normalize_checks(raw.get("checks"))
        if freshness != "exists_before_or_after" and not any(
            str(check.get("type") or "").casefold() == "mtime_after" for check in checks
        ):
            checks.append({"type": "mtime_after"})
        artifact: dict[str, Any] = {
            "id": artifact_id,
            "kind": kind,
            "required": bool(raw.get("required", True)),
            "source": "model_declared",
            "confidence": _confidence(raw.get("confidence")),
            "freshness": freshness,
            "checks": checks,
        }
        if path:
            artifact["path"] = path
        if stream:
            artifact["target"] = {"type": "stream", "stream": stream}
        artifacts.append(artifact)
    return artifacts[:12]


def _unsupported_expected_artifact(raw: Mapping[str, Any], *, artifact_id: str, reason: str) -> dict[str, Any]:
    return {
        "id": artifact_id,
        "kind": "file",
        "required": True,
        "source": "model_declared",
        "confidence": "low",
        "freshness": "exists_before_or_after",
        "checks": [
            {
                "type": "unsupported_artifact_contract",
                "reason": reason,
                "original_kind": _clean_text(raw.get("kind")),
                "original_path": _clean_text(raw.get("path") or _mapping(raw.get("target")).get("path")),
                "severity": "blocking",
            }
        ],
    }


def _normalize_checks(value: object) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for item in _list(value):
        raw = _mapping(item)
        if not raw:
            continue
        check = dict(raw)
        check_type = _clean_text(check.get("type") or check.get("check") or check.get("kind") or "exists")
        check["type"] = check_type or "exists"
        checks.append(check)
    if not checks:
        checks.append({"type": "exists"})
    return checks[:8]


def _normalize_source_requirements(value: object) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    for item in _list(value):
        raw = _mapping(item)
        path = _clean_text(raw.get("path") or raw.get("source_ref"))
        if not path:
            continue
        requirement = {"path": path}
        reason = _clean_text(raw.get("reason"))
        if reason:
            requirement["reason"] = reason
        requirements.append(requirement)
    return requirements[:16]


def _path_has_glob_magic(path: str) -> bool:
    return any(char in str(path or "") for char in "*?[")


def _confidence(value: object) -> str:
    text = _clean_text(value).casefold()
    return text if text in {"high", "medium", "low"} else "high"


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _clean_text_list(value: object) -> list[str]:
    return [text for item in _list(value) if (text := _clean_text(item))][:16]


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
