"""Production-safe finish acceptance helpers for implement_v2."""

from __future__ import annotations

import json
import re

from ..acceptance import (
    implementation_contract_source_requirements,
    implementation_source_ref_matches_text,
    is_runtime_visual_artifact_task,
)
from .execution_evidence import (
    build_oracle_bundle,
    evidence_events_from_tool_payload,
    recommend_finish_evidence_refs,
)
from .exec_runtime import EXEC_TOOL_NAMES
from .types import ImplementLaneInput, ToolResultEnvelope


_COMPLETED_FINISH_OUTCOMES = {"completed", "task_complete", "done", "success"}
_EVIDENCE_PROVIDER_CALL_RE = re.compile(r"\bcall-[A-Za-z0-9_.:-]+\b")
_PROVIDER_ID_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:-]+")


def _first_result_payload(result: ToolResultEnvelope) -> dict[str, object]:
    for item in result.content:
        if isinstance(item, dict):
            return item
    return {}


def _finish_outcome(finish_arguments: dict[str, object]) -> str:
    return str((finish_arguments or {}).get("outcome") or (finish_arguments or {}).get("status") or "").strip()


def _live_task_description(lane_input: ImplementLaneInput) -> str:
    contract = lane_input.task_contract if isinstance(lane_input.task_contract, dict) else {}
    chunks = [
        str(contract.get("title") or "").strip(),
        str(contract.get("goal") or "").strip(),
        str(contract.get("objective") or "").strip(),
        str(contract.get("description") or "").strip(),
        str(contract.get("guidance") or "").strip(),
        str(contract.get("verify_command") or "").strip(),
    ]
    criteria = contract.get("completion_criteria")
    if isinstance(criteria, list):
        chunks.extend(str(item or "").strip() for item in criteria)
    return "\n".join(chunk for chunk in chunks if chunk)


def _finish_acceptance_action(
    finish_arguments: dict[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    task_description: str = "",
) -> dict[str, object]:
    action = dict(finish_arguments or {})
    action["task_done"] = _finish_outcome(action) in _COMPLETED_FINISH_OUTCOMES
    checks = action.get("acceptance_checks")
    acceptance_checks: list[object] = []
    if isinstance(checks, list):
        acceptance_checks = [
            _with_finish_evidence_refs(check, tool_results) if isinstance(check, dict) else check for check in checks
        ]
    if not acceptance_checks:
        acceptance_checks = _synthetic_finish_acceptance_checks(action, tool_results)
    sidecar_checks = [
        *_structured_finish_acceptance_checks(tool_results),
        *_source_grounding_finish_acceptance_checks(task_description, tool_results),
    ]
    acceptance_checks = _merge_finish_acceptance_sidecar_checks(acceptance_checks, sidecar_checks)
    action["acceptance_checks"] = acceptance_checks
    existing_refs = _finish_action_evidence_ref_items(action.get("evidence_refs") or action.get("evidence_ref"))
    typed_refs = _typed_finish_evidence_refs(
        tool_results,
        task_description=task_description,
        include_supplemental=not existing_refs,
    )
    merged_refs = _merge_finish_action_evidence_refs(existing_refs, typed_refs)
    if merged_refs:
        action["evidence_refs"] = merged_refs
    return action


def _merge_finish_action_evidence_refs(
    existing: object,
    typed_refs: list[dict[str, object]],
    *,
    limit: int = 16,
) -> list[dict[str, object]]:
    """Merge model refs with obligation-driven refs, keeping required refs first."""

    merged: list[dict[str, object]] = []
    seen: set[str] = set()
    for ref in [*typed_refs, *_finish_action_evidence_ref_items(existing)]:
        key = json.dumps(ref, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        merged.append(ref)
        if len(merged) >= limit:
            break
    return merged


def _finish_action_evidence_ref_items(value: object) -> list[dict[str, object]]:
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return [dict(item) for item in value if item]
    if isinstance(value, dict):
        candidates = [value]
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    elif isinstance(value, str):
        candidates = [value]
    else:
        candidates = []
    refs: list[dict[str, object]] = []
    for item in candidates:
        if isinstance(item, dict):
            if item:
                refs.append(dict(item))
            continue
        if isinstance(item, str) and item.strip():
            refs.append({"kind": "evidence_event", "id": item.strip()})
    return refs


def _typed_finish_evidence_refs(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    include_supplemental: bool = True,
    task_description: object = "",
) -> list[dict[str, object]]:
    source_refs: list[dict[str, object]] = []
    for requirement in implementation_contract_source_requirements(task_description):
        if not isinstance(requirement, dict):
            continue
        source_ref = str(requirement.get("path") or "").strip()
        match = _source_grounding_tool_result(source_ref, tool_results)
        if match is None:
            continue
        tool_index, result = match
        ref = {"kind": "evidence_event", "id": f"ev:source:{source_ref}:{result.provider_call_id or tool_index}"}
        if ref not in source_refs:
            source_refs.append(ref)
    ref_limit = 16
    typed_acceptance = _typed_acceptance_session_from_tool_results(tool_results, lane_input=None)
    recommended = recommend_finish_evidence_refs(
        typed_acceptance.get("oracle_bundle") if isinstance(typed_acceptance.get("oracle_bundle"), dict) else None,
        tuple(item for item in typed_acceptance.get("evidence_events") or () if isinstance(item, dict)),
        include_supplemental=include_supplemental,
        limit=max(0, ref_limit - len(source_refs)),
    )
    if recommended:
        refs = [dict(ref) for ref in recommended]
        for ref in source_refs:
            if ref not in refs:
                refs.append(ref)
        return refs[:ref_limit]
    if not include_supplemental:
        return source_refs[:ref_limit]
    refs: list[dict[str, object]] = []
    fallback_limit = max(0, ref_limit - len(source_refs))
    for index, result in enumerate(tool_results, start=1):
        if len(refs) >= fallback_limit:
            break
        payload = _first_result_payload(result)
        if not payload:
            continue
        for event in evidence_events_from_tool_payload(
            tool_index=index,
            tool_name=result.tool_name,
            tool_status=result.status,
            provider_call_id=result.provider_call_id,
            payload=payload,
        ):
            if event.status != "passed":
                continue
            if event.kind not in {"artifact_check", "verifier_result", "oracle_check", "source_grounding"}:
                continue
            ref = {"kind": "evidence_event", "id": event.id}
            if ref not in refs:
                refs.append(ref)
            if len(refs) >= fallback_limit:
                break
    for ref in source_refs:
        if ref not in refs:
            refs.append(ref)
    return refs[:ref_limit]


def _merge_finish_acceptance_sidecar_checks(
    acceptance_checks: list[object],
    sidecar_checks: list[dict[str, object]],
) -> list[object]:
    if not sidecar_checks:
        return acceptance_checks
    for check in sidecar_checks:
        check.setdefault("source", "finish_sidecar")
    merged: list[object] = []
    for check in sidecar_checks:
        if not _acceptance_check_equivalent_exists(merged, check):
            merged.append(check)
    terminal_sidecars = [check for check in sidecar_checks if _acceptance_check_has_terminal_ref(check)]
    demoted_covered_checks: list[object] = []
    for check in acceptance_checks:
        demoted = _demote_unreferenced_model_check_when_sidecar_covers(check, terminal_sidecars)
        if demoted is not check:
            demoted_covered_checks.append(demoted)
            continue
        if not isinstance(check, dict) or not _acceptance_check_equivalent_exists(merged, check):
            merged.append(check)
    for check in demoted_covered_checks:
        if not isinstance(check, dict) or not _acceptance_check_equivalent_exists(merged, check):
            merged.append(check)
    return merged


def _acceptance_check_equivalent_exists(checks: list[object], candidate: dict[str, object]) -> bool:
    candidate_constraint = str(candidate.get("constraint") or "").casefold().strip()
    candidate_evidence = str(candidate.get("evidence") or "").casefold().strip()
    for check in checks:
        if not isinstance(check, dict):
            continue
        if str(check.get("constraint") or "").casefold().strip() != candidate_constraint:
            continue
        if str(check.get("evidence") or "").casefold().strip() == candidate_evidence:
            return True
    return False


def _acceptance_check_has_terminal_ref(check: object) -> bool:
    if not isinstance(check, dict):
        return False
    refs = check.get("evidence_refs")
    if not isinstance(refs, list):
        return False
    return any(isinstance(ref, dict) and str(ref.get("kind") or "tool_call") == "tool_call" for ref in refs)


def _demote_unreferenced_model_check_when_sidecar_covers(
    check: object,
    terminal_sidecars: list[dict[str, object]],
) -> object:
    if not isinstance(check, dict):
        return check
    if str(check.get("source") or "").endswith("_sidecar"):
        return check
    if str(check.get("status") or "").casefold() not in {"pass", "passed", "satisfied", "verified", "ok"}:
        return check
    if _acceptance_check_has_terminal_ref(check):
        return check
    if not any(_sidecar_constraint_covers_check(sidecar, check) for sidecar in terminal_sidecars):
        return check
    demoted = dict(check)
    demoted["status"] = "unknown"
    demoted["mew_demoted_reason"] = "unreferenced_model_acceptance_check_replaced_by_structured_sidecar"
    return demoted


def _sidecar_constraint_covers_check(sidecar: dict[str, object], check: dict[str, object]) -> bool:
    sidecar_constraint = _normalized_acceptance_constraint(sidecar.get("constraint"))
    check_constraint = _normalized_acceptance_constraint(check.get("constraint"))
    return bool(sidecar_constraint and check_constraint and sidecar_constraint == check_constraint)


def _normalized_acceptance_constraint(value: object) -> str:
    return " ".join(str(value or "").casefold().strip().split())


def _source_grounding_finish_acceptance_checks(
    task_description: object,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    for requirement in implementation_contract_source_requirements(task_description):
        source_ref = str(requirement.get("path") or "").strip()
        if not source_ref:
            continue
        match = _source_grounding_tool_result(source_ref, tool_results)
        if match is None:
            continue
        index, result = match
        provider_call_id = str(result.provider_call_id or "").strip()
        checks.append(
            {
                "constraint": f"provided source or artifact {source_ref} is grounded",
                "status": "verified",
                "source": "source_grounding_sidecar",
                "evidence": (
                    f"{provider_call_id or f'Tool #{index}'} completed {result.tool_name} evidence "
                    f"grounding {source_ref}"
                ),
                "evidence_refs": [{"kind": "tool_call", "id": index}],
            }
        )
    return checks


def _source_grounding_tool_result(
    source_ref: object,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> tuple[int, ToolResultEnvelope] | None:
    for index, result in enumerate(tool_results, start=1):
        if result.status != "completed" or result.tool_name not in {
            "exec_command",
            "glob",
            "read_file",
            "run_command",
            "search_text",
        }:
            continue
        evidence_text = "\n".join(
            chunk
            for chunk in (
                str(result.provider_call_id or ""),
                result.tool_name,
                _tool_result_content_text(result),
            )
            if chunk
        )
        if implementation_source_ref_matches_text(source_ref, evidence_text):
            return index, result
    return None


def _structured_finish_acceptance_checks(tool_results: tuple[ToolResultEnvelope, ...]) -> list[dict[str, object]]:
    for index, result in reversed(tuple(enumerate(tool_results, start=1))):
        check = _structured_finish_acceptance_check(index, result)
        if check:
            return [check]
    return []


def _structured_finish_acceptance_check(index: int, result: ToolResultEnvelope) -> dict[str, object]:
    if result.status != "completed" or result.tool_name not in EXEC_TOOL_NAMES:
        return {}
    payload = next((item for item in result.content if isinstance(item, dict)), {})
    if not isinstance(payload, dict):
        return {}
    verifier = payload.get("verifier_evidence")
    if not isinstance(verifier, dict) or str(verifier.get("verdict") or "").casefold() != "pass":
        return {}
    contract = payload.get("execution_contract_normalized")
    if not isinstance(contract, dict):
        contract = payload.get("execution_contract")
    if not _structured_finish_contract_is_final_verifier(contract):
        return {}
    artifacts = payload.get("artifact_evidence")
    if not isinstance(artifacts, list):
        return {}
    artifact_ids: list[str] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").casefold() != "passed":
            continue
        artifact_id = str(item.get("artifact_id") or item.get("path") or "").strip()
        if not artifact_id or _is_verifier_scratch_artifact_id(artifact_id):
            continue
        if artifact_id not in artifact_ids:
            artifact_ids.append(artifact_id)
    if not artifact_ids:
        return {}
    evidence_text = _structured_finish_evidence_text(result, artifact_ids)
    return {
        "constraint": _structured_finish_constraint(artifact_ids),
        "status": "verified",
        "source": "structured_finish_sidecar",
        "evidence": evidence_text,
        "evidence_refs": [{"kind": "tool_call", "id": index}],
    }


def _structured_finish_contract_is_final_verifier(contract: object) -> bool:
    if not isinstance(contract, dict):
        return False
    proof_role = str(contract.get("proof_role") or "").casefold()
    acceptance_kind = str(contract.get("acceptance_kind") or "").casefold()
    stage = str(contract.get("stage") or "").casefold()
    purpose = str(contract.get("purpose") or "").casefold()
    role = str(contract.get("role") or "").casefold()
    if acceptance_kind not in {"external_verifier", "candidate_final_proof"}:
        return False
    if proof_role not in {"verifier", "final_artifact", "custom_runtime_smoke", "default_smoke"}:
        return False
    return (
        stage in {"verification", "artifact_proof", "custom_runtime_smoke", "default_smoke"}
        or purpose in {"verification", "artifact_proof", "smoke"}
        or role in {"verify", "runtime", "test"}
    )


def _is_verifier_scratch_artifact_id(value: str) -> bool:
    lowered = value.casefold()
    if not lowered.startswith("/tmp/"):
        return False
    if not lowered.endswith((".log", ".txt", ".out", ".stdout", ".stderr")):
        return False
    name = lowered.rsplit("/", 1)[-1]
    return any(token in name for token in ("log", "out", "stdout", "stderr", "trace", "transcript"))


def _structured_finish_constraint(artifact_ids: list[str]) -> str:
    if any(_artifact_id_is_visual_runtime_output(artifact) for artifact in artifact_ids):
        return "runtime visual artifact is correct"
    return "final verifier structured evidence passed"


def _artifact_id_is_visual_runtime_output(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in ("frame", "image", "screenshot", ".bmp", ".png", ".jpg", ".jpeg"))


def _structured_finish_evidence_text(result: ToolResultEnvelope, artifact_ids: list[str]) -> str:
    payload = next((item for item in result.content if isinstance(item, dict)), {})
    previews: list[str] = []
    if isinstance(payload, dict):
        for key in ("stdout_tail", "stdout", "stderr_tail", "stderr"):
            value = str(payload.get(key) or "")
            if not value:
                continue
            for marker in (
                "reference similarity",
                "similarity passed",
                "SSIM passed",
            ):
                if marker.casefold() in value.casefold() and marker not in previews:
                    previews.append(marker)
            for line in value.splitlines():
                lowered_line = line.casefold()
                if not re.search(r"\b\d{2,5}\s*(?:x|×|by)\s*\d{2,5}\b", line):
                    continue
                if not any(
                    token in lowered_line
                    for token in ("dimension", "dimensions", "resolution", "screen size", "framebuffer")
                ):
                    continue
                if any(
                    token in lowered_line
                    for token in ("actual", "different", "error", "failed", "mismatch", "not", "wrong")
                ):
                    continue
                if not any(
                    token in lowered_line for token in ("confirmed", "matches", "ok", "passed", "same", "verified")
                ):
                    continue
                preview = line.strip()
                if len(preview) > 120:
                    preview = preview[:117] + "..."
                if preview and preview not in previews:
                    previews.append(preview)
    artifacts = ", ".join(artifact_ids[:4])
    provider_call_id = str(result.provider_call_id or "").strip()
    pieces = [
        f"{provider_call_id or 'structured-final-verifier'} passed structured final verifier evidence",
        f"artifacts: {artifacts}",
    ]
    if previews:
        pieces.append("quality markers: " + ", ".join(previews[:4]))
    return "; ".join(pieces)


def _synthetic_finish_acceptance_checks(
    finish_arguments: dict[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> list[dict[str, object]]:
    evidence_items = finish_arguments.get("acceptance_evidence")
    if isinstance(evidence_items, str):
        items = [evidence_items]
    elif isinstance(evidence_items, (list, tuple)):
        items = list(evidence_items)
    else:
        items = []
    checks: list[dict[str, object]] = []
    for item in items[:8]:
        evidence = str(item or "").strip()
        if not evidence:
            continue
        check: dict[str, object] = {
            "constraint": _finish_constraint_from_evidence(evidence),
            "status": "verified",
            "evidence": evidence,
        }
        refs = _finish_evidence_refs(evidence, tool_results)
        if refs:
            check["evidence_refs"] = refs
        checks.append(check)
    return checks


def _with_finish_evidence_refs(
    check: dict[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, object]:
    enriched = dict(check)
    if enriched.get("evidence_refs") or enriched.get("evidence_ref"):
        return enriched
    evidence = "\n".join(str(enriched.get(key) or "") for key in ("constraint", "evidence", "proof"))
    refs = _finish_evidence_refs(evidence, tool_results)
    if refs:
        enriched["evidence_refs"] = refs
    return enriched


def _finish_constraint_from_evidence(evidence: str) -> str:
    lowered = evidence.casefold()
    if any(marker in lowered for marker in ("frame", "screenshot", "image", "render")):
        return "runtime visual artifact is correct"
    if any(marker in lowered for marker in ("stdout", "stderr", "exit_code", "command")):
        return "command behavior is verified"
    return "finish acceptance evidence"


def _finish_evidence_refs(
    evidence: str,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    provider_to_tool_id = {
        result.provider_call_id: index
        for index, result in enumerate(tool_results, start=1)
        if str(result.provider_call_id or "").strip()
    }
    for provider_call_id, tool_id in provider_to_tool_id.items():
        if _provider_call_id_mentioned(evidence, provider_call_id):
            ref = {"kind": "tool_call", "id": tool_id}
            if ref not in refs:
                refs.append(ref)
    for match in _EVIDENCE_PROVIDER_CALL_RE.finditer(evidence):
        provider_call_id = match.group(0)
        tool_id = provider_to_tool_id.get(provider_call_id)
        if tool_id is not None:
            ref = {"kind": "tool_call", "id": tool_id}
            if ref not in refs:
                refs.append(ref)
    for index, result in enumerate(tool_results, start=1):
        if any(str(ref or "") and str(ref or "") in evidence for ref in result.evidence_refs):
            ref = {"kind": "tool_call", "id": index}
            if ref not in refs:
                refs.append(ref)
    return refs


def _provider_call_id_mentioned(evidence: str, provider_call_id: object) -> bool:
    provider_id = str(provider_call_id or "").strip()
    if not provider_id:
        return False
    if len(provider_id) < 4:
        return False
    if provider_id.isalpha() or provider_id.isdigit():
        return False
    if not any(char.isalpha() for char in provider_id):
        return False
    if not any(char in "-_.:" for char in provider_id):
        return False
    for match in _PROVIDER_ID_TOKEN_RE.finditer(evidence):
        token = match.group(0)
        if token == provider_id:
            return True
        if token.rstrip(".,:;") == provider_id:
            return True
    return False


def _acceptance_session_from_tool_results(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    lane_input: ImplementLaneInput | None = None,
) -> dict[str, object]:
    session: dict[str, object] = {
        "tool_calls": [
            _acceptance_tool_call_from_result(index, result)
            for index, result in enumerate(tool_results, start=1)
        ]
    }
    typed_acceptance = _typed_acceptance_session_from_tool_results(tool_results, lane_input=lane_input)
    if typed_acceptance:
        session["typed_acceptance"] = typed_acceptance
    if lane_input is not None and isinstance(lane_input.task_contract, dict):
        compiler = lane_input.task_contract.get("task_contract_compiler")
        if isinstance(compiler, dict):
            session["task_contract_compiler"] = dict(compiler)
    return session


def _typed_acceptance_session_from_tool_results(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    lane_input: ImplementLaneInput | None = None,
) -> dict[str, object]:
    events = []
    execution_contracts: list[dict[str, object]] = []
    verifier_evidence: list[dict[str, object]] = []
    artifact_evidence: list[dict[str, object]] = []
    source_grounding_refs: list[dict[str, object]] = []
    for index, result in enumerate(tool_results, start=1):
        payload = _first_result_payload(result)
        if not payload:
            continue
        events.extend(
            event.as_dict()
            for event in evidence_events_from_tool_payload(
                tool_index=index,
                tool_name=result.tool_name,
                tool_status=result.status,
                provider_call_id=result.provider_call_id,
                payload=payload,
            )
        )
        contract = payload.get("execution_contract_normalized") or payload.get("execution_contract")
        if isinstance(contract, dict):
            execution_contracts.append(dict(contract))
        verifier = payload.get("verifier_evidence")
        if isinstance(verifier, dict):
            verifier_evidence.append(dict(verifier))
        artifacts = payload.get("artifact_evidence")
        if isinstance(artifacts, list):
            artifact_evidence.extend(dict(item) for item in artifacts if isinstance(item, dict))
    if lane_input is not None:
        task_description = _live_task_description(lane_input)
        for requirement in implementation_contract_source_requirements(task_description):
            if isinstance(requirement, dict):
                source_grounding_refs.append(dict(requirement))
                source_ref = str(requirement.get("path") or "").strip()
                match = _source_grounding_tool_result(source_ref, tool_results)
                if match is not None:
                    tool_index, result = match
                    events.append(
                        {
                            "schema_version": 1,
                            "id": f"ev:source:{source_ref}:{result.provider_call_id or tool_index}",
                            "kind": "source_grounding",
                            "status": "passed",
                            "observed": {"path": source_ref, "grounded": True},
                            "refs": [{"kind": "tool_call", "id": tool_index}],
                            "provider_call_id": result.provider_call_id,
                        }
                    )
    task_contract = lane_input.task_contract if lane_input is not None and isinstance(lane_input.task_contract, dict) else {}
    oracle_bundle = build_oracle_bundle(
        task_contract=task_contract,
        execution_contracts=execution_contracts,
        verifier_evidence=verifier_evidence,
        artifact_evidence=artifact_evidence,
        source_grounding_refs=source_grounding_refs,
    )
    if not events and oracle_bundle is None:
        return {}
    typed: dict[str, object] = {
        "evidence_events": events,
        "digest": _typed_acceptance_digest(events, oracle_bundle.as_dict() if oracle_bundle is not None else {}),
    }
    if oracle_bundle is not None:
        typed["oracle_bundle"] = oracle_bundle.as_dict()
        typed["retired_legacy_blockers"] = _typed_retired_legacy_blockers_for_bundle(
            oracle_bundle.as_dict(),
            task_description=_live_task_description(lane_input) if lane_input is not None else "",
        )
    return typed


def _typed_retired_legacy_blockers_for_bundle(
    oracle_bundle: dict[str, object],
    *,
    task_description: object = "",
) -> list[str]:
    obligations = oracle_bundle.get("obligations") if isinstance(oracle_bundle, dict) else []
    if not isinstance(obligations, list) or not obligations:
        return []
    kinds = {
        str(obligation.get("kind") or "")
        for obligation in obligations
        if isinstance(obligation, dict)
    }
    retired: set[str] = set()
    visual_quality_covered = "visual_similarity" in kinds
    artifact_covered = bool(kinds.intersection({"artifact_exists", "artifact_fresh"}))
    verifier_covered = _verifier_pass_obligation_is_component_behavior_cover(obligations)
    if verifier_covered:
        retired.add("runtime_component_behavior_evidence")
    if visual_quality_covered:
        retired.add("runtime_visual_artifact_quality_evidence")
    if artifact_covered and (visual_quality_covered or not is_runtime_visual_artifact_task(task_description)):
        retired.add("runtime_final_verifier_artifact_evidence")
    if "artifact_fresh" in kinds and (visual_quality_covered or not is_runtime_visual_artifact_task(task_description)):
        retired.add("runtime_artifact_freshness_unchecked")
    return sorted(retired)


def _verifier_pass_obligation_is_component_behavior_cover(obligations: object) -> bool:
    if not isinstance(obligations, list):
        return False
    for obligation in obligations:
        if not isinstance(obligation, dict):
            continue
        if str(obligation.get("kind") or "") != "verifier_pass":
            continue
        source = str(obligation.get("source") or "")
        subject = obligation.get("subject") if isinstance(obligation.get("subject"), dict) else {}
        verifier_id = str(subject.get("verifier_id") or "")
        contract_id = str(subject.get("contract_id") or "")
        if source in {"execution_contract", "verifier_evidence"} and (verifier_id or contract_id):
            return True
    return False


def _typed_acceptance_digest(events: list[dict[str, object]], oracle_bundle: dict[str, object]) -> dict[str, object]:
    obligations = oracle_bundle.get("obligations") if isinstance(oracle_bundle, dict) else []
    missing = []
    if isinstance(obligations, list):
        event_text = "\n".join(str(event.get("id") or "") + "\n" + str(event.get("observed") or {}) for event in events)
        for obligation in obligations:
            if not isinstance(obligation, dict):
                continue
            obligation_id = str(obligation.get("id") or "")
            subject = str(obligation.get("subject") or "")
            if obligation_id and (obligation_id not in event_text and subject not in event_text):
                missing.append(obligation_id)
    return {
        "typed_evidence_event_count": len(events),
        "oracle_obligation_count": len(obligations) if isinstance(obligations, list) else 0,
        "missing_obligations": missing[:12],
        "evidence": [
            {
                "id": event.get("id"),
                "kind": event.get("kind"),
                "status": event.get("status"),
                "obligation_id": event.get("obligation_id"),
            }
            for event in events[:12]
            if isinstance(event, dict)
        ],
    }


def _acceptance_tool_call_from_result(index: int, result: ToolResultEnvelope) -> dict[str, object]:
    content_items = [item for item in result.content if isinstance(item, dict)]
    primary = dict(content_items[0]) if content_items else {}
    command = str(primary.get("command") or "").strip()
    argv = primary.get("argv")
    if not command and isinstance(argv, list):
        command = " ".join(str(item) for item in argv)
    text = _tool_result_content_text(result)
    result_payload: dict[str, object] = {
        "text": text,
        "stdout": str(primary.get("stdout") or ""),
        "stderr": str(primary.get("stderr") or ""),
        "summary": text[:500],
        "output": text,
        "command": command,
    }
    if "exit_code" in primary:
        result_payload["exit_code"] = primary.get("exit_code")
    elif result.tool_name in EXEC_TOOL_NAMES:
        result_payload["exit_code"] = 0 if result.status == "completed" else 1
    if "timed_out" in primary:
        result_payload["timed_out"] = bool(primary.get("timed_out"))
    elif result.tool_name in EXEC_TOOL_NAMES:
        result_payload["timed_out"] = False
    for key in (
        "tool_name",
        "effective_tool_name",
        "command_run_id",
        "execution_contract",
        "execution_contract_normalized",
        "artifact_evidence",
        "verifier_evidence",
        "command_run",
        "tool_run_record",
    ):
        value = primary.get(key)
        if value:
            result_payload[key] = value
    parameters: dict[str, object] = {}
    if command:
        parameters["command"] = command
    if primary.get("cwd"):
        parameters["cwd"] = primary.get("cwd")
    contract = result_payload.get("execution_contract") or result_payload.get("execution_contract_normalized")
    if isinstance(contract, dict):
        parameters["execution_contract"] = dict(contract)
    if result_payload.get("effective_tool_name"):
        parameters["effective_tool_name"] = result_payload.get("effective_tool_name")
    if result_payload.get("command_run_id"):
        parameters["command_run_id"] = result_payload.get("command_run_id")
    return {
        "id": index,
        "tool": result.tool_name,
        "status": result.status,
        "parameters": parameters,
        "result": result_payload,
        "summary": text[:500],
    }


def _tool_result_content_text(result: ToolResultEnvelope) -> str:
    chunks: list[str] = []
    for item in result.content:
        if isinstance(item, dict):
            for key in ("command", "stdout", "stderr", "text", "summary", "output", "reason"):
                value = item.get(key)
                if value:
                    chunks.append(str(value))
            argv = item.get("argv")
            if isinstance(argv, list):
                chunks.append(" ".join(str(part) for part in argv))
        elif item:
            chunks.append(str(item))
    return "\n".join(chunks)


__all__ = [
    "_acceptance_session_from_tool_results",
    "_finish_acceptance_action",
    "_finish_outcome",
    "_first_result_payload",
    "_structured_finish_acceptance_check",
    "_typed_finish_evidence_refs",
    "_tool_result_content_text",
]
