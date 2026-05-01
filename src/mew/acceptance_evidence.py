from __future__ import annotations

import re
import shlex
from pathlib import Path


COMMAND_EVIDENCE_TOOLS = {"run_command", "run_tests"}

LONG_DEPENDENCY_ARTIFACT_PROOF_MARKERS = (
    "-version",
    "executable",
    "exists=true",
    "functional smoke",
    "ls -l",
    "regular file",
    "smoke_ok",
    "test -x",
)


def _result_dict(call: object) -> dict:
    if not isinstance(call, dict):
        return {}
    result = call.get("result")
    return result if isinstance(result, dict) else {}


def _parameters_dict(call: object) -> dict:
    if not isinstance(call, dict):
        return {}
    parameters = call.get("parameters")
    return parameters if isinstance(parameters, dict) else {}


def tool_call_output_text(call: object) -> str:
    if not isinstance(call, dict):
        return ""
    result = _result_dict(call)
    running_output = call.get("running_output") if isinstance(call.get("running_output"), dict) else {}
    parts = [
        call.get("error") or "",
        result.get("stdout") or "",
        result.get("stderr") or "",
        result.get("stdout_tail") or "",
        result.get("stderr_tail") or "",
        result.get("text") or "",
        result.get("summary") or "",
        result.get("output") or "",
        running_output.get("stdout") or "",
        running_output.get("stderr") or "",
    ]
    return "\n".join(str(part) for part in parts if part)


def tool_call_command_text(call: object) -> str:
    if not isinstance(call, dict):
        return ""
    result = _result_dict(call)
    parameters = _parameters_dict(call)
    return str(result.get("command") or parameters.get("command") or parameters.get("verify_command") or "")


def tool_call_cwd(call: object) -> str:
    result = _result_dict(call)
    parameters = _parameters_dict(call)
    return str(result.get("cwd") or parameters.get("cwd") or "")


def tool_call_terminal_success(call: object) -> bool:
    if not isinstance(call, dict):
        return False
    if str(call.get("status") or "").casefold() != "completed":
        return False
    result = _result_dict(call)
    if result.get("timed_out"):
        return False
    if call.get("tool") in COMMAND_EVIDENCE_TOOLS:
        return result.get("exit_code") == 0
    return True


def tool_call_evidence_ref(call: object) -> dict:
    if not isinstance(call, dict):
        return {}
    result = _result_dict(call)
    command = tool_call_command_text(call)
    output = tool_call_output_text(call)
    ref = {
        "kind": "tool_call",
        "id": call.get("id"),
        "tool": call.get("tool") or "",
        "status": call.get("status") or "",
        "exit_code": result.get("exit_code"),
        "timed_out": bool(result.get("timed_out")),
        "terminal_success": tool_call_terminal_success(call),
    }
    if command:
        ref["command"] = command
    if output:
        ref["summary"] = output[:240]
    return ref


def first_unquoted_shell_operator_span(command: object):
    text = str(command or "")
    in_single = False
    in_double = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and not in_single:
            escaped = True
            index += 1
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            index += 1
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            index += 1
            continue
        if in_single or in_double:
            index += 1
            continue
        if char in {"\n", "\r"}:
            return char, "chain", index, index + 1
        two_chars = text[index : index + 2]
        if two_chars in {"&&", "||"}:
            return two_chars, "chain", index, index + 2
        if char in {"|", ";"}:
            return char, "chain", index, index + 1
        index += 1
    return None, "", -1, -1


def split_unquoted_shell_command_segments(command: object) -> list[str]:
    text = str(command or "")
    segments: list[str] = []
    search_start = 0
    segment_start = 0
    while search_start < len(text):
        operator, kind, start, end = first_unquoted_shell_operator_span(text[search_start:])
        if not operator:
            break
        absolute_start = search_start + start
        absolute_end = search_start + end
        if kind == "chain":
            prefix = text[segment_start:absolute_start].strip()
            if prefix:
                segments.append(prefix)
            segment_start = absolute_end
        search_start = absolute_end
    tail = text[segment_start:].strip()
    if tail:
        segments.append(tail)
    return segments or [text]


def _long_dependency_artifact_command_refs(artifact: object, cwd: object = "") -> list[str]:
    artifact_text = str(artifact or "").strip()
    refs = [artifact_text] if artifact_text else []
    cwd_text = str(cwd or "").strip()
    artifact_path = Path(artifact_text)
    if artifact_path.is_absolute() and cwd_text and str(Path(cwd_text)) == str(artifact_path.parent):
        name = artifact_path.name.strip()
        if name and name not in refs:
            refs.append(name)
    return refs


def _long_dependency_invoked_command_token(parts: list[str]) -> str:
    index = 0
    while index < len(parts or []):
        token = str(parts[index] or "")
        name = Path(token).name.casefold()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            index += 1
            continue
        if name == "command":
            index += 1
            continue
        if name in {"timeout", "gtimeout"}:
            index += 1
            while index < len(parts):
                option = str(parts[index] or "")
                if option == "--":
                    index += 1
                    break
                if option in {"-s", "--signal", "-k", "--kill-after"} and index + 1 < len(parts):
                    index += 2
                    continue
                if option.startswith("-"):
                    index += 1
                    continue
                index += 1
                break
            continue
        if name == "env":
            index += 1
            while index < len(parts):
                env_token = str(parts[index] or "")
                if env_token == "--":
                    index += 1
                    break
                if env_token in {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"} and index + 1 < len(
                    parts
                ):
                    index += 2
                    continue
                if env_token.startswith("-") or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", env_token):
                    index += 1
                    continue
                break
            continue
        return token
    return ""


def _long_dependency_segment_invokes_artifact(segment: object, artifact_refs: list[str]) -> bool:
    segment = str(segment or "")
    if not segment:
        return False
    try:
        parts = shlex.split(segment, posix=True)
    except ValueError:
        parts = segment.split()
    command_token = _long_dependency_invoked_command_token(parts)
    if not command_token:
        return False
    command_path = str(command_token)
    command_name = Path(command_path).name
    for ref in artifact_refs or []:
        ref = str(ref or "").strip()
        if not ref:
            continue
        if "/" in ref and command_path == ref:
            return True
        if "/" not in ref and command_name == ref:
            return True
    return False


def _long_dependency_segment_strictly_proves_artifact(
    segment: object,
    artifact_text: str,
    test_x_pattern: str,
    bracket_x_pattern: str,
) -> bool:
    segment_text = str(segment or "")
    segment_lower = segment_text.casefold()
    artifact_lower = str(artifact_text or "").casefold()
    if artifact_lower not in segment_lower:
        return False
    if any(mask in segment_lower for mask in ("||", "2>/dev/null", ">/dev/null")):
        return False
    if re.search(test_x_pattern, segment_text) or re.search(bracket_x_pattern, segment_text):
        return True
    return _long_dependency_segment_invokes_artifact(segment_text, [artifact_text]) and any(
        marker in segment_lower for marker in ("-version", "--version", " -v", "-help", "--help")
    )


def _long_dependency_segment_may_mutate_artifact(segment: object) -> bool:
    text = str(segment or "").casefold()
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    command_names = {Path(str(part or "")).name.casefold() for part in parts}
    if command_names & {"rm", "unlink", "rmdir", "mv", "shred", "truncate"}:
        return True
    if "-delete" in text:
        return True
    if "-exec" in command_names and command_names & {"rm", "unlink", "rmdir", "mv", "shred", "truncate"}:
        return True
    return False


def long_dependency_command_surface_allows_artifact_proof(
    command: object,
    artifact: object,
    cwd: object = "",
) -> bool:
    command = str(command or "")
    artifact_text = str(artifact or "").strip()
    artifact_lower = artifact_text.casefold()
    artifact_refs = [ref.casefold() for ref in _long_dependency_artifact_command_refs(artifact_text, cwd)]
    if not command or not artifact_lower or not any(ref and ref in command.casefold() for ref in artifact_refs):
        return True
    if "\n" in command or "\r" in command:
        return False
    command_lower = command.casefold()
    if (
        "||" in command_lower
        or "|" in command_lower
        or ";" in command_lower
        or "/dev/null" in command_lower
        or re.search(r"(?<!&)&(?!&)", command_lower)
        or re.search(
            r"(?:^|[\s;&|])(?:if|then|fi|while|until|do|done|for|case|esac|select)(?:$|[\s;&|])",
            command_lower,
        )
        or re.search(r"(?:^|[\s;&|])!(?:$|[\s;&|])", command_lower)
    ):
        return False
    escaped_artifact = re.escape(artifact_text)
    test_x_pattern = rf"(?:^|[\s;&|])test\s+-x\s+['\"]?{escaped_artifact}['\"]?(?:$|[\s;&|])"
    bracket_x_pattern = rf"(?:^|[\s;&|])\[\s+-x\s+['\"]?{escaped_artifact}['\"]?\s+\]"
    saw_artifact_reference = False
    for segment in split_unquoted_shell_command_segments(command):
        segment_lower = segment.casefold()
        segment_has_artifact_ref = any(ref and ref in segment_lower for ref in artifact_refs)
        if segment_has_artifact_ref and _long_dependency_segment_may_mutate_artifact(segment):
            return False
        if _long_dependency_segment_strictly_proves_artifact(
            segment,
            artifact_text,
            test_x_pattern,
            bracket_x_pattern,
        ):
            saw_artifact_reference = True
            continue
        if saw_artifact_reference:
            return False
        if segment_has_artifact_ref:
            saw_artifact_reference = True
    return True


def _long_dependency_command_strictly_proves_artifact(call: object, artifact: object) -> bool:
    raw_command = tool_call_command_text(call)
    if "\n" in raw_command or "\r" in raw_command:
        return False
    command = re.sub(r"\\\r?\n\s*", " ", raw_command)
    artifact_text = str(artifact or "").strip()
    artifact_lower = artifact_text.casefold()
    if not command or not artifact_lower or artifact_lower not in command.casefold():
        return False
    artifact_refs = [ref.casefold() for ref in _long_dependency_artifact_command_refs(artifact_text, tool_call_cwd(call))]
    if not long_dependency_command_surface_allows_artifact_proof(command, artifact_text, tool_call_cwd(call)):
        return False
    escaped_artifact = re.escape(artifact_text)
    test_x_pattern = rf"(?:^|[\s;&|])test\s+-x\s+['\"]?{escaped_artifact}['\"]?(?:$|[\s;&|])"
    bracket_x_pattern = rf"(?:^|[\s;&|])\[\s+-x\s+['\"]?{escaped_artifact}['\"]?\s+\]"
    for raw_line in str(command or "").splitlines():
        line = raw_line.strip()
        line_lower = line.casefold()
        if artifact_lower not in line_lower:
            continue
        if (
            "||" in line_lower
            or "|" in line_lower
            or ";" in line_lower
            or re.search(r"(?<!&)&(?!&)", line_lower)
            or re.search(
                r"(?:^|[\s;&|])(?:if|then|fi|while|until|do|done|for|case|esac|select)(?:$|[\s;&|])",
                line_lower,
            )
            or re.search(r"(?:^|[\s;&|])!(?:$|[\s;&|])", line_lower)
        ):
            continue
        saw_proof_segment = False
        for segment in split_unquoted_shell_command_segments(line):
            segment_lower = segment.casefold()
            segment_proves_artifact = _long_dependency_segment_strictly_proves_artifact(
                segment,
                artifact_text,
                test_x_pattern,
                bracket_x_pattern,
            )
            if saw_proof_segment and not segment_proves_artifact:
                return False
            if artifact_lower not in segment_lower and not (
                saw_proof_segment and any(ref and ref in segment_lower for ref in artifact_refs)
            ):
                continue
            if not segment_proves_artifact:
                return False
            saw_proof_segment = True
        if saw_proof_segment:
            return True
    return False


def long_dependency_artifact_proven_by_call(call: object, artifact: object) -> bool:
    if not isinstance(call, dict) or call.get("tool") not in COMMAND_EVIDENCE_TOOLS:
        return False
    if str(call.get("status") or "").casefold() != "completed":
        return False
    result = _result_dict(call)
    if result.get("timed_out"):
        return False
    if result.get("exit_code") != 0:
        return False
    output_text = tool_call_output_text(call).casefold()
    artifact_lower = str(artifact or "").casefold()
    if not artifact_lower:
        return False
    if not long_dependency_command_surface_allows_artifact_proof(
        tool_call_command_text(call),
        artifact,
        tool_call_cwd(call),
    ):
        return False
    if any(marker in output_text for marker in ("does not exist", "missing", "no such file", "not found")):
        return False
    if artifact_lower in output_text and any(
        marker in output_text for marker in LONG_DEPENDENCY_ARTIFACT_PROOF_MARKERS
    ):
        return True
    return _long_dependency_command_strictly_proves_artifact(call, artifact)
