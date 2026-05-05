from __future__ import annotations

import hashlib
import json
import re


SCHEMA_VERSION = 1
FINGERPRINT_VERSION = "active_compatibility_frontier_failure_signature_v1"
PRIMARY_TOKEN_CATEGORIES = (
    "error_tokens",
    "missing_symbol_tokens",
    "failing_test_tokens",
    "stack_anchor_tokens",
)
OPEN_CANDIDATE_STATUSES = {"unexplored", "read", "anchored", "edited"}
FRONTIER_BLOCKING_STATES = {"open", "search_needed", "read_needed", "edit_needed", "cheap_verify_needed"}
FRONTIER_BLOCKING_GUARD_MODES = {"block_broad", "block_finish"}
FRONTIER_CHEAP_CONTRACT_TERMS = {
    "cheap",
    "focused",
    "targeted",
    "narrow",
    "smoke",
    "behavior",
    "runtime_behavior",
    "repository_tail",
    "unit",
}
FRONTIER_BROAD_CONTRACT_TERMS = {
    "acceptance",
    "all",
    "broad",
    "build",
    "final",
    "full",
    "full_suite",
    "install",
    "rebuild",
    "suite",
    "task_verifier",
}
FRONTIER_DURABLE_EVIDENCE_REF_KINDS = {
    "command_evidence",
    "external_verifier",
    "result_artifact",
    "resume_key",
    "tool_call",
    "verifier_output",
}


def _clip_text(value, limit=160):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _dedupe(items):
    result = []
    seen = set()
    for item in items or []:
        text = str(item or "").strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _stable_token(value, *, lower=True):
    text = str(value or "").strip()
    text = text.replace("\\", "/")
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" \t\r\n\"'`.,:;")
    return text.casefold() if lower else text


def _normalize_path(value, *, cwd=""):
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    cwd = str(cwd or "").strip().replace("\\", "/")
    if cwd and text == cwd:
        return "<repo>"
    if cwd and text.startswith(f"{cwd}/"):
        text = f"<repo>/{text[len(cwd) + 1:]}"
    text = re.sub(r"/private/var/folders/[^ \t\r\n\"']+", "<tmp>", text)
    text = re.sub(r"/var/folders/[^ \t\r\n\"']+", "<tmp>", text)
    text = re.sub(r"/tmp/[^ \t\r\n\"']+", "<tmp>", text)
    text = re.sub(r"/(?:Users|home)/[^/]+/\.cache/[^ \t\r\n\"']+", "<cache>", text)
    return text


def _normalize_shape(value, *, cwd=""):
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    if cwd:
        cwd_text = str(cwd).strip().replace("\\", "/")
        text = text.replace(cwd_text, "<repo>")
    text = _normalize_path(text, cwd=cwd)
    text = re.sub(r"0x[0-9a-fA-F]+", "0x<hex>", text)
    text = re.sub(r"\b\d+(?:\.\d+)?s\b", "<duration>", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _canonical_hash(core):
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{FINGERPRINT_VERSION}\n{canonical}".encode("utf-8")).hexdigest()


def _short_id(prefix, core):
    return f"{prefix}-{_canonical_hash(core)[:12]}"


def _call_id(call):
    if not isinstance(call, dict):
        return None
    return call.get("id")


def _find_call(calls, tool_call_id):
    wanted = str(tool_call_id or "")
    if not wanted:
        return {}
    for call in calls or []:
        if isinstance(call, dict) and str(call.get("id") or "") == wanted:
            return call
    return {}


def _source_call_for_agenda(calls, agenda):
    return _find_call(calls, (agenda or {}).get("source_tool_call_id"))


def _exit_class(source_call, agenda):
    source_call = source_call if isinstance(source_call, dict) else {}
    result = source_call.get("result") if isinstance(source_call.get("result"), dict) else {}
    exit_code = (agenda or {}).get("exit_code")
    if exit_code is None:
        exit_code = result.get("exit_code")
    status = str(source_call.get("status") or "").casefold()
    error_text = str(source_call.get("error") or "").casefold()
    if "timeout" in status or "timeout" in error_text or "timed out" in error_text:
        return "timeout"
    if exit_code not in (None, "", 0, "0"):
        return "nonzero"
    if status in {"failed", "interrupted"}:
        return "tool_failed"
    return "tool_failed" if (agenda or {}).get("error_lines") else "unknown"


def _error_tokens(error_lines):
    tokens = []
    for line in error_lines or []:
        text = str(line or "")
        for token in re.findall(r"\b([A-Za-z_][\w.]*?(?:Error|Exception|Failure|Timeout|Fault))\b", text):
            tokens.append(token.rsplit(".", 1)[-1].casefold())
        lowered = text.casefold()
        for phrase, token in (
            ("segmentation fault", "segmentation_fault"),
            ("assertion failed", "assertion_failed"),
            ("command not found", "command_not_found"),
            ("permission denied", "permission_denied"),
        ):
            if phrase in lowered:
                tokens.append(token)
    return sorted(_dedupe(tokens))


def _missing_symbol_tokens(agenda):
    tokens = []
    for symbol in (agenda or {}).get("symbols") or []:
        token = _stable_token(symbol, lower=False)
        if token:
            tokens.append(token)
    for line in (agenda or {}).get("error_lines") or []:
        text = str(line or "")
        for pattern in (
            r"has no attribute ['\"]([^'\"]+)['\"]",
            r"cannot import name ['\"]([^'\"]+)['\"]",
            r"No module named ['\"]([^'\"]+)['\"]",
            r"undefined symbol:?\s+([A-Za-z_][\w.]*)",
            r"unresolved symbol:?\s+([A-Za-z_][\w.]*)",
        ):
            for match in re.findall(pattern, text):
                token = _stable_token(match, lower=False)
                if token:
                    tokens.append(token)
    return sorted(_dedupe(tokens), key=lambda item: item.casefold())


def _normalize_test_token(value):
    text = str(value or "").strip().replace("\\", "/")
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = text.rstrip(":.,")
    return text


def _failing_test_tokens(error_lines):
    tokens = []
    for line in error_lines or []:
        text = str(line or "")
        for match in re.findall(r"\b(?:FAILED|ERROR)\s+([^\s]+)", text):
            token = _normalize_test_token(match)
            if token:
                tokens.append(token)
        for match in re.findall(r"((?:tests?/|[^:\s]+/tests?/)[^:\s]*\.py(?:::[A-Za-z_][\w.\-]*)?)", text):
            token = _normalize_test_token(match)
            if token:
                tokens.append(token)
        for match in re.findall(r"\b([^:\s]+test[^:\s]*\.py):\d+\b", text):
            token = _normalize_test_token(match)
            if token:
                tokens.append(token)
    return sorted(_dedupe(tokens), key=lambda item: item.casefold())


def _stack_anchor_tokens(source_locations, *, cwd=""):
    tokens = []
    for location in source_locations or []:
        if not isinstance(location, dict):
            continue
        path = _normalize_path(location.get("path") or "", cwd=cwd)
        if path:
            tokens.append(path)
    return sorted(_dedupe(tokens), key=lambda item: item.casefold())


def _runtime_component_kind(agenda, error_lines, command_shape):
    runtime_gap = (agenda or {}).get("runtime_contract_gap")
    if isinstance(runtime_gap, dict) and runtime_gap:
        gap_kind = str(runtime_gap.get("kind") or "").casefold()
        if any(token in gap_kind for token in ("opcode", "instruction", "program", "syscall", "register")):
            return "custom_runtime"
        return "custom_runtime"
    text = "\n".join(str(line or "") for line in error_lines or [])
    combined = f"{text}\n{command_shape}".casefold()
    if any(token in combined for token in ("dlopen", "ctypes", "cffi", "ffi.load")):
        return "shared_library"
    if re.search(r"\.(so|pyd|dylib|dll)\b", combined):
        if any(token in combined for token in ("import", "initialization", "module")):
            return "native_module"
        return "shared_library"
    if any(token in combined for token in ("plugin", "entrypoint", "entry point")):
        return "plugin"
    if any(token in combined for token in ("exec format", "permission denied", "command not found", "spawn", "shebang")):
        return "executable"
    if any(token in combined for token in ("opcode", "program counter", "pc=", "pc=0x", "register", "frame artifact")):
        return "custom_runtime"
    return "unknown"


def _platform_tokens(error_lines, command_shape):
    text = f"{command_shape}\n" + "\n".join(str(line or "") for line in error_lines or [])
    tokens = []
    for major, minor in re.findall(r"\bpython(?:\s|-)?([23])\.(\d+)\b", text, flags=re.IGNORECASE):
        tokens.append(f"python-{major}.{minor}")
    lowered = text.casefold()
    for token in ("linux", "darwin", "windows", "macos"):
        if token in lowered:
            tokens.append("darwin" if token == "macos" else token)
    return sorted(_dedupe(tokens))


def _execution_contract(source_call):
    source_call = source_call if isinstance(source_call, dict) else {}
    parameters = source_call.get("parameters") if isinstance(source_call.get("parameters"), dict) else {}
    contract = parameters.get("execution_contract") if isinstance(parameters.get("execution_contract"), dict) else {}
    return {
        key: _stable_token(contract.get(key))
        for key in ("purpose", "stage", "proof_role", "acceptance_kind", "risk_class")
        if str(contract.get(key) or "").strip()
    }


def _command_evidence_ref(source_call):
    source_call = source_call if isinstance(source_call, dict) else {}
    ref = source_call.get("command_evidence_ref")
    if not isinstance(ref, dict) or not ref:
        return {}
    result = {}
    for key in ("kind", "id", "path", "command_run_id"):
        if ref.get(key) not in (None, "", [], {}):
            result[key] = ref.get(key)
    if not result:
        result = {"kind": "command_evidence"}
    result.setdefault("kind", "command_evidence")
    return result


def build_failure_signature(verifier_failure_repair_agenda, source_call=None):
    agenda = verifier_failure_repair_agenda if isinstance(verifier_failure_repair_agenda, dict) else {}
    if not agenda:
        return {}
    source_call = source_call if isinstance(source_call, dict) else {}
    result = source_call.get("result") if isinstance(source_call.get("result"), dict) else {}
    parameters = source_call.get("parameters") if isinstance(source_call.get("parameters"), dict) else {}
    command = agenda.get("command") or result.get("command") or parameters.get("command") or ""
    cwd = agenda.get("cwd") or result.get("cwd") or parameters.get("cwd") or ""
    command_shape = _normalize_shape(command, cwd=cwd)
    cwd_shape = "<repo>" if cwd and _normalize_path(cwd, cwd=cwd) == "<repo>" else _normalize_path(cwd, cwd=cwd)
    error_lines = list(agenda.get("error_lines") or [])
    runtime_component_kind = _runtime_component_kind(agenda, error_lines, command_shape)
    kind = "runtime_failure" if runtime_component_kind != "unknown" else "verifier_failure"
    token_categories = {
        "error_tokens": _error_tokens(error_lines),
        "missing_symbol_tokens": _missing_symbol_tokens(agenda),
        "failing_test_tokens": _failing_test_tokens(error_lines),
        "stack_anchor_tokens": _stack_anchor_tokens(agenda.get("source_locations") or [], cwd=cwd),
        "component_tokens": [] if runtime_component_kind == "unknown" else [runtime_component_kind],
        "platform_tokens": _platform_tokens(error_lines, command_shape),
    }
    execution_contract = _execution_contract(source_call)
    exit_class = _exit_class(source_call, agenda)
    strict_core = {
        "schema_version": SCHEMA_VERSION,
        "fingerprint_version": FINGERPRINT_VERSION,
        "kind": kind,
        "tool": _stable_token(agenda.get("tool") or source_call.get("tool") or ""),
        "command_shape": command_shape,
        "cwd_shape": cwd_shape,
        "execution_contract": execution_contract,
        "exit_class": exit_class,
        "error_tokens": token_categories["error_tokens"],
        "missing_symbol_tokens": token_categories["missing_symbol_tokens"],
        "failing_test_tokens": token_categories["failing_test_tokens"],
        "stack_anchor_tokens": token_categories["stack_anchor_tokens"][:3],
        "runtime_component_kind": runtime_component_kind,
        "platform_facts": token_categories["platform_tokens"],
    }
    family_core = {
        "kind": kind,
        "stage": execution_contract.get("stage") or "",
        "proof_role": execution_contract.get("proof_role") or "",
        "error_tokens": token_categories["error_tokens"],
        "missing_symbol_tokens": token_categories["missing_symbol_tokens"],
        "failing_test_tokens": token_categories["failing_test_tokens"],
        "runtime_component_kind": runtime_component_kind,
        "first_stable_stack_anchor": (token_categories["stack_anchor_tokens"] or [""])[0],
    }
    command_ref = _command_evidence_ref(source_call)
    return {
        "schema_version": SCHEMA_VERSION,
        "fingerprint_version": FINGERPRINT_VERSION,
        "kind": kind,
        "fingerprint": _canonical_hash(strict_core),
        "family_key": _canonical_hash(family_core),
        "source_tool_call_id": agenda.get("source_tool_call_id") or source_call.get("id"),
        "command_evidence_ref": command_ref,
        "tool": agenda.get("tool") or source_call.get("tool") or "",
        "command_shape": command_shape,
        "cwd_shape": cwd_shape,
        "execution_contract": execution_contract,
        "exit_class": exit_class,
        "error_fingerprint": "|".join(
            token_categories["error_tokens"]
            + token_categories["missing_symbol_tokens"]
            + token_categories["failing_test_tokens"][:3]
            + token_categories["stack_anchor_tokens"][:3]
        ),
        "failing_tests": token_categories["failing_test_tokens"],
        "runtime_component_kind": runtime_component_kind,
        "platform_facts": token_categories["platform_tokens"],
        "token_categories": token_categories,
    }


def _evidence_refs(agenda, source_call, search_anchor_observations):
    refs = []
    command_ref = _command_evidence_ref(source_call)
    if command_ref:
        ref = dict(command_ref)
        ref["summary"] = "command evidence for compatibility frontier failure"
        refs.append(ref)
    source_id = (agenda or {}).get("source_tool_call_id") or _call_id(source_call)
    if source_id not in (None, ""):
        refs.append(
            {
                "kind": "tool_call",
                "id": source_id,
                "summary": (
                    f"{(agenda or {}).get('tool') or (source_call or {}).get('tool') or 'tool'} "
                    f"exit={(agenda or {}).get('exit_code')}"
                ),
            }
        )
    if agenda:
        refs.append(
            {
                "kind": "resume_key",
                "key": "verifier_failure_repair_agenda",
                "summary": "normalized verifier failure agenda",
            }
        )
    for observation in search_anchor_observations or []:
        if not isinstance(observation, dict) or observation.get("tool_call_id") in (None, ""):
            continue
        refs.append(
            {
                "kind": "tool_call",
                "id": observation.get("tool_call_id"),
                "summary": f"successful search anchor for {observation.get('path') or observation.get('query') or 'candidate'}",
            }
        )
    return _merge_dicts_by_identity([], refs, limit=20)


def _line_number(value):
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _anchor(kind, *, subject="", path="", line=None, query="", source_event=None, read_status="unread", evidence_refs=None):
    source_event = source_event if isinstance(source_event, dict) else {}
    anchor = {
        "id": _short_id("anchor", {"kind": kind, "subject": subject, "path": path, "line": line, "query": query}),
        "kind": kind,
        "subject": subject,
        "path": path,
        "line": line,
        "query": query,
        "source_event": source_event,
        "read_status": read_status,
        "evidence_refs": list(evidence_refs or [])[:5],
    }
    return {key: value for key, value in anchor.items() if value not in (None, "", [], {})}


def _build_anchors(agenda, signature, search_anchor_observations, evidence_refs, *, cwd=""):
    anchors = []
    source_event = {"kind": "tool_call", "id": (agenda or {}).get("source_tool_call_id")}
    for location in (agenda or {}).get("source_locations") or []:
        if not isinstance(location, dict):
            continue
        path = _normalize_path(location.get("path") or "", cwd=cwd)
        if not path:
            continue
        line = _line_number(location.get("line"))
        subject = f"{path}:{line}" if line else path
        anchors.append(
            _anchor(
                "source_location",
                subject=subject,
                path=path,
                line=line,
                source_event=source_event,
                evidence_refs=evidence_refs,
            )
        )
    for test_name in (signature or {}).get("failing_tests") or []:
        anchors.append(
            _anchor(
                "test_name",
                subject=test_name,
                source_event=source_event,
                read_status="not_needed",
                evidence_refs=evidence_refs,
            )
        )
    for query in (agenda or {}).get("sibling_search_queries") or []:
        query_text = _clip_text(query, 160)
        if query_text:
            anchors.append(
                _anchor(
                    "search_query",
                    subject=query_text,
                    query=query_text,
                    source_event=source_event,
                    evidence_refs=evidence_refs,
                )
            )
    for observation in search_anchor_observations or []:
        if not isinstance(observation, dict):
            continue
        path = _normalize_path(observation.get("path") or "")
        line = _line_number(observation.get("first_match_line"))
        query = _clip_text(observation.get("query") or observation.get("pattern") or "", 160)
        subject = f"{path}:{line}" if path and line else path or query
        anchors.append(
            _anchor(
                "search_match",
                subject=subject,
                path=path,
                line=line,
                query=query,
                source_event={"kind": "tool_call", "id": observation.get("tool_call_id")},
                evidence_refs=evidence_refs,
            )
        )
    return _merge_dicts_by_identity([], anchors, id_key="id", limit=30)


def _candidate(kind, *, subject="", path="", anchors=None, reason="", status="unexplored", evidence_refs=None):
    candidate = {
        "id": _short_id("candidate", {"kind": kind, "subject": subject, "path": path}),
        "kind": kind,
        "subject": subject,
        "path": path,
        "anchors": list(anchors or [])[:10],
        "reason": _clip_text(reason, 240),
        "status": status,
        "rejection_reason": "",
        "evidence_refs": list(evidence_refs or [])[:5],
    }
    return {key: value for key, value in candidate.items() if value not in (None, "", [], {})}


def _build_candidates(agenda, signature, anchors, evidence_refs):
    candidates = []
    anchors_by_path = {}
    anchors_by_subject = {}
    for anchor in anchors or []:
        path = anchor.get("path")
        subject = anchor.get("subject")
        if path:
            anchors_by_path.setdefault(path, []).append(anchor.get("id"))
        if subject:
            anchors_by_subject.setdefault(subject, []).append(anchor.get("id"))
    for path, anchor_ids in anchors_by_path.items():
        candidates.append(
            _candidate(
                "file",
                subject=path,
                path=path,
                anchors=anchor_ids,
                reason="verifier or search evidence names this source surface",
                status="anchored",
                evidence_refs=evidence_refs,
            )
        )
    for test_name in (signature or {}).get("failing_tests") or []:
        candidates.append(
            _candidate(
                "test",
                subject=test_name,
                anchors=anchors_by_subject.get(test_name) or [],
                reason="verifier output identifies this failing test or check",
                status="anchored",
                evidence_refs=evidence_refs,
            )
        )
    for symbol in (agenda or {}).get("symbols") or []:
        subject = _stable_token(symbol, lower=False)
        if not subject:
            continue
        candidates.append(
            _candidate(
                "symbol",
                subject=subject,
                anchors=[],
                reason="verifier output names a missing or incompatible symbol",
                status="unexplored",
                evidence_refs=evidence_refs,
            )
        )
    runtime_kind = (signature or {}).get("runtime_component_kind") or "unknown"
    if runtime_kind != "unknown":
        candidates.append(
            _candidate(
                "runtime_entrypoint",
                subject=runtime_kind,
                anchors=[],
                reason="positive runtime-component evidence is present in the verifier failure",
                status="unexplored",
                evidence_refs=evidence_refs,
            )
        )
    return _merge_dicts_by_identity([], candidates, id_key="id", limit=30)


def _open_candidates(candidates):
    return [item for item in candidates or [] if str(item.get("status") or "") in OPEN_CANDIDATE_STATUSES]


def _closure_state(anchors, candidates, signature):
    unread_anchors = [
        item
        for item in anchors or []
        if item.get("read_status") == "unread" and item.get("kind") in {"source_location", "search_match"}
    ]
    search_queries = [item for item in anchors or [] if item.get("kind") == "search_query"]
    open_candidates = _open_candidates(candidates)
    runtime_kind = (signature or {}).get("runtime_component_kind") or "unknown"
    verifier_obligations = []
    if runtime_kind != "unknown":
        verifier_obligations.append("invoke behavior through original runtime context")
    if unread_anchors:
        state = "read_needed"
        next_action = f"read_file {unread_anchors[0].get('path')}:{unread_anchors[0].get('line') or 1}"
    elif search_queries:
        state = "search_needed"
        next_action = f"search_text {search_queries[0].get('query')}"
    elif open_candidates:
        state = "edit_needed"
        next_action = "repair the open same-family sibling candidates"
    else:
        state = "cheap_verify_needed"
        next_action = "run the cheapest verifier that exercises this failure family"
    has_signature = bool((signature or {}).get("fingerprint"))
    evidence_strength = "none"
    if has_signature:
        evidence_strength = "actionable"
    broad_blocker = bool(unread_anchors or search_queries or open_candidates)
    finish_blocker = bool(verifier_obligations or broad_blocker)
    if finish_blocker:
        evidence_strength = "blocking"
    blocked_actions = []
    if broad_blocker or finish_blocker:
        blocked_actions.append("broad_verifier")
    if finish_blocker:
        blocked_actions.append("finish")
    if unread_anchors or search_queries:
        blocked_actions.append("repeat_search")
    guard_mode = "observe_only"
    if evidence_strength == "actionable":
        guard_mode = "prompt_nudge"
    if "broad_verifier" in blocked_actions:
        guard_mode = "block_broad"
    if "finish" in blocked_actions:
        guard_mode = "block_finish"
    return {
        "state": state,
        "reason": "same-family compatibility frontier has open evidence obligations",
        "evidence_strength": evidence_strength,
        "guard_mode": guard_mode,
        "open_candidate_count": len(open_candidates),
        "unread_anchor_count": len(unread_anchors),
        "unverified_patch_batch_count": 0,
        "verifier_obligations": verifier_obligations,
        "blocked_action_kinds": blocked_actions,
        "blocked_action_fingerprints": [],
        "broad_verifier_allowed": "broad_verifier" not in blocked_actions
        and state in {"broad_verify_ready", "closed", "deferred"},
        "finish_allowed": "finish" not in blocked_actions and state in {"closed", "deferred"} and not verifier_obligations,
        "next_action": _clip_text(next_action, 220),
    }


def _hypotheses(candidates, closure_state, current_time):
    open_candidate_ids = [item.get("id") for item in _open_candidates(candidates)]
    required_next_action = {
        "search_needed": "search",
        "read_needed": "read",
        "edit_needed": "edit",
        "cheap_verify_needed": "cheap_verify",
        "broad_verify_ready": "broad_verify",
        "closed": "finish",
        "deferred": "defer",
    }.get((closure_state or {}).get("state"), "search")
    return [
        {
            "id": _short_id("hypothesis", {"candidate_ids": open_candidate_ids, "action": required_next_action}),
            "summary": "same-family compatibility repair remains open in visible siblings",
            "status": "open",
            "candidate_ids": open_candidate_ids[:10],
            "expected_effect": "cheap verifier changes or clears the failure signature",
            "required_next_action": required_next_action,
            "blocking_evidence_refs": [],
            "updated_at": current_time,
        }
    ]


def _verifier_history_entry(signature, agenda, source_call, transition):
    source_call = source_call if isinstance(source_call, dict) else {}
    exit_code = (agenda or {}).get("exit_code")
    if exit_code is None:
        result = source_call.get("result") if isinstance(source_call.get("result"), dict) else {}
        exit_code = result.get("exit_code")
    command_ref = (signature or {}).get("command_evidence_ref") or {}
    scope = "broad"
    contract = (signature or {}).get("execution_contract") or {}
    if contract.get("proof_role") in {"targeted", "cheap", "behavior"} or contract.get("stage") in {"targeted", "behavior"}:
        scope = "targeted"
    return {
        "id": _short_id(
            "verifier",
            {
                "tool_call_id": (agenda or {}).get("source_tool_call_id") or source_call.get("id"),
                "signature": (signature or {}).get("fingerprint"),
            },
        ),
        "kind": "targeted_test" if scope == "targeted" else "broad_build",
        "scope": scope,
        "command_evidence_ref": command_ref,
        "tool_call_id": (agenda or {}).get("source_tool_call_id") or source_call.get("id"),
        "exit_code": exit_code,
        "signature_fingerprint": (signature or {}).get("fingerprint") or "",
        "family_changed": transition not in {"same", "narrower"},
        "closed_candidate_ids": [],
        "opened_candidate_ids": [],
        "notes": f"{(signature or {}).get('kind') or 'failure'} observed; transition={transition}",
    }


def _dict_identity(item, id_key="id"):
    if not isinstance(item, dict):
        return str(item)
    if item.get(id_key) not in (None, ""):
        return f"{id_key}:{item.get(id_key)}"
    stable = {key: value for key, value in item.items() if key not in {"summary", "notes", "updated_at"}}
    return json.dumps(stable, sort_keys=True, default=str)


def _merge_dicts_by_identity(existing, incoming, *, id_key="id", limit=50):
    merged = []
    seen = set()
    for item in list(existing or []) + list(incoming or []):
        if not isinstance(item, dict):
            continue
        identity = _dict_identity(item, id_key=id_key)
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(dict(item))
    return merged[-limit:]


def category_overlap(new_signature, previous_signature):
    new_categories = (new_signature or {}).get("token_categories") or {}
    previous_categories = (previous_signature or {}).get("token_categories") or {}
    overlap_categories = []
    contradiction_categories = []
    narrowed_categories = []
    for category in PRIMARY_TOKEN_CATEGORIES:
        new_tokens = set(new_categories.get(category) or [])
        previous_tokens = set(previous_categories.get(category) or [])
        if not new_tokens or not previous_tokens:
            continue
        if new_tokens & previous_tokens:
            overlap_categories.append(category)
            if len(new_tokens) < len(previous_tokens):
                narrowed_categories.append(category)
        else:
            contradiction_categories.append(category)
    primary_overlap = bool(overlap_categories)
    execution_new = (new_signature or {}).get("execution_contract") or {}
    execution_previous = (previous_signature or {}).get("execution_contract") or {}
    command_stage_moved = any(
        execution_new.get(key)
        and execution_previous.get(key)
        and execution_new.get(key) != execution_previous.get(key)
        for key in ("stage", "proof_role")
    )
    new_stack = set(new_categories.get("stack_anchor_tokens") or [])
    previous_stack = set(previous_categories.get("stack_anchor_tokens") or [])
    stack_moved = bool(new_stack and previous_stack and not (new_stack & previous_stack))
    behavior_surface_moved = bool(
        (new_signature or {}).get("command_shape")
        and (previous_signature or {}).get("command_shape")
        and (new_signature or {}).get("command_shape") != (previous_signature or {}).get("command_shape")
    )
    return {
        "primary_overlap": primary_overlap,
        "overlap_categories": overlap_categories,
        "contradiction_categories": contradiction_categories,
        "narrowed_categories": narrowed_categories,
        "narrower": primary_overlap and not contradiction_categories and bool(narrowed_categories),
        "moved": primary_overlap and (stack_moved or command_stage_moved or behavior_surface_moved),
    }


def family_transition(new_signature, previous_frontier):
    previous_signature = (previous_frontier or {}).get("failure_signature") if isinstance(previous_frontier, dict) else {}
    if not previous_signature:
        return "new", category_overlap(new_signature, {})
    overlap = category_overlap(new_signature, previous_signature)
    if (new_signature or {}).get("family_key") and (new_signature or {}).get("family_key") == previous_signature.get("family_key"):
        if overlap.get("primary_overlap") or (
            (new_signature or {}).get("fingerprint")
            and (new_signature or {}).get("fingerprint") == previous_signature.get("fingerprint")
        ):
            return "same", overlap
        return "new", overlap
    if overlap.get("narrower"):
        return "narrower", overlap
    if overlap.get("moved"):
        return "moved", overlap
    return "new", overlap


def _next_frontier_id(session):
    session = session if isinstance(session, dict) else {}
    try:
        ordinal = int(session.get("active_compatibility_frontier_ordinal") or 0) + 1
    except (TypeError, ValueError):
        ordinal = 1
    session["active_compatibility_frontier_ordinal"] = ordinal
    session_id = session.get("id") or "session"
    return f"compat-frontier-{session_id}-{ordinal}"


def _compact_summary(frontier):
    signature = (frontier or {}).get("failure_signature") or {}
    closure = (frontier or {}).get("closure_state") or {}
    open_candidates = [item.get("id") for item in _open_candidates((frontier or {}).get("sibling_candidates") or [])]
    one_line = (
        f"{signature.get('kind') or 'compatibility'} frontier; "
        f"{len(open_candidates)} sibling candidates open"
    )
    return {
        "one_line": one_line,
        "failure_signature": signature.get("fingerprint") or "",
        "evidence_refs": list((frontier or {}).get("evidence_refs") or [])[:8],
        "open_candidates": open_candidates[:8],
        "next_action": closure.get("next_action") or "",
        "guard_mode": closure.get("guard_mode") or "observe_only",
        "blocked_action_kinds": list(closure.get("blocked_action_kinds") or []),
    }


def _limited_dict_list(items, *, limit=8):
    return [dict(item) for item in items or [] if isinstance(item, dict)][:limit]


def _project_failure_signature(signature):
    signature = signature if isinstance(signature, dict) else {}
    if not signature:
        return {}
    projected = {
        key: signature.get(key)
        for key in (
            "schema_version",
            "fingerprint_version",
            "kind",
            "fingerprint",
            "family_key",
            "source_tool_call_id",
            "command_evidence_ref",
            "tool",
            "command_shape",
            "cwd_shape",
            "execution_contract",
            "exit_class",
            "error_fingerprint",
            "failing_tests",
            "runtime_component_kind",
            "platform_facts",
        )
        if signature.get(key) not in (None, "", [], {})
    }
    token_categories = signature.get("token_categories")
    if isinstance(token_categories, dict):
        projected["token_categories"] = {
            key: list(value or [])[:8]
            for key, value in token_categories.items()
            if value not in (None, "", [], {})
        }
    return projected


def _project_anchor(anchor):
    anchor = anchor if isinstance(anchor, dict) else {}
    projected = {
        key: anchor.get(key)
        for key in ("id", "kind", "subject", "path", "line", "query", "source_event", "read_status")
        if anchor.get(key) not in (None, "", [], {})
    }
    if anchor.get("evidence_refs"):
        projected["evidence_refs"] = _limited_dict_list(anchor.get("evidence_refs"), limit=4)
    return projected


def _project_candidate(candidate):
    candidate = candidate if isinstance(candidate, dict) else {}
    projected = {
        key: candidate.get(key)
        for key in ("id", "kind", "subject", "path", "anchors", "reason", "status", "rejection_reason")
        if candidate.get(key) not in (None, "", [], {})
    }
    if candidate.get("evidence_refs"):
        projected["evidence_refs"] = _limited_dict_list(candidate.get("evidence_refs"), limit=4)
    return projected


def _project_closure_state(closure_state):
    closure_state = closure_state if isinstance(closure_state, dict) else {}
    if not closure_state:
        return {}
    return {
        key: closure_state.get(key)
        for key in (
            "state",
            "reason",
            "evidence_strength",
            "guard_mode",
            "open_candidate_count",
            "unread_anchor_count",
            "unverified_patch_batch_count",
            "verifier_obligations",
            "blocked_action_kinds",
            "blocked_action_fingerprints",
            "broad_verifier_allowed",
            "finish_allowed",
            "next_action",
        )
        if closure_state.get(key) not in (None, "", [], {})
    }


def project_active_compatibility_frontier(frontier, *, anchor_limit=10, candidate_limit=10, history_limit=4):
    frontier = frontier if isinstance(frontier, dict) else {}
    if not frontier:
        return {}
    candidate_source = frontier.get("sibling_candidates") or frontier.get("open_candidates") or []
    candidates = [
        _project_candidate(candidate)
        for candidate in candidate_source
        if isinstance(candidate, dict)
        and (not candidate.get("status") or str(candidate.get("status") or "") in OPEN_CANDIDATE_STATUSES)
    ]
    projected = {
        "schema_version": frontier.get("schema_version"),
        "id": frontier.get("id"),
        "status": frontier.get("status"),
        "created_at": frontier.get("created_at"),
        "updated_at": frontier.get("updated_at"),
        "failure_signature": _project_failure_signature(frontier.get("failure_signature")),
        "family_transition": frontier.get("family_transition") if isinstance(frontier.get("family_transition"), dict) else {},
        "evidence_refs": _limited_dict_list(frontier.get("evidence_refs"), limit=12),
        "anchors": [
            _project_anchor(anchor)
            for anchor in (frontier.get("anchors") or [])[:anchor_limit]
            if isinstance(anchor, dict)
        ],
        "open_candidates": candidates[:candidate_limit],
        "closure_state": _project_closure_state(frontier.get("closure_state")),
        "compact_summary": frontier.get("compact_summary") if isinstance(frontier.get("compact_summary"), dict) else {},
        "verifier_history": _limited_dict_list(
            (frontier.get("verifier_history") or [])[-history_limit:] if history_limit > 0 else [],
            limit=history_limit,
        ),
    }
    return {key: value for key, value in projected.items() if value not in (None, "", [], {})}


def _frontier_signature(frontier):
    signature = (frontier or {}).get("failure_signature")
    return signature if isinstance(signature, dict) else {}


def _frontier_closure(frontier):
    closure = (frontier or {}).get("closure_state")
    return closure if isinstance(closure, dict) else {}


def _frontier_candidates(frontier):
    frontier = frontier if isinstance(frontier, dict) else {}
    candidates = frontier.get("open_candidates")
    if isinstance(candidates, list):
        return [item for item in candidates if isinstance(item, dict)]
    return _open_candidates(frontier.get("sibling_candidates") or [])


def _frontier_guard_path(value):
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    if text.startswith("./"):
        text = text[2:]
    if text.startswith("<repo>/"):
        text = text[len("<repo>/") :]
    return text.strip("/")


def _frontier_guard_paths_match(left, right):
    left = _frontier_guard_path(left)
    right = _frontier_guard_path(right)
    if not left or not right:
        return False
    if left == right:
        return True
    return left.endswith(f"/{right}") or right.endswith(f"/{left}")


def _frontier_anchor_paths(frontier):
    paths = []
    for anchor in (frontier or {}).get("anchors") or []:
        if not isinstance(anchor, dict):
            continue
        path = _frontier_guard_path(anchor.get("path"))
        if path:
            paths.append(path)
    return _dedupe(paths)


def _frontier_candidate_paths(frontier):
    paths = []
    for candidate in _frontier_candidates(frontier):
        path = _frontier_guard_path(candidate.get("path"))
        if path:
            paths.append(path)
        for anchor in candidate.get("anchors") or []:
            if isinstance(anchor, dict):
                anchor_path = _frontier_guard_path(anchor.get("path"))
                if anchor_path:
                    paths.append(anchor_path)
    return _dedupe(paths)


def _frontier_required_edit_paths(frontier):
    required = []
    for candidate in _frontier_candidates(frontier):
        status = str(candidate.get("status") or "unexplored").strip()
        if status in {"verified", "rejected", "deferred"}:
            continue
        path = _frontier_guard_path(candidate.get("path"))
        if path:
            required.append(path)
    return _dedupe(required)


def _action_command(action):
    action = action if isinstance(action, dict) else {}
    return str(action.get("command") or "").strip()


def _execution_contract_terms(action):
    action = action if isinstance(action, dict) else {}
    contract = action.get("execution_contract") if isinstance(action.get("execution_contract"), dict) else {}
    terms = []
    for key in ("purpose", "stage", "proof_role", "acceptance_kind"):
        value = contract.get(key)
        if isinstance(value, str) and value.strip():
            terms.extend(re.findall(r"[a-zA-Z0-9_]+", value.casefold()))
        elif isinstance(value, list):
            for item in value:
                terms.extend(re.findall(r"[a-zA-Z0-9_]+", str(item).casefold()))
    return set(terms)


def _command_mentions_frontier_target(command, frontier):
    command = str(command or "").casefold()
    if not command:
        return False
    signature = _frontier_signature(frontier)
    targets = []
    targets.extend(str(item or "") for item in signature.get("failing_tests") or [])
    targets.extend(_frontier_anchor_paths(frontier))
    targets.extend(_frontier_candidate_paths(frontier))
    for target in targets:
        target_text = str(target or "").strip().replace("\\", "/")
        if target_text and target_text.casefold() in command:
            return True
    return False


def _command_looks_broad_verifier(command):
    command = str(command or "").casefold()
    if not command:
        return False
    broad_patterns = (
        r"\b(pytest|unittest|tox|nox)\b",
        r"\b(cargo|go|npm|pnpm|yarn|mvn|gradle)\s+test\b",
        r"\b(make|ninja|cmake|meson|bazel)\b",
        r"\b(build|rebuild|install|full[-_ ]?suite|acceptance)\b",
    )
    return any(re.search(pattern, command) for pattern in broad_patterns)


def _frontier_action_is_cheap_verifier(action, frontier):
    action = action if isinstance(action, dict) else {}
    action_type = str(action.get("type") or action.get("tool") or "").strip()
    if action_type not in {"run_command", "run_tests"}:
        return False
    terms = _execution_contract_terms(action)
    if terms & FRONTIER_CHEAP_CONTRACT_TERMS:
        return True
    if terms & FRONTIER_BROAD_CONTRACT_TERMS:
        return False
    return _command_mentions_frontier_target(_action_command(action), frontier)


def _frontier_action_is_broad_verifier(action, frontier):
    action = action if isinstance(action, dict) else {}
    action_type = str(action.get("type") or action.get("tool") or "").strip()
    if action_type == "batch":
        return any(_frontier_action_is_broad_verifier(tool, frontier) for tool in action.get("tools") or [])
    if action_type not in {"run_command", "run_tests"}:
        return False
    if _frontier_action_is_cheap_verifier(action, frontier):
        return False
    terms = _execution_contract_terms(action)
    if terms & FRONTIER_BROAD_CONTRACT_TERMS:
        return True
    if action_type == "run_tests":
        return True
    return _command_looks_broad_verifier(_action_command(action))


def _frontier_action_is_finish_like(action):
    action = action if isinstance(action, dict) else {}
    action_type = str(action.get("type") or action.get("tool") or "").strip()
    if action_type == "finish":
        return True
    return action_type == "send_message" and bool(action.get("task_done"))


def _frontier_action_repeats_search(action, frontier):
    action = action if isinstance(action, dict) else {}
    if str(action.get("type") or action.get("tool") or "").strip() != "search_text":
        return False
    closure = _frontier_closure(frontier)
    blocked_fingerprints = {
        str(item or "").strip()
        for item in closure.get("blocked_action_fingerprints") or []
        if str(item or "").strip()
    }
    if _frontier_action_fingerprint(action) in blocked_fingerprints:
        return True
    query = str(action.get("query") or "").strip().casefold()
    path = _frontier_guard_path(action.get("path"))
    if not query:
        return False
    for anchor in (frontier or {}).get("anchors") or []:
        if not isinstance(anchor, dict):
            continue
        if anchor.get("kind") != "search_match":
            continue
        anchor_query = str(anchor.get("query") or "").strip().casefold()
        if query != anchor_query:
            continue
        anchor_path = _frontier_guard_path(anchor.get("path"))
        if not path or not anchor_path or _frontier_guard_paths_match(path, anchor_path):
            return True
    return False


def _frontier_has_blocking_evidence(frontier):
    frontier = frontier if isinstance(frontier, dict) else {}
    closure = _frontier_closure(frontier)
    signature = _frontier_signature(frontier)
    state = str(closure.get("state") or "open").strip()
    evidence_strength = str(closure.get("evidence_strength") or "").strip()
    if str(frontier.get("status") or "") != "open":
        return False
    if not _frontier_has_guard_evidence(frontier):
        return False
    guard_mode = str(closure.get("guard_mode") or "").strip()
    if guard_mode in {"observe_only", "prompt_nudge"}:
        return False
    if not guard_mode and not (state == "open" and evidence_strength in {"actionable", "blocking"}):
        return False
    if guard_mode and guard_mode not in FRONTIER_BLOCKING_GUARD_MODES:
        return False
    if evidence_strength == "weak":
        return False
    if state not in FRONTIER_BLOCKING_STATES:
        return False
    try:
        unverified_patch_batch_count = int(closure.get("unverified_patch_batch_count") or 0)
    except (TypeError, ValueError):
        unverified_patch_batch_count = 0
    has_obligation = bool(
        frontier.get("anchors")
        or _frontier_candidates(frontier)
        or signature.get("failing_tests")
        or closure.get("verifier_obligations")
        or unverified_patch_batch_count
    )
    return has_obligation


def _frontier_has_guard_evidence(frontier):
    frontier = frontier if isinstance(frontier, dict) else {}
    signature = _frontier_signature(frontier)
    if not signature.get("fingerprint"):
        return False
    for ref in frontier.get("evidence_refs") or []:
        if _frontier_evidence_ref_is_durable(ref):
            return True
    return False


def _frontier_evidence_ref_is_durable(ref):
    if not isinstance(ref, dict):
        return False
    kind = str(ref.get("kind") or "").strip()
    if kind == "tool_call":
        return ref.get("id") not in (None, "")
    if kind == "command_evidence":
        return any(ref.get(key) not in (None, "") for key in ("id", "path", "command_run_id"))
    if kind == "resume_key":
        return bool(ref.get("key"))
    if kind in FRONTIER_DURABLE_EVIDENCE_REF_KINDS:
        return any(ref.get(key) not in (None, "") for key in ("id", "key", "path", "command_run_id"))
    return bool(kind and any(ref.get(key) not in (None, "") for key in ("id", "key", "path", "command_run_id")))


def _frontier_has_finish_blocker(frontier):
    frontier = frontier if isinstance(frontier, dict) else {}
    if str(frontier.get("status") or "") != "open":
        return False
    if not _frontier_has_guard_evidence(frontier):
        return False
    closure = _frontier_closure(frontier)
    signature = _frontier_signature(frontier)
    return bool(
        _frontier_has_blocking_evidence(frontier)
        or signature.get("kind") == "finish_false_positive"
        or closure.get("verifier_obligations")
    )


def _frontier_finish_guard_enabled(frontier):
    closure = _frontier_closure(frontier)
    return bool(
        str(closure.get("guard_mode") or "").strip() == "block_finish"
        and "finish" in (closure.get("blocked_action_kinds") or [])
        and str(closure.get("evidence_strength") or "").strip() != "weak"
    )


def _active_work_todo_covers_frontier(active_work_todo, frontier):
    todo = active_work_todo if isinstance(active_work_todo, dict) else {}
    if not todo:
        return False
    source = todo.get("source") if isinstance(todo.get("source"), dict) else {}
    raw_target_paths = source.get("target_paths") or todo.get("target_paths") or []
    target_paths = [
        _frontier_guard_path(path)
        for path in raw_target_paths
        if isinstance(path, str) and path.strip()
    ]
    if not target_paths:
        return False
    required_paths = _frontier_required_edit_paths(frontier)
    if not required_paths:
        return False
    return all(
        any(_frontier_guard_paths_match(required, target) for target in target_paths)
        for required in required_paths
    )


def _frontier_first_unread_anchor_action(frontier, reason):
    for anchor in (frontier or {}).get("anchors") or []:
        if not isinstance(anchor, dict):
            continue
        if anchor.get("read_status") != "unread":
            continue
        if anchor.get("kind") not in {"source_location", "search_match"}:
            continue
        path = anchor.get("path")
        if not path:
            continue
        try:
            line = max(1, int(anchor.get("line") or 1))
        except (TypeError, ValueError):
            line = 1
        return {
            "type": "read_file",
            "path": path,
            "line_start": max(1, line - 20),
            "line_count": 80,
            "reason": reason,
        }
    return {}


def _frontier_first_candidate_read_action(frontier, reason):
    for candidate in _frontier_candidates(frontier):
        path = candidate.get("path")
        if not path:
            continue
        return {
            "type": "read_file",
            "path": path,
            "reason": reason,
        }
    return {}


def _frontier_first_search_action(frontier, reason):
    for anchor in (frontier or {}).get("anchors") or []:
        if not isinstance(anchor, dict):
            continue
        if anchor.get("kind") != "search_query":
            continue
        query = str(anchor.get("query") or "").strip()
        if not query:
            continue
        action = {
            "type": "search_text",
            "path": anchor.get("path") or ".",
            "query": query,
            "reason": reason,
        }
        if anchor.get("pattern"):
            action["pattern"] = anchor.get("pattern")
        return action
    return {}


def _frontier_replacement_action(frontier, *, blocked_action_kind):
    closure = _frontier_closure(frontier)
    state = str(closure.get("state") or "open").strip()
    base_reason = (
        "active compatibility frontier requires "
        f"{closure.get('next_action') or 'closing open evidence obligations'} "
        f"before {blocked_action_kind}"
    )
    action = _frontier_first_unread_anchor_action(frontier, base_reason)
    if action:
        return action
    if state == "search_needed":
        action = _frontier_first_search_action(frontier, base_reason)
        if action:
            return action
    action = _frontier_first_candidate_read_action(frontier, base_reason)
    if action:
        return action
    if state == "search_needed":
        action = _frontier_first_search_action(frontier, base_reason)
        if action:
            return action
    return {
        "type": "wait",
        "reason": base_reason,
    }


def _frontier_action_fingerprint(action):
    action = action if isinstance(action, dict) else {}
    action_type = str(action.get("type") or action.get("tool") or "").strip()
    core = {"type": action_type}
    for key in ("command", "cwd", "path", "query", "pattern"):
        value = action.get(key)
        if value not in (None, "", [], {}):
            core[key] = _normalize_shape(value) if isinstance(value, str) else value
    if action_type == "batch":
        core["tools"] = [_frontier_action_fingerprint(tool) for tool in action.get("tools") or []]
    return _short_id("action", core)


def active_compatibility_frontier_action_guard(
    frontier,
    action,
    *,
    resume=None,
    active_work_todo=None,
):
    """Return a deterministic replacement for broad/finish actions blocked by an open frontier."""
    frontier = frontier if isinstance(frontier, dict) else {}
    action = action if isinstance(action, dict) else {}
    resume = resume if isinstance(resume, dict) else {}
    closure = _frontier_closure(frontier)
    skipped_reason = ""
    if resume.get("pending_approvals"):
        skipped_reason = "pending_approvals"
    elif resume.get("running_commands"):
        skipped_reason = "running_commands"
    elif resume.get("stop_request"):
        skipped_reason = "stop_request"
    elif str(resume.get("phase") or "") in {"running_tool", "planning", "stop_requested"}:
        skipped_reason = f"phase:{resume.get('phase')}"
    if skipped_reason:
        return dict(action), {"applied": False, "skipped_reason": skipped_reason}

    action_type = str(action.get("type") or action.get("tool") or "").strip()
    if (
        action_type in {"write_file", "edit_file", "edit_file_hunks"}
        and _active_work_todo_covers_frontier(active_work_todo, frontier)
    ):
        return dict(action), {"applied": False, "skipped_reason": "active_work_todo_covers_frontier"}

    blocked_action_kind = ""
    if _frontier_action_is_finish_like(action):
        if _frontier_finish_guard_enabled(frontier) and _frontier_has_finish_blocker(frontier):
            blocked_action_kind = "finish"
    elif (
        _frontier_action_repeats_search(action, frontier)
        and "repeat_search" in (closure.get("blocked_action_kinds") or [])
    ):
        if _frontier_has_blocking_evidence(frontier):
            blocked_action_kind = "repeat_search"
    elif _frontier_action_is_broad_verifier(action, frontier):
        if (
            _frontier_has_blocking_evidence(frontier)
            and "broad_verifier" in (closure.get("blocked_action_kinds") or [])
            and not bool(closure.get("broad_verifier_allowed"))
        ):
            blocked_action_kind = "broad_verifier"

    if not blocked_action_kind:
        return dict(action), {"applied": False}

    original_fingerprint = _frontier_action_fingerprint(action)
    replacement = _frontier_replacement_action(frontier, blocked_action_kind=blocked_action_kind)
    if _frontier_action_fingerprint(replacement) == original_fingerprint:
        if blocked_action_kind == "repeat_search":
            replacement = {
                "type": "wait",
                "reason": "active compatibility frontier blocked repeated search but has no distinct read/search replacement",
            }
        else:
            return dict(action), {
                "applied": False,
                "skipped_reason": "replacement_matches_original_action",
            }
    decision = {
        "applied": True,
        "frontier_id": frontier.get("id") or "",
        "frontier_state": closure.get("state") or "open",
        "guard_mode": closure.get("guard_mode") or "",
        "blocked_action_kind": blocked_action_kind,
        "original_action_type": action_type,
        "replacement_action_type": replacement.get("type") or "",
        "action_fingerprint": original_fingerprint,
        "reason": replacement.get("reason") or "",
    }
    return replacement, decision


def build_active_compatibility_frontier(
    session,
    calls,
    *,
    verifier_failure_repair_agenda=None,
    search_anchor_observations=None,
    current_time=None,
):
    session = session if isinstance(session, dict) else {}
    agenda = verifier_failure_repair_agenda if isinstance(verifier_failure_repair_agenda, dict) else {}
    previous = session.get("active_compatibility_frontier")
    previous = previous if isinstance(previous, dict) else {}
    if not agenda:
        return previous or {}
    search_anchor_observations = list(search_anchor_observations or [])
    source_call = _source_call_for_agenda(calls, agenda)
    signature = build_failure_signature(agenda, source_call=source_call)
    if not signature:
        return previous or {}
    transition, overlap = family_transition(signature, previous)
    evidence_refs = _evidence_refs(agenda, source_call, search_anchor_observations)
    source_result = source_call.get("result") if isinstance(source_call.get("result"), dict) else {}
    source_parameters = source_call.get("parameters") if isinstance(source_call.get("parameters"), dict) else {}
    source_cwd = agenda.get("cwd") or source_result.get("cwd") or source_parameters.get("cwd") or ""
    anchors = _build_anchors(agenda, signature, search_anchor_observations, evidence_refs, cwd=source_cwd)
    candidates = _build_candidates(agenda, signature, anchors, evidence_refs)
    closure = _closure_state(anchors, candidates, signature)
    verifier_entry = _verifier_history_entry(signature, agenda, source_call, transition)
    keep_previous = transition in {"same", "narrower"}
    frontier = {
        "schema_version": SCHEMA_VERSION,
        "id": previous.get("id") if keep_previous and previous.get("id") else _next_frontier_id(session),
        "status": "open",
        "created_at": previous.get("created_at") if keep_previous and previous.get("created_at") else current_time,
        "updated_at": current_time,
        "failure_signature": signature,
        "family_transition": {
            "state": transition,
            "overlap": overlap,
            "previous_frontier_id": previous.get("id") if previous and not keep_previous else "",
        },
        "evidence_refs": _merge_dicts_by_identity(previous.get("evidence_refs") if keep_previous else [], evidence_refs, limit=30),
        "anchors": _merge_dicts_by_identity(previous.get("anchors") if keep_previous else [], anchors, id_key="id", limit=40),
        "sibling_candidates": _merge_dicts_by_identity(
            previous.get("sibling_candidates") if keep_previous else [],
            candidates,
            id_key="id",
            limit=40,
        ),
        "hypotheses": _hypotheses(candidates, closure, current_time),
        "patch_batch": previous.get("patch_batch") if keep_previous and isinstance(previous.get("patch_batch"), dict) else {},
        "verifier_history": _merge_dicts_by_identity(
            previous.get("verifier_history") if keep_previous else [],
            [verifier_entry],
            id_key="id",
            limit=20,
        ),
        "closure_state": closure,
    }
    if previous and transition == "moved":
        frontier["evidence_refs"] = _merge_dicts_by_identity(previous.get("evidence_refs") or [], frontier["evidence_refs"], limit=30)
    frontier["compact_summary"] = _compact_summary(frontier)
    return frontier


def update_session_active_compatibility_frontier(
    session,
    calls,
    *,
    verifier_failure_repair_agenda=None,
    search_anchor_observations=None,
    current_time=None,
):
    if not isinstance(session, dict):
        return {}
    frontier = build_active_compatibility_frontier(
        session,
        calls,
        verifier_failure_repair_agenda=verifier_failure_repair_agenda,
        search_anchor_observations=search_anchor_observations,
        current_time=current_time,
    )
    if frontier:
        session["active_compatibility_frontier"] = frontier
    return frontier
