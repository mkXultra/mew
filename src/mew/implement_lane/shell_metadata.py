"""Conservative shell metadata for implement_v2 process-runner tools.

This module is intentionally not a source mutation classifier. It exposes only
bounded command-shape metadata for display, metrics, lifecycle hints, and exact
bridge eligibility gates.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import shlex
from typing import Literal

COMMAND_CLASSIFICATION_SCHEMA_VERSION = 1

CommandClassificationStatus = Literal["simple", "too_complex", "unavailable"]
ReadSearchListHint = Literal["search", "read", "list", "unknown"]
ProcessLifecycleHint = Literal["foreground", "background", "yieldable", "unknown"]

_CONNECTORS = frozenset({"&&", "||", ";", "|", "&"})
_REDIRECTS = frozenset({"<", "<<", "<<<", ">", ">>", ">|", "<>"})
_CONTROL_WORDS = frozenset(
    {
        "case",
        "do",
        "done",
        "elif",
        "else",
        "esac",
        "fi",
        "for",
        "function",
        "if",
        "select",
        "then",
        "until",
        "while",
        "{",
        "}",
        "(",
        ")",
    }
)
_SHELL_NAMES = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
_SEARCH_COMMANDS = frozenset({"rg", "grep", "ag", "ack", "fd"})
_LIST_COMMANDS = frozenset({"find", "ls", "tree"})
_READ_COMMANDS = frozenset({"cat", "head", "tail", "sed", "awk", "file", "stat", "readlink", "wc"})
_YIELDABLE_COMMANDS = frozenset(
    {
        "cargo",
        "clang",
        "cmake",
        "coqc",
        "gcc",
        "go",
        "make",
        "mvn",
        "ninja",
        "npm",
        "opam",
        "pnpm",
        "pytest",
        "rustc",
        "yarn",
    }
)


def classify_shell_command_metadata(
    command: object,
    *,
    command_source: str = "",
    use_shell: bool = False,
    parser_available: bool = True,
) -> dict[str, object]:
    """Return conservative tri-state metadata for a shell/argv command.

    `simple` means the command shape is parseable enough for summaries and
    narrow bridge preconditions. It never means read-only, edit-safe, approved,
    or source-mutating.
    """

    text = str(command or "").strip()
    if not parser_available:
        return _payload(
            result="unavailable",
            parser="none",
            reason="parser_not_installed",
            command=text,
            features=_empty_features(),
        )
    if not text:
        return _payload(
            result="unavailable",
            parser="shell_words",
            reason="command_unavailable",
            command=text,
            features=_empty_features(),
        )

    try:
        tokens = _shell_tokens(text)
    except ValueError as exc:
        return _payload(
            result="too_complex",
            parser="shell_words",
            reason=f"parse_error:{exc}",
            command=text,
            features=_empty_features(),
        )

    features = _features_from_tokens(tokens, command_source=command_source, use_shell=use_shell, raw_text=text)
    reason = _too_complex_reason(tokens, features, raw_text=text, command_source=command_source, use_shell=use_shell)
    result: CommandClassificationStatus = "too_complex" if reason else "simple"
    return _payload(
        result=result,
        parser="shell_words",
        reason=reason or "parsed_plain_command_sequence",
        command=text,
        features=features,
    )


def _payload(
    *,
    result: CommandClassificationStatus,
    parser: str,
    reason: str,
    command: str,
    features: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": COMMAND_CLASSIFICATION_SCHEMA_VERSION,
        "result": result,
        "parser": parser,
        "reason": reason,
        "command_hash": _command_hash(command),
        "features": features,
        "not_source_mutation_classifier": True,
        "shortcut_consumers_enabled": result == "simple",
    }


def _empty_features() -> dict[str, object]:
    return {
        "base_commands": [],
        "connectors": [],
        "has_redirection": False,
        "has_shell_expansion": False,
        "explicit_shell_interpreter": False,
        "read_search_list_hint": "unknown",
        "process_lifecycle_hint": "unknown",
    }


def _shell_tokens(text: str) -> list[str]:
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return [str(token) for token in lexer if str(token)]


def _features_from_tokens(
    tokens: list[str],
    *,
    command_source: str,
    use_shell: bool,
    raw_text: str,
) -> dict[str, object]:
    base_commands = _base_commands(tokens)
    connectors = tuple(dict.fromkeys(token for token in tokens if token in _CONNECTORS))
    has_redirection = any(_is_redirection_token(token) for token in tokens)
    has_shell_expansion = False if command_source in {"argv", "command_argv", "cmd_argv"} and not use_shell else _has_shell_expansion(raw_text)
    explicit_shell_interpreter = _has_explicit_shell_interpreter(tokens)
    return {
        "base_commands": list(base_commands[:8]),
        "connectors": list(connectors),
        "has_redirection": has_redirection,
        "has_shell_expansion": has_shell_expansion,
        "explicit_shell_interpreter": explicit_shell_interpreter,
        "read_search_list_hint": _read_search_list_hint(base_commands),
        "process_lifecycle_hint": _process_lifecycle_hint(base_commands, connectors),
        "command_source": command_source or "unknown",
        "use_shell": bool(use_shell),
    }


def _too_complex_reason(
    tokens: list[str],
    features: dict[str, object],
    *,
    raw_text: str,
    command_source: str,
    use_shell: bool,
) -> str:
    if command_source in {"argv", "command_argv", "cmd_argv"} and not use_shell:
        return ""
    if bool(features.get("has_shell_expansion")):
        return "shell_expansion"
    if any(token in _CONTROL_WORDS for token in tokens):
        return "control_flow"
    if "<<" in tokens or "<<<" in tokens:
        return "heredoc"
    if bool(features.get("explicit_shell_interpreter")):
        return "explicit_shell_interpreter"
    if raw_text.count("\n") > 0:
        return "multiline_shell"
    return ""


def _base_commands(tokens: list[str]) -> tuple[str, ...]:
    commands: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _CONNECTORS:
            _append_base_command(commands, current)
            current = []
            index += 1
            continue
        redirection_end = _redirection_span_end(tokens, index)
        if redirection_end is not None:
            index = redirection_end
            continue
        current.append(token)
        index += 1
    _append_base_command(commands, current)
    return tuple(dict.fromkeys(command for command in commands if command))


def _append_base_command(commands: list[str], tokens: list[str]) -> None:
    command_tokens = _command_tokens(tokens)
    if not command_tokens:
        return
    commands.append(Path(command_tokens[0]).name)


def _command_tokens(tokens: list[str]) -> list[str]:
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if "=" in token and not token.startswith("-") and token.split("=", 1)[0].replace("_", "A").isalnum():
            index += 1
            continue
        if Path(token).name == "env":
            index += 1
            while index < len(tokens) and tokens[index].startswith("-"):
                if tokens[index] in {"-u", "-C", "-S"} and index + 1 < len(tokens):
                    index += 2
                    continue
                index += 1
            continue
        if token == "command":
            index += 1
            continue
        return tokens[index:]
    return []


def _has_explicit_shell_interpreter(tokens: list[str]) -> bool:
    command_tokens = _command_tokens(tokens)
    if not command_tokens:
        return False
    if Path(command_tokens[0]).name not in _SHELL_NAMES:
        return False
    return any(token in {"-c", "-lc", "-cl"} or (token.startswith("-") and "c" in token[1:]) for token in command_tokens[1:])


def _has_shell_expansion(text: str) -> bool:
    in_single = False
    in_double = False
    escaped = False
    word_start = True
    chars = str(text or "")
    for index, char in enumerate(chars):
        if escaped:
            escaped = False
            word_start = False
            continue
        if char == "\\" and not in_single:
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            word_start = False
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            word_start = False
            continue
        if in_single:
            word_start = False
            continue
        if char.isspace():
            word_start = True
            continue
        two_chars = chars[index : index + 2]
        if char == "`" or two_chars in {"$(", "${", "$[", "<(", ">("}:
            return True
        if char == "$" and index + 1 < len(chars) and (
            chars[index + 1].isalnum() or chars[index + 1] in {"_", "?", "#", "@", "*", "$", "!"}
        ):
            return True
        if char in {"*", "?", "["}:
            return True
        if char in {"{", "}"}:
            return True
        if char == "~" and word_start:
            return True
        word_start = False
    return False


def _read_search_list_hint(base_commands: tuple[str, ...]) -> ReadSearchListHint:
    lowered = {command.casefold() for command in base_commands}
    if lowered & _SEARCH_COMMANDS:
        return "search"
    if lowered & _LIST_COMMANDS:
        return "list"
    if lowered & _READ_COMMANDS:
        return "read"
    return "unknown"


def _process_lifecycle_hint(base_commands: tuple[str, ...], connectors: tuple[str, ...]) -> ProcessLifecycleHint:
    if "&" in connectors:
        return "background"
    if {command.casefold() for command in base_commands} & _YIELDABLE_COMMANDS:
        return "yieldable"
    if base_commands:
        return "foreground"
    return "unknown"


def _is_redirection_token(token: str) -> bool:
    return token in _REDIRECTS or token.endswith(">") or token.endswith("<")


def _redirection_span_end(tokens: list[str], index: int) -> int | None:
    if index >= len(tokens):
        return None
    token = tokens[index]
    if token.isdigit() and index + 1 < len(tokens) and _is_redirection_token(tokens[index + 1]):
        index += 1
    elif not _is_redirection_token(token):
        return None
    while index < len(tokens) and _is_redirection_token(tokens[index]):
        index += 1
    if index < len(tokens) and tokens[index] == "&":
        return index + 2 if index + 1 < len(tokens) else index + 1
    return index + 1 if index < len(tokens) else index


def _command_hash(command: str) -> str:
    digest = hashlib.sha256(str(command or "").encode("utf-8", errors="replace")).hexdigest()
    return f"sha256:{digest}"


__all__ = [
    "COMMAND_CLASSIFICATION_SCHEMA_VERSION",
    "classify_shell_command_metadata",
]
