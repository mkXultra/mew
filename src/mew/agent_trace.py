from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Iterable, Sequence


TRACE_SCHEMA_VERSION = 1
SUMMARY_SCHEMA_VERSION = 1
_WALL_TIME_RE = re.compile(r"Wall time:\s*([0-9.]+)\s*seconds")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json_list(path: Path) -> list[Any]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _parse_timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_timestamp(value: dt.datetime) -> str:
    text = value.isoformat(timespec="milliseconds")
    return text.replace("+00:00", "Z")


def _elapsed_ms(timestamp: dt.datetime | None, start: dt.datetime | None) -> int | None:
    if timestamp is None or start is None:
        return None
    return max(0, int((timestamp - start).total_seconds() * 1000))


def _jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    if not path.exists():
        return
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        if _is_known_non_json_trace_line(line):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            yield line_number, {"_parse_error": True, "raw": line}
            continue
        if isinstance(payload, dict):
            yield line_number, payload
        else:
            yield line_number, {"_parse_error": True, "raw": payload}


def _is_known_non_json_trace_line(line: str) -> bool:
    stripped = line.strip()
    return stripped in {
        "Reading additional input from stdin...",
    }


def _truncate(value: Any, limit: int = 500) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _base_event(
    *,
    agent: str,
    source_path: Path | None,
    line_number: int | None,
    kind: str,
    timestamp: dt.datetime | str | None = None,
    elapsed_ms: int | None = None,
    step_id: int | None = None,
) -> dict[str, Any]:
    event = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "agent": agent,
        "kind": kind,
        "source": str(source_path) if source_path else "",
        "line_number": line_number,
    }
    if isinstance(timestamp, dt.datetime):
        event["timestamp"] = _format_timestamp(timestamp)
    elif isinstance(timestamp, str) and timestamp:
        event["timestamp"] = timestamp
    if elapsed_ms is not None:
        event["elapsed_ms"] = elapsed_ms
    if step_id is not None:
        event["step_id"] = step_id
    return event


def _tool_event(
    *,
    agent: str,
    source_path: Path | None,
    line_number: int | None,
    phase: str,
    tool: str,
    tool_id: str = "",
    summary: Any = "",
    status: Any = "",
    exit_code: Any = None,
    server: str = "",
    timestamp: dt.datetime | str | None = None,
    elapsed_ms: int | None = None,
    step_id: int | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    event = _base_event(
        agent=agent,
        source_path=source_path,
        line_number=line_number,
        kind="tool_call",
        timestamp=timestamp,
        elapsed_ms=elapsed_ms,
        step_id=step_id,
    )
    event.update(
        {
            "phase": phase,
            "tool": tool,
            "id": tool_id,
            "summary": _truncate(summary),
            "status": str(status or ""),
            "server": server,
        }
    )
    if isinstance(exit_code, int):
        event["exit_code"] = exit_code
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    return event


def normalize_codex_stdout(stdout_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, payload in _jsonl(stdout_path):
        if payload.get("_parse_error"):
            event = _base_event(agent="codex", source_path=stdout_path, line_number=line_number, kind="parse_error")
            event["summary"] = _truncate(payload.get("raw"))
            events.append(event)
            continue

        if payload.get("type") == "thread.started":
            event = _base_event(agent="codex", source_path=stdout_path, line_number=line_number, kind="session")
            event["session_id"] = payload.get("thread_id", "")
            events.append(event)
            continue

        item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
        msg = payload.get("msg") if isinstance(payload.get("msg"), dict) else {}
        if item.get("type") == "agent_message" and item.get("text"):
            event = _base_event(agent="codex", source_path=stdout_path, line_number=line_number, kind="message")
            event["summary"] = _truncate(item.get("text"))
            events.append(event)
            continue
        if msg.get("type") == "agent_message" and msg.get("message"):
            event = _base_event(agent="codex", source_path=stdout_path, line_number=line_number, kind="message")
            event["summary"] = _truncate(msg.get("message"))
            events.append(event)
            continue
        if msg.get("type") == "token_count":
            event = _base_event(agent="codex", source_path=stdout_path, line_number=line_number, kind="usage")
            event["summary"] = _truncate(msg)
            event["usage"] = msg
            events.append(event)
            continue

        raw_type = payload.get("type")
        if raw_type in {"item.started", "item.completed"}:
            phase = "started" if raw_type == "item.started" else "completed"
            if item.get("type") == "command_execution":
                events.append(
                    _tool_event(
                        agent="codex",
                        source_path=stdout_path,
                        line_number=line_number,
                        phase=phase,
                        tool="command_execution",
                        tool_id=str(item.get("id", "")),
                        summary=item.get("command") or item.get("aggregated_output") or item,
                        status=item.get("status") or item.get("error") or "",
                        exit_code=item.get("exit_code"),
                    )
                )
                continue
            if item.get("type") == "mcp_tool_call":
                events.append(
                    _tool_event(
                        agent="codex",
                        source_path=stdout_path,
                        line_number=line_number,
                        phase=phase,
                        tool=str(item.get("tool") or "mcp_tool_call"),
                        tool_id=str(item.get("id", "")),
                        summary=item.get("arguments") or item.get("result") or item,
                        status=item.get("status") or item.get("error") or "",
                        server=str(item.get("server") or ""),
                    )
                )
                continue
    return events


def normalize_claude_stdout(stdout_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    tool_memory: dict[str, dict[str, Any]] = {}
    for line_number, payload in _jsonl(stdout_path):
        if payload.get("_parse_error"):
            event = _base_event(agent="claude", source_path=stdout_path, line_number=line_number, kind="parse_error")
            event["summary"] = _truncate(payload.get("raw"))
            events.append(event)
            continue

        if payload.get("session_id"):
            event = _base_event(agent="claude", source_path=stdout_path, line_number=line_number, kind="session")
            event["session_id"] = payload.get("session_id", "")
            events.append(event)

        if payload.get("type") == "assistant":
            for content in payload.get("message", {}).get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "text" and content.get("text"):
                    event = _base_event(agent="claude", source_path=stdout_path, line_number=line_number, kind="message")
                    event["summary"] = _truncate(content.get("text"))
                    events.append(event)
                elif content.get("type") == "tool_use":
                    tool_id = str(content.get("id", ""))
                    tool_event = _tool_event(
                        agent="claude",
                        source_path=stdout_path,
                        line_number=line_number,
                        phase="started",
                        tool=str(content.get("name") or "tool_use"),
                        tool_id=tool_id,
                        summary=content.get("input") or content,
                    )
                    tool_memory[tool_id] = tool_event
                    events.append(tool_event)
            continue

        if payload.get("type") == "user":
            for content in payload.get("message", {}).get("content", []):
                if not isinstance(content, dict) or content.get("type") != "tool_result":
                    continue
                tool_id = str(content.get("tool_use_id", ""))
                remembered = tool_memory.get(tool_id, {})
                events.append(
                    _tool_event(
                        agent="claude",
                        source_path=stdout_path,
                        line_number=line_number,
                        phase="completed",
                        tool=str(remembered.get("tool") or "tool_result"),
                        tool_id=tool_id,
                        summary=remembered.get("summary") or content.get("content") or content,
                        status="failed" if content.get("is_error") is True else "success",
                    )
                )
            continue

        if payload.get("type") == "result":
            event = _base_event(agent="claude", source_path=stdout_path, line_number=line_number, kind="result")
            event["summary"] = _truncate(payload.get("result") or payload)
            if payload.get("usage"):
                event["usage"] = payload.get("usage")
            events.append(event)
    return events


def normalize_atif_trajectory(*, agent: str, trajectory_path: Path) -> list[dict[str, Any]]:
    trajectory = _read_json(trajectory_path)
    steps = trajectory.get("steps") if isinstance(trajectory.get("steps"), list) else []
    timestamps = [_parse_timestamp(step.get("timestamp")) for step in steps if isinstance(step, dict)]
    start = next((timestamp for timestamp in timestamps if timestamp is not None), None)
    events: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        timestamp = _parse_timestamp(step.get("timestamp"))
        step_id = step.get("step_id") if isinstance(step.get("step_id"), int) else None
        line_number = step_id
        tool_calls = step.get("tool_calls") if isinstance(step.get("tool_calls"), list) else []
        if tool_calls:
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                events.extend(
                    _events_from_atif_tool_call(
                        agent=agent,
                        source_path=trajectory_path,
                        line_number=line_number,
                        step_id=step_id,
                        timestamp=timestamp,
                        start=start,
                        step=step,
                        tool_call=tool_call,
                    )
                )
            continue

        event = _event_from_atif_non_tool_step(
            agent=agent,
            source_path=trajectory_path,
            line_number=line_number,
            step_id=step_id,
            timestamp=timestamp,
            start=start,
            step=step,
        )
        if event is not None:
            events.append(event)
    events.sort(key=_event_sort_key)
    return events


def _events_from_atif_tool_call(
    *,
    agent: str,
    source_path: Path,
    line_number: int | None,
    step_id: int | None,
    timestamp: dt.datetime | None,
    start: dt.datetime | None,
    step: dict[str, Any],
    tool_call: dict[str, Any],
) -> list[dict[str, Any]]:
    tool = str(tool_call.get("function_name") or tool_call.get("name") or tool_call.get("type") or "tool_call")
    tool_id = str(tool_call.get("tool_call_id") or tool_call.get("id") or "")
    arguments = tool_call.get("arguments")
    summary = _tool_summary(tool=tool, arguments=arguments, step=step)
    status = _tool_status(step)
    exit_code = _tool_exit_code(step)
    duration_ms = _tool_duration_ms(step)
    started_at = timestamp
    if timestamp is not None and duration_ms is not None:
        started_at = timestamp - dt.timedelta(milliseconds=duration_ms)
    started = _tool_event(
        agent=agent,
        source_path=source_path,
        line_number=line_number,
        phase="started",
        tool=tool,
        tool_id=tool_id,
        summary=summary,
        timestamp=started_at,
        elapsed_ms=_elapsed_ms(started_at, start),
        step_id=step_id,
    )
    completed = _tool_event(
        agent=agent,
        source_path=source_path,
        line_number=line_number,
        phase="completed",
        tool=tool,
        tool_id=tool_id,
        summary=summary,
        status=status,
        exit_code=exit_code,
        timestamp=timestamp,
        elapsed_ms=_elapsed_ms(timestamp, start),
        step_id=step_id,
        duration_ms=duration_ms,
    )
    if isinstance(arguments, dict) and arguments:
        started["arguments"] = dict(arguments)
        completed["arguments"] = dict(arguments)
    return [started, completed]


def _event_from_atif_non_tool_step(
    *,
    agent: str,
    source_path: Path,
    line_number: int | None,
    step_id: int | None,
    timestamp: dt.datetime | None,
    start: dt.datetime | None,
    step: dict[str, Any],
) -> dict[str, Any] | None:
    source = str(step.get("source") or "")
    message = step.get("message")
    reasoning = step.get("reasoning_content")
    if not isinstance(message, str) and not isinstance(reasoning, str):
        return None
    kind = "message" if source == "agent" else "input"
    event = _base_event(
        agent=agent,
        source_path=source_path,
        line_number=line_number,
        kind=kind,
        timestamp=timestamp,
        elapsed_ms=_elapsed_ms(timestamp, start),
        step_id=step_id,
    )
    event["source_role"] = source
    event["summary"] = _truncate(message if isinstance(message, str) and message else reasoning)
    metrics = step.get("metrics") if isinstance(step.get("metrics"), dict) else {}
    if metrics:
        event["model_metrics"] = metrics
    if isinstance(reasoning, str) and reasoning and message:
        event["reasoning_summary"] = _truncate(reasoning)
    return event


def _tool_summary(*, tool: str, arguments: Any, step: dict[str, Any]) -> Any:
    if isinstance(arguments, dict):
        for key in ("cmd", "command", "file_path", "pattern", "input"):
            value = arguments.get(key)
            if value:
                return value
    if arguments:
        return arguments
    message = step.get("message")
    if message:
        return message
    return tool


def _tool_status(step: dict[str, Any]) -> str:
    extra = step.get("extra") if isinstance(step.get("extra"), dict) else {}
    if isinstance(extra.get("status"), str) and extra["status"]:
        return extra["status"]
    if extra.get("tool_result_is_error") is True:
        return "failed"
    raw_result = _raw_tool_result(extra)
    if isinstance(raw_result, dict) and raw_result.get("is_error") is True:
        return "failed"
    exit_code = _tool_exit_code(step)
    if isinstance(exit_code, int):
        return "success" if exit_code == 0 else "failed"
    return "success"


def _tool_exit_code(step: dict[str, Any]) -> int | None:
    extra = step.get("extra") if isinstance(step.get("extra"), dict) else {}
    tool_metadata = extra.get("tool_metadata") if isinstance(extra.get("tool_metadata"), dict) else {}
    exit_code = tool_metadata.get("exit_code")
    if isinstance(exit_code, int):
        return exit_code
    content = _observation_content(step)
    if "Process exited with code " not in content:
        return None
    try:
        return int(content.split("Process exited with code ", 1)[1].split(maxsplit=1)[0])
    except (ValueError, IndexError):
        return None


def _tool_duration_ms(step: dict[str, Any]) -> int | None:
    extra = step.get("extra") if isinstance(step.get("extra"), dict) else {}
    tool_metadata = extra.get("tool_metadata") if isinstance(extra.get("tool_metadata"), dict) else {}
    duration_seconds = tool_metadata.get("duration_seconds")
    if isinstance(duration_seconds, (int, float)):
        return int(duration_seconds * 1000)
    metadata = _tool_use_result(extra)
    duration_ms = metadata.get("durationMs") if isinstance(metadata, dict) else None
    if isinstance(duration_ms, (int, float)):
        return int(duration_ms)
    match = _WALL_TIME_RE.search(_observation_content(step))
    if match:
        return int(float(match.group(1)) * 1000)
    return None


def _tool_use_result(extra: dict[str, Any]) -> dict[str, Any]:
    for container_key in ("tool_result_metadata", "metadata"):
        container = extra.get(container_key)
        if isinstance(container, dict) and isinstance(container.get("tool_use_result"), dict):
            return container["tool_use_result"]
    return {}


def _raw_tool_result(extra: dict[str, Any]) -> dict[str, Any]:
    for container_key in ("tool_result_metadata", "metadata"):
        container = extra.get(container_key)
        if isinstance(container, dict) and isinstance(container.get("raw_tool_result"), dict):
            return container["raw_tool_result"]
    return {}


def _observation_content(step: dict[str, Any]) -> str:
    observation = step.get("observation") if isinstance(step.get("observation"), dict) else {}
    results = observation.get("results") if isinstance(observation.get("results"), list) else []
    chunks = []
    for result in results:
        if isinstance(result, dict) and isinstance(result.get("content"), str):
            chunks.append(result["content"])
    return "\n".join(chunks)


def _event_sort_key(event: dict[str, Any]) -> tuple[str, int, int]:
    phase_rank = {"started": 0, "completed": 1}
    return (
        str(event.get("timestamp") or ""),
        int(event.get("step_id") or 0),
        phase_rank.get(str(event.get("phase") or ""), 0),
    )


def normalize_mew_report(report_path: Path) -> list[dict[str, Any]]:
    history_path = report_path.parent / "implement_v2" / "history.json"
    if history_path.exists():
        events = normalize_mew_implement_v2_history(history_path=history_path, report_path=report_path)
        if events:
            return events

    report = _read_json(report_path)
    work_report = report.get("work_report") if isinstance(report.get("work_report"), dict) else {}
    steps = work_report.get("steps") if isinstance(work_report.get("steps"), list) else []
    events: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        action = step.get("action") if isinstance(step.get("action"), dict) else {}
        tool = str(action.get("type") or step.get("tool_call") or "work_step")
        event = _tool_event(
            agent="mew",
            source_path=report_path,
            line_number=step.get("index") if isinstance(step.get("index"), int) else None,
            phase="completed",
            tool=tool,
            tool_id=str(step.get("index", "")),
            summary=action.get("command") or action.get("summary") or step.get("summary") or action,
            status=step.get("status") or "",
        )
        model_turn = step.get("model_turn") if isinstance(step.get("model_turn"), dict) else {}
        metrics = model_turn.get("metrics") if isinstance(model_turn.get("metrics"), dict) else {}
        if metrics:
            event["model_metrics"] = metrics
        arguments = {
            key: action.get(key)
            for key in ("cmd", "command", "path", "query", "pattern")
            if action.get(key) not in (None, "", [], {})
        }
        if arguments:
            event["arguments"] = arguments
        if isinstance(action.get("reason"), str) and action.get("reason"):
            event["reason"] = _truncate(action.get("reason"))
        if isinstance(step.get("elapsed_ms"), int):
            event["elapsed_ms"] = step.get("elapsed_ms")
        execution_contract = action.get("execution_contract")
        if isinstance(execution_contract, dict):
            event["execution_contract"] = {
                key: execution_contract.get(key)
                for key in (
                    "purpose",
                    "stage",
                    "risk_class",
                    "proof_role",
                    "acceptance_kind",
                )
                if key in execution_contract
            }
        events.append(event)
    return events


def normalize_mew_implement_v2_history(*, history_path: Path, report_path: Path | None = None) -> list[dict[str, Any]]:
    turns = _read_json_list(history_path)
    if not turns:
        return []
    report = _read_json(report_path) if report_path is not None else {}
    start = _mew_report_start(report)
    elapsed_by_turn = _mew_observed_elapsed_by_turn(history_path.parent / "integration-observation.json")
    events: list[dict[str, Any]] = []
    for line_number, turn in enumerate(turns, 1):
        if not isinstance(turn, dict):
            continue
        turn_index = turn.get("turn") if isinstance(turn.get("turn"), int) else line_number
        turn_elapsed_ms = elapsed_by_turn.get(turn_index)
        turn_timestamp = start + dt.timedelta(milliseconds=turn_elapsed_ms) if start and turn_elapsed_ms is not None else None
        summary = turn.get("summary")
        if isinstance(summary, str) and summary:
            event = _base_event(
                agent="mew",
                source_path=history_path,
                line_number=line_number,
                kind="message",
                timestamp=turn_timestamp,
                elapsed_ms=turn_elapsed_ms,
                step_id=turn_index,
            )
            event["source_role"] = "agent"
            event["summary"] = _truncate(summary)
            events.append(event)

        results_by_id = {
            str(result.get("provider_call_id") or result.get("id") or ""): result
            for result in turn.get("tool_results", [])
            if isinstance(result, dict)
        }
        tool_calls = turn.get("tool_calls") if isinstance(turn.get("tool_calls"), list) else []
        for sequence_index, tool_call in enumerate(tool_calls, 1):
            if not isinstance(tool_call, dict):
                continue
            provider_call_id = str(tool_call.get("provider_call_id") or tool_call.get("id") or "")
            result = results_by_id.get(provider_call_id, {})
            events.extend(
                _events_from_mew_implement_v2_tool_call(
                    history_path=history_path,
                    line_number=line_number,
                    turn_index=turn_index,
                    sequence_index=sequence_index,
                    turn_elapsed_ms=turn_elapsed_ms,
                    start=start,
                    tool_call=tool_call,
                    result=result,
                )
            )
    events.sort(key=_event_sort_key)
    return events


def _mew_report_start(report: dict[str, Any]) -> dt.datetime | None:
    work_report = report.get("work_report") if isinstance(report.get("work_report"), dict) else {}
    steps = work_report.get("steps") if isinstance(work_report.get("steps"), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        model_turn = step.get("model_turn") if isinstance(step.get("model_turn"), dict) else {}
        for key in ("started_at", "created", "updated_at", "finished_at"):
            timestamp = _parse_timestamp(model_turn.get(key))
            if timestamp is not None:
                return timestamp
    return None


def _mew_observed_elapsed_by_turn(observation_path: Path) -> dict[int, int]:
    observation = _read_json(observation_path)
    turns = observation.get("turns") if isinstance(observation.get("turns"), list) else []
    elapsed_by_turn: dict[int, int] = {}
    cumulative_ms = 0
    for fallback_index, turn in enumerate(turns, 1):
        if not isinstance(turn, dict):
            continue
        elapsed_seconds = turn.get("elapsed_seconds")
        if isinstance(elapsed_seconds, (int, float)):
            cumulative_ms += max(0, int(elapsed_seconds * 1000))
        turn_index = turn.get("turn_index") if isinstance(turn.get("turn_index"), int) else fallback_index
        elapsed_by_turn[turn_index] = cumulative_ms
    return elapsed_by_turn


def _events_from_mew_implement_v2_tool_call(
    *,
    history_path: Path,
    line_number: int,
    turn_index: int,
    sequence_index: int,
    turn_elapsed_ms: int | None,
    start: dt.datetime | None,
    tool_call: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    tool = str(tool_call.get("tool_name") or result.get("tool_name") or "tool_call")
    tool_id = str(tool_call.get("provider_call_id") or result.get("provider_call_id") or "")
    arguments = tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {}
    content = result.get("content") if isinstance(result.get("content"), dict) else {}
    terminal_record = _mew_terminal_tool_run_record(content, tool_id)
    started_at = _parse_timestamp(terminal_record.get("started_at"))
    finished_at = _parse_timestamp(terminal_record.get("finished_at"))
    if started_at is None:
        started_at = _mew_content_timestamp(content, "started_at")
    if finished_at is None:
        finished_at = _mew_content_timestamp(content, "finished_at")
    started_elapsed = _elapsed_ms(started_at, start)
    finished_elapsed = _elapsed_ms(finished_at, start)
    if started_elapsed is None:
        started_elapsed = turn_elapsed_ms
    if finished_elapsed is None:
        finished_elapsed = turn_elapsed_ms

    summary = _mew_tool_summary(tool=tool, arguments=arguments, content=content)
    status = _mew_tool_result_status(result=result, terminal_record=terminal_record)
    exit_code = terminal_record.get("exit_code")
    duration_seconds = terminal_record.get("duration_seconds")
    duration_ms = int(duration_seconds * 1000) if isinstance(duration_seconds, (int, float)) else None
    started = _tool_event(
        agent="mew",
        source_path=history_path,
        line_number=line_number,
        phase="started",
        tool=tool,
        tool_id=tool_id,
        summary=summary,
        timestamp=started_at,
        elapsed_ms=started_elapsed,
        step_id=turn_index,
    )
    completed = _tool_event(
        agent="mew",
        source_path=history_path,
        line_number=line_number,
        phase="completed",
        tool=tool,
        tool_id=tool_id,
        summary=summary,
        status=status,
        exit_code=exit_code,
        timestamp=finished_at,
        elapsed_ms=finished_elapsed,
        step_id=turn_index,
        duration_ms=duration_ms,
    )
    compact_arguments = _compact_mew_tool_arguments(arguments)
    if compact_arguments:
        started["arguments"] = compact_arguments
        completed["arguments"] = compact_arguments
    if sequence_index:
        started["sequence_index"] = sequence_index
        completed["sequence_index"] = sequence_index
    execution_contract = arguments.get("execution_contract")
    if isinstance(execution_contract, dict):
        projected_contract = {
            key: execution_contract.get(key)
            for key in (
                "role",
                "purpose",
                "stage",
                "risk_class",
                "proof_role",
                "acceptance_kind",
                "expected_exit",
            )
            if key in execution_contract
        }
        started["execution_contract"] = projected_contract
        completed["execution_contract"] = projected_contract
    side_effects = content.get("side_effects") if isinstance(content.get("side_effects"), list) else []
    side_effect_kinds = [str(effect.get("kind")) for effect in side_effects if isinstance(effect, dict) and effect.get("kind")]
    if side_effect_kinds:
        completed["side_effect_kinds"] = side_effect_kinds
    return [started, completed]


def _mew_terminal_tool_run_record(content: dict[str, Any], provider_call_id: str) -> dict[str, Any]:
    side_effects = content.get("side_effects") if isinstance(content.get("side_effects"), list) else []
    records: list[dict[str, Any]] = []
    terminal_record_id = ""
    for effect in side_effects:
        if not isinstance(effect, dict):
            continue
        record = effect.get("record") if isinstance(effect.get("record"), dict) else {}
        if effect.get("kind") == "command_run" and not terminal_record_id:
            terminal_record_id = str(record.get("terminal_record_id") or "")
        if effect.get("kind") != "tool_run_record":
            continue
        if provider_call_id and record.get("provider_call_id") not in (None, provider_call_id):
            continue
        records.append(record)
    if terminal_record_id:
        for record in records:
            if record.get("record_id") == terminal_record_id:
                return record
    if records:
        return records[-1]
    items = content.get("content") if isinstance(content.get("content"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        if any(key in item for key in ("command_run_id", "duration_seconds", "exit_code", "started_at", "finished_at")):
            return item
    return {}


def _mew_content_timestamp(content: dict[str, Any], key: str) -> dt.datetime | None:
    items = content.get("content") if isinstance(content.get("content"), list) else []
    for item in items:
        if isinstance(item, dict):
            timestamp = _parse_timestamp(item.get(key))
            if timestamp is not None:
                return timestamp
    return None


def _mew_tool_result_status(*, result: dict[str, Any], terminal_record: dict[str, Any]) -> str:
    if terminal_record.get("status"):
        return str(terminal_record.get("status"))
    status = result.get("status")
    if isinstance(status, str) and status:
        return status
    if result.get("is_error") is True:
        return "failed"
    return "completed"


def _mew_tool_summary(*, tool: str, arguments: dict[str, Any], content: dict[str, Any]) -> Any:
    for key in ("cmd", "command", "path", "query", "pattern"):
        value = arguments.get(key)
        if value:
            return value
    items = content.get("content") if isinstance(content.get("content"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("summary", "operation", "path"):
            value = item.get(key)
            if value:
                return value
    return tool


def _compact_mew_tool_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in (
        "cmd",
        "command",
        "path",
        "query",
        "pattern",
        "foreground_budget_seconds",
        "timeout_seconds",
        "apply",
        "create",
    ):
        if arguments.get(key) not in (None, "", [], {}):
            compact[key] = arguments[key]
    for key in ("content", "old_string", "new_string"):
        value = arguments.get(key)
        if isinstance(value, str) and value:
            compact[f"{key}_chars"] = len(value)
    return compact


def normalize_harbor_agent_trace(
    *,
    agent: str,
    task_dir: Path,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    report_path: Path | None = None,
    transcript_path: Path | None = None,
    trajectory_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    agent = agent.lower().strip()
    task_dir = task_dir.resolve()
    if stdout_path is None:
        stdout_path = task_dir / "raw" / "stdout.jsonl"
    if stderr_path is None:
        stderr_path = task_dir / "raw" / "stderr.log"
    if report_path is None:
        report_path = task_dir / "mew-report.json"
    if transcript_path is None:
        transcript_path = task_dir / "command-transcript.json"
    if trajectory_path is None:
        trajectory_path = _resolve_default_path(
            task_dir / "agent" / "trajectory.json",
            task_dir / "trajectory.json",
        )

    if trajectory_path.exists() and agent in {"codex", "claude"}:
        events = normalize_atif_trajectory(agent=agent, trajectory_path=trajectory_path)
    elif agent == "codex":
        stdout_path = _resolve_default_path(stdout_path, task_dir / "agent" / "codex.txt", task_dir / "codex.txt")
        events = normalize_codex_stdout(stdout_path)
    elif agent == "claude":
        stdout_path = _resolve_default_path(
            stdout_path,
            task_dir / "agent" / "claude-code.txt",
            task_dir / "claude-code.txt",
        )
        events = normalize_claude_stdout(stdout_path)
    elif agent == "mew":
        events = normalize_mew_report(report_path)
    else:
        raise ValueError(f"unsupported agent trace kind: {agent}")

    transcript = _read_json(transcript_path)
    stderr_bytes = stderr_path.stat().st_size if stderr_path.exists() else 0
    summary = summarize_trace(agent=agent, events=events, transcript=transcript, stderr_bytes=stderr_bytes)
    return events, summary


def _resolve_default_path(primary: Path, *fallbacks: Path) -> Path:
    if primary.exists():
        return primary
    for fallback in fallbacks:
        if fallback.exists():
            return fallback
    return fallbacks[-1] if fallbacks else primary


def summarize_trace(
    *,
    agent: str,
    events: Sequence[dict[str, Any]],
    transcript: dict[str, Any] | None = None,
    stderr_bytes: int = 0,
) -> dict[str, Any]:
    transcript = transcript or {}
    tool_events = [event for event in events if event.get("kind") == "tool_call"]
    command_events = [
        event
        for event in tool_events
        if event.get("tool") in {"command_execution", "Bash", "run_command"} or "command" in str(event.get("tool", "")).lower()
    ]
    edit_events = [
        event
        for event in tool_events
        if any(token in str(event.get("tool", "")).lower() for token in ("edit", "patch", "write"))
    ]
    verifier_events = [
        event
        for event in tool_events
        if _is_verifier_event(event)
    ]
    command_invocations = _count_invocations(command_events)
    edit_invocations = _count_invocations(edit_events)
    verifier_invocations = _count_invocations(verifier_events)
    elapsed_values = [event.get("elapsed_ms") for event in events if isinstance(event.get("elapsed_ms"), int)]
    command_durations = [
        event.get("duration_ms")
        for event in command_events
        if event.get("phase") == "completed" and isinstance(event.get("duration_ms"), int)
    ]
    frontier_metrics = summarize_frontier_trace_metrics(events)
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "agent": agent,
        "event_count": len(events),
        "message_count": sum(1 for event in events if event.get("kind") == "message"),
        "tool_call_count": len(tool_events),
        "tool_call_started_count": sum(1 for event in tool_events if event.get("phase") == "started"),
        "tool_call_completed_count": sum(1 for event in tool_events if event.get("phase") == "completed"),
        "command_event_count": len(command_events),
        "command_count": command_invocations,
        "edit_event_count": len(edit_events),
        "edit_count": edit_invocations,
        "verifier_event_count": len(verifier_events),
        "verifier_count": verifier_invocations,
        "parse_error_count": sum(1 for event in events if event.get("kind") == "parse_error"),
        "stderr_bytes": stderr_bytes,
        "exit_code": transcript.get("exit_code"),
        "timed_out": transcript.get("timed_out"),
        "timeout_seconds": transcript.get("timeout_seconds"),
        "start_timestamp": _first_timestamp(events),
        "end_timestamp": _last_timestamp(events),
        "total_seconds": round(max(elapsed_values) / 1000, 3) if elapsed_values else None,
        "first_tool_seconds": _first_elapsed_seconds(tool_events),
        "first_command_seconds": _first_elapsed_seconds(command_events),
        "first_edit_seconds": _first_elapsed_seconds(edit_events),
        "first_verifier_seconds": _first_elapsed_seconds(verifier_events),
        "command_duration_seconds": round(sum(command_durations) / 1000, 3) if command_durations else None,
        "command_duration_observed_count": len(command_durations),
        **frontier_metrics,
    }


def _count_invocations(events: Sequence[dict[str, Any]]) -> int:
    started = sum(1 for event in events if event.get("phase") == "started")
    if started:
        return started
    return len(events)


def _is_verifier_event(event: dict[str, Any]) -> bool:
    execution_contract = event.get("execution_contract") if isinstance(event.get("execution_contract"), dict) else {}
    if str(execution_contract.get("proof_role") or "").casefold() in {"verifier", "acceptance", "proof"}:
        return True
    if str(execution_contract.get("acceptance_kind") or "").casefold():
        return True
    if str(execution_contract.get("stage") or "").casefold() in {"verify", "verification"}:
        return True
    summary = str(event.get("summary", "")).lower()
    if any(token in summary for token in ("pytest", "verifier", "verify", "cargo test", "npm test", "go test")):
        return True
    if "coqc" in summary and "--version" not in summary:
        return True
    return False


def _event_text(event: dict[str, Any]) -> str:
    chunks = []
    for key in ("summary", "message", "text", "tool", "action_type", "reason"):
        if event.get(key):
            chunks.append(str(event.get(key)))
    arguments = event.get("arguments") if isinstance(event.get("arguments"), dict) else {}
    for key in ("cmd", "command", "path", "query", "pattern"):
        if arguments.get(key):
            chunks.append(str(arguments.get(key)))
    return "\n".join(chunks).casefold()


def _event_elapsed_ms(event: dict[str, Any]) -> int | None:
    value = event.get("elapsed_ms")
    return value if isinstance(value, int) else None


def _event_command_text(event: dict[str, Any]) -> str:
    arguments = event.get("arguments") if isinstance(event.get("arguments"), dict) else {}
    for key in ("cmd", "command"):
        if arguments.get(key):
            return str(arguments.get(key)).casefold()
    return _event_text(event)


def _is_frontier_anchor_event(event: dict[str, Any]) -> bool:
    if event.get("kind") != "tool_call":
        return False
    tool = str(event.get("tool") or "").casefold()
    arguments = event.get("arguments") if isinstance(event.get("arguments"), dict) else {}
    if tool in {"read_file", "search_text"}:
        if tool == "read_file":
            return bool(arguments.get("path") or event.get("summary"))
        return bool(arguments.get("query") or arguments.get("pattern") or event.get("summary"))
    command = _event_command_text(event)
    return bool(re.search(r"(?:^|\s)(?:rg|grep|git grep|sed|awk)\b", command))


def _is_patch_event(event: dict[str, Any]) -> bool:
    if event.get("kind") != "tool_call":
        return False
    tool = str(event.get("tool") or "").casefold()
    text = _event_text(event)
    return any(token in tool for token in ("edit", "patch", "write")) or any(
        token in text for token in ("apply_patch", "edit_file", "write_file")
    )


def _is_same_frontier_broad_cycle_event(event: dict[str, Any]) -> bool:
    if event.get("kind") != "tool_call":
        return False
    if event.get("phase") not in (None, "", "completed"):
        return False
    model_metrics = event.get("model_metrics") if isinstance(event.get("model_metrics"), dict) else {}
    guard = model_metrics.get("active_compatibility_frontier_guard")
    if isinstance(guard, dict) and guard.get("blocked_action_kind") == "broad_verifier":
        return True
    tool = str(event.get("tool") or "").casefold()
    if tool == "run_tests":
        return True
    command = _event_command_text(event)
    execution_contract = event.get("execution_contract") if isinstance(event.get("execution_contract"), dict) else {}
    proof_role = str(execution_contract.get("proof_role") or "").casefold()
    if tool in {"run_command", "exec_command", "command_execution", "bash", "bashoutput"}:
        if proof_role in {"acceptance", "broad", "full_suite"}:
            return True
        return bool(
            re.search(
                r"(?:^|\s)(?:pytest|tox|nox|cargo\s+test|npm\s+test|pnpm\s+test|yarn\s+test|go\s+test|make|ninja)\b",
                command,
            )
        )
    return False


def summarize_frontier_trace_metrics(events: Sequence[dict[str, Any]]) -> dict[str, Any]:
    anchor_elapsed = [
        elapsed
        for event in events
        for elapsed in [_event_elapsed_ms(event)]
        if elapsed is not None and _is_frontier_anchor_event(event)
    ]
    first_anchor = min(anchor_elapsed) if anchor_elapsed else None
    first_patch = None
    if first_anchor is not None:
        patch_elapsed = [
            elapsed
            for event in events
            for elapsed in [_event_elapsed_ms(event)]
            if elapsed is not None and elapsed >= first_anchor and _is_patch_event(event)
        ]
        first_patch = min(patch_elapsed) if patch_elapsed else None
    broad_cycle_count = 0
    if first_anchor is not None:
        for event in events:
            elapsed = _event_elapsed_ms(event)
            if elapsed is None or elapsed < first_anchor:
                continue
            if first_patch is not None and elapsed > first_patch:
                continue
            if _is_same_frontier_broad_cycle_event(event):
                broad_cycle_count += 1
    return {
        "frontier_first_anchor_seconds": round(first_anchor / 1000, 3) if first_anchor is not None else None,
        "frontier_first_patch_seconds": round(first_patch / 1000, 3) if first_patch is not None else None,
        "time_from_first_anchor_to_first_patch_seconds": round((first_patch - first_anchor) / 1000, 3)
        if first_anchor is not None and first_patch is not None
        else None,
        "same_frontier_broad_cycle_count": broad_cycle_count,
    }


def _first_elapsed_seconds(events: Sequence[dict[str, Any]]) -> float | None:
    elapsed_values = [event.get("elapsed_ms") for event in events if isinstance(event.get("elapsed_ms"), int)]
    if not elapsed_values:
        return None
    return round(min(elapsed_values) / 1000, 3)


def _first_timestamp(events: Sequence[dict[str, Any]]) -> str | None:
    timestamps = [str(event["timestamp"]) for event in events if event.get("timestamp")]
    return min(timestamps) if timestamps else None


def _last_timestamp(events: Sequence[dict[str, Any]]) -> str | None:
    timestamps = [str(event["timestamp"]) for event in events if event.get("timestamp")]
    return max(timestamps) if timestamps else None


def write_normalized_trace(events: Sequence[dict[str, Any]], summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / "agent_trace.jsonl"
    with trace_path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize Harbor agent raw traces into a comparable JSONL schema.")
    parser.add_argument("--agent", required=True, choices=["mew", "codex", "claude"])
    parser.add_argument("--task-dir", required=True, type=Path)
    parser.add_argument("--stdout", type=Path, default=None)
    parser.add_argument("--stderr", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--transcript", type=Path, default=None)
    parser.add_argument("--trajectory", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print summary JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.out or (args.task_dir / "normalized-trace")
    events, summary = normalize_harbor_agent_trace(
        agent=args.agent,
        task_dir=args.task_dir,
        stdout_path=args.stdout,
        stderr_path=args.stderr,
        report_path=args.report,
        transcript_path=args.transcript,
        trajectory_path=args.trajectory,
    )
    write_normalized_trace(events, summary, output_dir)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(f"wrote {output_dir / 'agent_trace.jsonl'}")
        print(f"wrote {output_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
