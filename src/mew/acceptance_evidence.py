from __future__ import annotations

import re
import shlex
from pathlib import Path


COMMAND_EVIDENCE_TOOLS = {"run_command", "run_tests"}
PATH_REF_BOUNDARY_CHARS = r"A-Za-z0-9._~+/-"
ARTIFACT_MUTATOR_COMMANDS = (
    "chmod",
    "chgrp",
    "chown",
    "cp",
    "dd",
    "install",
    "rm",
    "unlink",
    "rmdir",
    "mv",
    "shred",
    "truncate",
)
ARTIFACT_MUTATOR_SCRIPT_PATTERNS = (
    r"\bos\.remove\s*\(",
    r"\bos\.unlink\s*\(",
    r"\bpathlib\.path\s*\([^)]*\)\.unlink\s*\(",
)
OPAQUE_INTERPRETER_COMMANDS = {
    "bash",
    "dash",
    "node",
    "perl",
    "php",
    "python",
    "python3",
    "ruby",
    "sh",
    "zsh",
}


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


def split_unquoted_shell_command_segment_spans(command: object) -> list[dict[str, object]]:
    text = str(command or "")
    segments: list[dict[str, object]] = []
    search_start = 0
    segment_start = 0
    previous_operator = ""
    while search_start < len(text):
        operator, kind, start, end = first_unquoted_shell_operator_span(text[search_start:])
        if not operator:
            break
        absolute_start = search_start + start
        absolute_end = search_start + end
        if kind == "chain":
            raw_segment = text[segment_start:absolute_start]
            stripped = raw_segment.strip()
            if stripped:
                leading = len(raw_segment) - len(raw_segment.lstrip())
                trailing = len(raw_segment) - len(raw_segment.rstrip())
                segments.append(
                    {
                        "text": stripped,
                        "start": segment_start + leading,
                        "end": absolute_start - trailing,
                        "before_operator": previous_operator,
                        "after_operator": operator,
                    }
                )
            previous_operator = operator
            segment_start = absolute_end
        search_start = absolute_end
    raw_tail = text[segment_start:]
    stripped_tail = raw_tail.strip()
    if stripped_tail:
        leading = len(raw_tail) - len(raw_tail.lstrip())
        trailing = len(raw_tail) - len(raw_tail.rstrip())
        segments.append(
            {
                "text": stripped_tail,
                "start": segment_start + leading,
                "end": len(text) - trailing,
                "before_operator": previous_operator,
                "after_operator": "",
            }
        )
    return segments or [{"text": text, "start": 0, "end": len(text), "before_operator": "", "after_operator": ""}]


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


def _long_dependency_artifact_ref_pattern(ref: object) -> str:
    ref_text = str(ref or "").strip().casefold()
    if not ref_text:
        return r"(?!)"
    escaped = re.escape(ref_text)
    if "/" in ref_text:
        return rf"(?<![{PATH_REF_BOUNDARY_CHARS}]){escaped}(?![{PATH_REF_BOUNDARY_CHARS}])"
    return (
        rf"(?:(?<![{PATH_REF_BOUNDARY_CHARS}]){escaped}(?![{PATH_REF_BOUNDARY_CHARS}])|"
        rf"(?<![{PATH_REF_BOUNDARY_CHARS}])\./{escaped}(?![{PATH_REF_BOUNDARY_CHARS}]))"
    )


def _long_dependency_artifact_refs_pattern(artifact_refs: list[str]) -> str:
    patterns = [_long_dependency_artifact_ref_pattern(ref) for ref in artifact_refs if ref]
    return r"(?!)" if not patterns else "(?:" + "|".join(patterns) + ")"


def _long_dependency_text_has_artifact_ref(text: object, artifact_refs: list[str]) -> bool:
    lowered = str(text or "").casefold()
    return any(ref and re.search(_long_dependency_artifact_ref_pattern(ref), lowered) for ref in artifact_refs)


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
    command_path = str(command_token).casefold()
    for ref in artifact_refs or []:
        ref = str(ref or "").strip()
        if not ref:
            continue
        if "/" in ref and command_path == ref:
            return True
        if "/" not in ref and command_path in {ref, f"./{ref}"}:
            return True
    return False


def _long_dependency_segment_strictly_proves_artifact(
    segment: object,
    artifact_text: str,
    test_x_pattern: str,
    bracket_x_pattern: str,
    artifact_refs: list[str] | None = None,
) -> bool:
    segment_text = str(segment or "")
    segment_lower = segment_text.casefold()
    artifact_lower = str(artifact_text or "").casefold()
    refs = artifact_refs or [artifact_lower]
    if not _long_dependency_text_has_artifact_ref(segment_lower, refs):
        return False
    if any(mask in segment_lower for mask in ("||", "2>/dev/null", ">/dev/null")):
        return False
    try:
        parts = shlex.split(segment_text)
    except ValueError:
        parts = segment_text.split()
    lowered_parts = [str(part or "").casefold() for part in parts]
    if len(lowered_parts) == 3 and lowered_parts[0] == "test" and lowered_parts[1] == "-x":
        return _long_dependency_argument_matches_artifact_ref(lowered_parts[2], refs)
    if (
        len(lowered_parts) == 4
        and lowered_parts[0] == "["
        and lowered_parts[1] == "-x"
        and lowered_parts[-1] == "]"
    ):
        return _long_dependency_argument_matches_artifact_ref(lowered_parts[2], refs)
    return _long_dependency_segment_invokes_artifact(segment_text, refs) and any(
        marker in segment_lower for marker in ("-version", "--version", " -v", "-help", "--help")
    )


def _long_dependency_argument_matches_artifact_ref(argument: object, artifact_refs: list[str]) -> bool:
    value = str(argument or "").casefold()
    for ref in artifact_refs:
        ref = str(ref or "").strip().casefold()
        if not ref:
            continue
        if "/" in ref and value == ref:
            return True
        if "/" not in ref and value in {ref, f"./{ref}"}:
            return True
    return False


def _long_dependency_segment_may_mutate_artifact(segment: object) -> bool:
    text = str(segment or "").casefold()
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    command_names = {Path(str(part or "")).name.casefold() for part in parts}
    if command_names & set(ARTIFACT_MUTATOR_COMMANDS):
        return True
    mutator_pattern = r"(?:^|[\s;&|('\"])(?:{})\b".format("|".join(ARTIFACT_MUTATOR_COMMANDS))
    if re.search(mutator_pattern, text):
        return True
    if any(re.search(pattern, text) for pattern in ARTIFACT_MUTATOR_SCRIPT_PATTERNS):
        return True
    if "-delete" in text:
        return True
    if "-exec" in command_names and command_names & {"rm", "unlink", "rmdir", "mv", "shred", "truncate"}:
        return True
    return False


def _long_dependency_segment_redirects_to_artifact(segment: object, artifact_refs: list[str]) -> bool:
    text = str(segment or "").casefold()
    for ref in artifact_refs:
        if not ref:
            continue
        escaped = re.escape(ref)
        if re.search(rf"(?:^|[\s;&|])(?:\d*>>|\d*>\||\d*>|<>)\s*['\"]?{escaped}['\"]?(?:$|[\s;&|])", text):
            return True
    return False


def _long_dependency_segment_targets_artifact_parent_glob(segment: object, artifact: object, cwd: object = "") -> bool:
    artifact_text = str(artifact or "").strip()
    if not artifact_text:
        return False
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    artifact_path = Path(artifact_text)
    if not artifact_path.is_absolute():
        return False
    parent = str(artifact_path.parent).casefold()
    cwd_text = str(Path(str(cwd or ""))).casefold() if cwd else ""
    cwd_is_parent = bool(cwd_text and cwd_text == parent)
    text = str(segment or "").casefold()
    if re.search(rf"{re.escape(parent)}/[^\s;&|'\"]*[*?\[]", text):
        return True
    if cwd_is_parent and re.search(r"(?:^|[\s;&|'\"])(?:\*|\./\*|\.)(?:$|[\s;&|'\"])", text):
        return True
    for part in parts:
        token = str(part or "").strip().casefold()
        if not token:
            continue
        if cwd_is_parent and token in {"*", "./*", ".", "./"}:
            return True
        if token == parent:
            return True
        if token.startswith(parent + "/"):
            tail = token[len(parent) + 1 :]
            if not tail or any(char in tail for char in "*?["):
                return True
    return False


def _long_dependency_segment_invokes_opaque_interpreter(segment: object) -> bool:
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    invoked = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
    if _long_dependency_is_opaque_interpreter_name(invoked):
        return True
    return any(_long_dependency_is_opaque_interpreter_name(Path(str(part or "")).name.casefold()) for part in parts)


def _long_dependency_is_opaque_interpreter_name(name: object) -> bool:
    value = str(name or "").casefold()
    return value in OPAQUE_INTERPRETER_COMMANDS or bool(
        re.fullmatch(r"(?:python|python3|pypy|pypy3)(?:\.\d+)*", value)
    )


def _long_dependency_segment_may_mutate_artifact_scope(segment: object, artifact: object, cwd: object = "") -> bool:
    artifact_refs = [ref.casefold() for ref in _long_dependency_artifact_command_refs(artifact, cwd)]
    if _long_dependency_segment_redirects_to_artifact(segment, artifact_refs):
        return True
    segment_refs_artifact = _long_dependency_text_has_artifact_ref(segment, artifact_refs)
    if segment_refs_artifact and _long_dependency_segment_invokes_opaque_interpreter(segment):
        return True
    if not _long_dependency_segment_may_mutate_artifact(segment):
        return False
    return segment_refs_artifact or _long_dependency_segment_targets_artifact_parent_glob(
        segment,
        artifact,
        cwd,
    )


def _long_dependency_segment_suppresses_artifact_proof_output(segment: object) -> bool:
    text = str(segment or "").casefold()
    return bool(re.search(r"(?:^|[\s;&|])(?:\d*>>|\d*>\||\d*>|<>)\s*(?:/dev/null|['\"]/dev/null['\"])", text))


def _long_dependency_command_enforces_errexit(command: object) -> bool:
    errexit = False
    for segment in split_unquoted_shell_command_segments(command):
        try:
            parts = shlex.split(segment)
        except ValueError:
            parts = segment.split()
        if not parts or parts[0] != "set":
            continue
        for index, part in enumerate(parts):
            if part == "+o" and index + 1 < len(parts) and parts[index + 1] == "errexit":
                errexit = False
            elif part == "-o" and index + 1 < len(parts) and parts[index + 1] == "errexit":
                errexit = True
            elif part.startswith("+") and "e" in part and not part.startswith("++"):
                errexit = False
            elif part.startswith("-") and "e" in part and not part.startswith("--"):
                errexit = True
    return errexit


def long_dependency_command_surface_allows_artifact_proof(
    command: object,
    artifact: object,
    cwd: object = "",
) -> bool:
    command = str(command or "")
    artifact_text = str(artifact or "").strip()
    artifact_lower = artifact_text.casefold()
    artifact_refs = [ref.casefold() for ref in _long_dependency_artifact_command_refs(artifact_text, cwd)]
    if not command or not artifact_lower or not _long_dependency_text_has_artifact_ref(command, artifact_refs):
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
        segment_has_artifact_ref = _long_dependency_text_has_artifact_ref(segment_lower, artifact_refs)
        if segment_has_artifact_ref and _long_dependency_segment_may_mutate_artifact(segment):
            return False
        if _long_dependency_segment_strictly_proves_artifact(
            segment,
            artifact_text,
            test_x_pattern,
            bracket_x_pattern,
            artifact_refs,
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
    artifact_refs = [ref.casefold() for ref in _long_dependency_artifact_command_refs(artifact_text, tool_call_cwd(call))]
    if not command or not artifact_lower or not _long_dependency_text_has_artifact_ref(command, artifact_refs):
        return False
    if not long_dependency_command_surface_allows_artifact_proof(command, artifact_text, tool_call_cwd(call)):
        return False
    escaped_artifact = re.escape(artifact_text)
    test_x_pattern = rf"(?:^|[\s;&|])test\s+-x\s+['\"]?{escaped_artifact}['\"]?(?:$|[\s;&|])"
    bracket_x_pattern = rf"(?:^|[\s;&|])\[\s+-x\s+['\"]?{escaped_artifact}['\"]?\s+\]"
    for raw_line in str(command or "").splitlines():
        line = raw_line.strip()
        line_lower = line.casefold()
        if not _long_dependency_text_has_artifact_ref(line_lower, artifact_refs):
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
            segment_has_artifact_ref = _long_dependency_text_has_artifact_ref(segment_lower, artifact_refs)
            segment_proves_artifact = _long_dependency_segment_strictly_proves_artifact(
                segment,
                artifact_text,
                test_x_pattern,
                bracket_x_pattern,
                artifact_refs,
            )
            if saw_proof_segment and not segment_proves_artifact:
                return False
            if not segment_has_artifact_ref and not (saw_proof_segment and segment_has_artifact_ref):
                continue
            if not segment_proves_artifact:
                return False
            saw_proof_segment = True
        if saw_proof_segment:
            return True
    return False


def _long_dependency_output_proves_artifact(call: object, artifact: object) -> bool:
    output_text = tool_call_output_text(call).casefold()
    artifact_lower = str(artifact or "").casefold()
    artifact_refs = [ref.casefold() for ref in _long_dependency_artifact_command_refs(artifact, tool_call_cwd(call))]
    artifact_pattern = _long_dependency_artifact_refs_pattern(artifact_refs)
    if not artifact_lower or not _long_dependency_text_has_artifact_ref(output_text, artifact_refs):
        return False
    if _long_dependency_output_reports_artifact_missing(output_text, artifact_pattern):
        return False
    if not _long_dependency_command_has_artifact_proof_segment(call, artifact):
        return False
    if re.search(rf"(?m)^[bcdlps-][rwxstST-]{{9}}\s+.*{artifact_pattern}", output_text):
        return True
    if re.search(rf"\bexists=true\b.*{artifact_pattern}", output_text):
        return True
    if re.search(rf"{artifact_pattern}.*\bexists=true\b", output_text):
        return True
    if re.search(rf"{artifact_pattern}.*\b(?:regular file|executable|elf|mach-o|script)\b", output_text):
        return True
    if re.search(rf"\b(?:regular file|executable|elf|mach-o|script)\b.*{artifact_pattern}", output_text):
        return True
    if "smoke_ok" in output_text and _long_dependency_text_has_artifact_ref(output_text, artifact_refs):
        return True
    return False


def _long_dependency_output_reports_artifact_missing(output_text: str, artifact_pattern: str) -> bool:
    missing_pattern = r"(?:does not exist|missing|no such file|not found)"
    for line in str(output_text or "").splitlines():
        if re.search(artifact_pattern, line, re.IGNORECASE) and re.search(
            rf"\b{missing_pattern}\b",
            line,
            re.IGNORECASE,
        ):
            return True
    return False


def _long_dependency_command_has_artifact_proof_segment(
    call: object,
    artifact: object,
    *,
    allow_metadata_probes: bool = True,
) -> bool:
    command = tool_call_command_text(call)
    artifact_text = str(artifact or "").strip()
    if not command or not artifact_text:
        return False
    artifact_refs = [ref.casefold() for ref in _long_dependency_artifact_command_refs(artifact_text, tool_call_cwd(call))]
    escaped_artifact = re.escape(artifact_text)
    test_x_pattern = rf"(?:^|[\s;&|])test\s+-x\s+['\"]?{escaped_artifact}['\"]?(?:$|[\s;&|])"
    bracket_x_pattern = rf"(?:^|[\s;&|])\[\s+-x\s+['\"]?{escaped_artifact}['\"]?\s+\]"
    segment_entries = split_unquoted_shell_command_segment_spans(command)
    segments = [str(entry.get("text") or "") for entry in segment_entries]
    artifact_segments = [
        (index, entry, str(entry.get("text") or ""))
        for index, entry in enumerate(segment_entries)
        for segment in [str(entry.get("text") or "")]
        if _long_dependency_text_has_artifact_ref(segment, artifact_refs)
    ]

    def later_sequential_operator_exists(entry_index: int) -> bool:
        return any(
            str(later_entry.get("after_operator") or "") in {";", "\n", "\r"}
            for later_entry in segment_entries[entry_index:]
        )

    for index, entry, segment in artifact_segments:
        before_operator = str(entry.get("before_operator") or "")
        after_operator = str(entry.get("after_operator") or "")
        if (
            _long_dependency_segment_may_mutate_artifact(segment)
            or _long_dependency_segment_redirects_to_artifact(segment, artifact_refs)
            or _long_dependency_segment_suppresses_artifact_proof_output(segment)
            or before_operator == "|"
            or after_operator == "|"
            or before_operator == "||"
            or after_operator == "||"
            or (
                index < len(segment_entries) - 1
                and after_operator in {";", "\n", "\r"}
                and (
                    before_operator == "&&"
                    or not _long_dependency_command_enforces_errexit(command[: int(entry.get("start") or 0)])
                )
            )
            or (before_operator == "&&" and later_sequential_operator_exists(index))
            or (after_operator == "&&" and later_sequential_operator_exists(index))
        ):
            continue
        proves_artifact = _long_dependency_segment_strictly_proves_artifact(
            segment,
            artifact_text,
            test_x_pattern,
            bracket_x_pattern,
            artifact_refs,
        )
        try:
            parts = shlex.split(segment)
        except ValueError:
            parts = segment.split()
        invoked = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
        proves_artifact = proves_artifact or (allow_metadata_probes and invoked in {"file", "ls", "stat"})
        if not proves_artifact:
            continue
        if any(
            _long_dependency_segment_may_mutate_artifact_scope(later_segment, artifact_text, tool_call_cwd(call))
            for later_index, later_segment in enumerate(segments)
            if later_index > index
        ):
            continue
        return True
    return False


def _long_dependency_command_echoes_artifact_output(call: object, artifact: object) -> bool:
    command = tool_call_command_text(call)
    artifact_lower = str(artifact or "").casefold()
    if not command or not artifact_lower:
        return False
    artifact_refs = [ref.casefold() for ref in _long_dependency_artifact_command_refs(artifact, tool_call_cwd(call))]
    # The raw command may hide the path with shell-quoted string
    # concatenation, so inspect echo/printf arguments after tokenization.
    for segment in split_unquoted_shell_command_segments(command):
        try:
            parts = shlex.split(segment)
        except ValueError:
            parts = segment.split()
        invoked = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
        if invoked not in {"echo", "printf"}:
            continue
        rendered_arguments = " ".join(str(part or "") for part in parts[1:]).casefold()
        if not _long_dependency_text_has_artifact_ref(rendered_arguments, artifact_refs):
            continue
        if re.search(r"[bcdlps-][rwxstST-]{9}\s+.*" + _long_dependency_artifact_refs_pattern(artifact_refs), rendered_arguments):
            return True
        if re.search(r"\bexists=true\b.*" + _long_dependency_artifact_refs_pattern(artifact_refs), rendered_arguments):
            return True
        if re.search(_long_dependency_artifact_refs_pattern(artifact_refs) + r".*\bexists=true\b", rendered_arguments):
            return True
        if re.search(
            _long_dependency_artifact_refs_pattern(artifact_refs)
            + r".*\b(?:regular file|executable|elf|mach-o|script|smoke_ok)\b",
            rendered_arguments,
        ):
            return True
        if re.search(
            r"\b(?:regular file|executable|elf|mach-o|script|smoke_ok)\b.*"
            + _long_dependency_artifact_refs_pattern(artifact_refs),
            rendered_arguments,
        ):
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
    artifact_lower = str(artifact or "").casefold()
    if not artifact_lower:
        return False
    if _long_dependency_command_echoes_artifact_output(
        call,
        artifact,
    ) and not _long_dependency_command_has_artifact_proof_segment(
        call,
        artifact,
        allow_metadata_probes=False,
    ):
        return False
    if _long_dependency_output_proves_artifact(call, artifact):
        return True
    output_text = tool_call_output_text(call).casefold()
    if not long_dependency_command_surface_allows_artifact_proof(
        tool_call_command_text(call),
        artifact,
        tool_call_cwd(call),
    ):
        return False
    artifact_refs = [ref.casefold() for ref in _long_dependency_artifact_command_refs(artifact, tool_call_cwd(call))]
    artifact_pattern = _long_dependency_artifact_refs_pattern(artifact_refs)
    if _long_dependency_output_reports_artifact_missing(output_text, artifact_pattern):
        return False
    return _long_dependency_command_strictly_proves_artifact(call, artifact)
