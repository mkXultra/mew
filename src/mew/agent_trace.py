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
    native_transcript_path = report_path.parent / "response_transcript.json"
    if native_transcript_path.exists():
        report = _read_json(report_path)
        events = normalize_mew_native_response_transcript(
            transcript_path=native_transcript_path,
            manifest_path=report_path.parent / "proof-manifest.json",
            report_metrics=_mew_implement_lane_metrics(report),
        )
        if events:
            return events

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


def normalize_mew_native_response_transcript(
    *,
    transcript_path: Path,
    manifest_path: Path | None = None,
    report_metrics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    transcript = _read_json(transcript_path)
    items = transcript.get("items") if isinstance(transcript.get("items"), list) else []
    if not items:
        return []
    manifest = _read_json(manifest_path or transcript_path.parent / "proof-manifest.json")
    latency_by_call = _native_latency_by_call(manifest, report_metrics=report_metrics or {})
    output_by_call, pairing_errors = _native_output_by_call(items)
    call_tool_names = {
        str(item.get("call_id")): str(item.get("tool_name") or "")
        for item in items
        if isinstance(item, dict)
        and item.get("kind") in {"function_call", "custom_tool_call", "finish_call"}
        and item.get("call_id")
    }
    source_mutation_by_call = _native_source_mutation_by_call(
        transcript_path.parent,
        call_tool_names=call_tool_names,
    )
    events: list[dict[str, Any]] = []
    for message in pairing_errors:
        events.append(_native_parse_error_event(transcript_path, line_number=1, summary=message))
    call_index = 0
    seen_call_ids: set[str] = set()
    for line_number, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        if kind not in {"function_call", "custom_tool_call", "finish_call"}:
            if kind in {"message", "reasoning"}:
                event = _base_event(
                    agent="mew",
                    source_path=transcript_path,
                    line_number=line_number,
                    kind="message",
                    step_id=_native_turn_index(item),
                )
                event["source_role"] = "agent"
                event["summary"] = kind
                events.append(event)
            continue
        call_index += 1
        tool = str(item.get("tool_name") or ("finish" if kind == "finish_call" else "tool_call"))
        call_id = str(item.get("call_id") or item.get("provider_item_id") or f"native-call-{call_index}")
        duplicate_call = call_id in seen_call_ids
        if duplicate_call:
            events.append(
                _native_parse_error_event(
                    transcript_path,
                    line_number=line_number,
                    summary=f"duplicate native tool call for call_id={call_id}",
                )
            )
        seen_call_ids.add(call_id)
        arguments, argument_error = _native_arguments(item)
        if argument_error:
            events.append(_native_parse_error_event(transcript_path, line_number=line_number, summary=argument_error))
        output = {} if duplicate_call else output_by_call.get(call_id, {})
        latency = latency_by_call.get(call_id, {})
        started_ms = _int_or_none(latency.get("started_ms"))
        duration_ms = _int_or_none(latency.get("finished_ms"))
        completed_ms = started_ms + duration_ms if started_ms is not None and duration_ms is not None else started_ms
        summary = _native_tool_summary(tool=tool, arguments=arguments, output=output)
        status = str(output.get("status") or "")
        exit_code = _native_exit_code(output)
        turn_index = _native_turn_index(item)
        started = _tool_event(
            agent="mew",
            source_path=transcript_path,
            line_number=line_number,
            phase="started",
            tool=tool,
            tool_id=call_id,
            summary=summary,
            elapsed_ms=started_ms,
            step_id=turn_index,
        )
        completed = _tool_event(
            agent="mew",
            source_path=transcript_path,
            line_number=line_number,
            phase="completed",
            tool=tool,
            tool_id=call_id,
            summary=summary,
            status=status,
            exit_code=exit_code,
            elapsed_ms=completed_ms,
            step_id=turn_index,
            duration_ms=duration_ms,
        )
        compact_arguments = _compact_mew_tool_arguments(arguments)
        if compact_arguments:
            started["arguments"] = compact_arguments
            completed["arguments"] = compact_arguments
        if item.get("output_index") is not None:
            started["sequence_index"] = item.get("output_index")
            completed["sequence_index"] = item.get("output_index")
        source_mutation = source_mutation_by_call.get(call_id, {})
        if source_mutation:
            completed["source_mutation"] = source_mutation
            effect_kinds = source_mutation.get("effect_kinds")
            if isinstance(effect_kinds, list) and effect_kinds:
                completed["source_mutation_effect_kinds"] = effect_kinds
                completed["side_effect_kinds"] = effect_kinds
        events.append(started)
        if output:
            events.append(completed)
        else:
            events.append(
                _native_parse_error_event(
                    transcript_path,
                    line_number=line_number,
                    summary=f"missing native tool output for call_id={call_id}",
                )
            )
    events.sort(key=_event_sort_key)
    return events


def _native_output_by_call(items: list[Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    call_ids: list[str] = []
    call_kind_by_id: dict[str, str] = {}
    output_by_call_candidate: dict[str, dict[str, Any]] = {}
    output_kind_by_id: dict[str, str] = {}
    output_by_call: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        call_id = str(item.get("call_id") or "")
        if kind in {"function_call", "custom_tool_call", "finish_call"}:
            if not call_id:
                errors.append("native tool call is missing call_id")
                continue
            if call_id in call_ids:
                errors.append(f"duplicate native tool call for call_id={call_id}")
                continue
            call_ids.append(call_id)
            call_kind_by_id[call_id] = kind
            continue
        if kind not in {"function_call_output", "custom_tool_call_output", "finish_output"}:
            continue
        if not call_id:
            errors.append("native tool output is missing call_id")
            continue
        if call_id in output_by_call_candidate:
            errors.append(f"duplicate native tool output for call_id={call_id}")
            continue
        output_by_call_candidate[call_id] = item
        output_kind_by_id[call_id] = kind
    call_id_set = set(call_ids)
    output_id_set = set(output_by_call_candidate)
    for call_id in sorted(output_id_set - call_id_set):
        errors.append(f"orphan native tool output for call_id={call_id}")
    for call_id in sorted(call_id_set - output_id_set):
        errors.append(f"missing native tool output for call_id={call_id}")
    expected_output_kind = {
        "function_call": "function_call_output",
        "custom_tool_call": "custom_tool_call_output",
        "finish_call": "finish_output",
    }
    for call_id in sorted(call_id_set & output_id_set):
        call_kind = call_kind_by_id[call_id]
        output_kind = output_kind_by_id[call_id]
        if output_kind != expected_output_kind[call_kind]:
            errors.append(f"native tool call/output kind mismatch for call_id={call_id}")
            continue
        output_by_call[call_id] = output_by_call_candidate[call_id]
    return output_by_call, errors


def _native_source_mutation_by_call(
    artifact_root: Path,
    *,
    call_tool_names: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """Return sidecar-observed source mutations keyed by provider call id."""

    index = _read_json(artifact_root / "tool_result_index.json")
    by_call = index.get("by_provider_call_id") if isinstance(index.get("by_provider_call_id"), dict) else {}
    result: dict[str, dict[str, Any]] = {}
    for call_id, payload in by_call.items():
        transcript_tool_name = call_tool_names.get(str(call_id))
        if transcript_tool_name is None:
            continue
        if not isinstance(payload, dict):
            continue
        card = payload.get("compact_result_card") if isinstance(payload.get("compact_result_card"), dict) else {}
        indexed_tool_name = str(payload.get("tool_name") or card.get("tool_name") or "")
        if indexed_tool_name and indexed_tool_name != transcript_tool_name:
            continue
        changed_paths = _strings_from_any(payload.get("changed_paths"))
        if not changed_paths:
            changed_paths = _strings_from_any(card.get("changed_paths")) if isinstance(card, dict) else []
        mutation_refs = _strings_from_any(payload.get("mutation_refs"))
        if not mutation_refs:
            mutation_refs = _strings_from_any(card.get("mutation_refs")) if isinstance(card, dict) else []
        effect_kinds = _strings_from_any(payload.get("source_mutation_effect_kinds"))
        if not effect_kinds and isinstance(card, dict):
            effect_kinds = _strings_from_any(card.get("source_mutation_effect_kinds"))
        changed_count = len(changed_paths)
        if not changed_count and (mutation_refs or effect_kinds):
            changed_count = 1
        if changed_count <= 0:
            continue
        effect_kind_set = {str(item) for item in effect_kinds}
        if "process_source_observation" in effect_kind_set:
            if transcript_tool_name not in {"run_command", "run_tests"}:
                continue
        elif effect_kind_set & {"file_write", "source_tree_mutation"}:
            if transcript_tool_name not in {"write_file", "edit_file", "apply_patch"}:
                continue
        elif transcript_tool_name not in {"write_file", "edit_file", "apply_patch"}:
            continue
        result[str(call_id)] = {
            "changed_count": changed_count,
            "changed_paths": changed_paths,
            "mutation_refs": mutation_refs,
            "effect_kinds": effect_kinds,
            "source": "tool_result_index.json",
        }
    return result


def _strings_from_any(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _native_parse_error_event(source_path: Path, *, line_number: int, summary: str) -> dict[str, Any]:
    event = _base_event(
        agent="mew",
        source_path=source_path,
        line_number=line_number,
        kind="parse_error",
    )
    event["summary"] = summary
    return event


def _native_latency_by_call(manifest: dict[str, Any], *, report_metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    latencies = metrics.get("tool_latency") if isinstance(metrics.get("tool_latency"), list) else []
    if not latencies:
        latencies = report_metrics.get("tool_latency") if isinstance(report_metrics.get("tool_latency"), list) else []
    return {
        str(item.get("call_id") or ""): item
        for item in latencies
        if isinstance(item, dict) and item.get("call_id")
    }


def _mew_implement_lane_metrics(report: dict[str, Any]) -> dict[str, Any]:
    work_report = report.get("work_report") if isinstance(report.get("work_report"), dict) else {}
    result = work_report.get("implement_lane_result") if isinstance(work_report.get("implement_lane_result"), dict) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    return dict(metrics)


def _native_arguments(item: dict[str, Any]) -> tuple[dict[str, Any], str]:
    raw = item.get("arguments_json_text")
    if not isinstance(raw, str) or not raw:
        return {}, ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}, "invalid native tool arguments JSON"
    if not isinstance(payload, dict):
        return {}, "native tool arguments JSON is not an object"
    return payload, ""


def _native_turn_index(item: dict[str, Any]) -> int | None:
    turn_id = str(item.get("turn_id") or "")
    try:
        return int(turn_id.rsplit("-", 1)[-1])
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _native_exit_code(output: dict[str, Any]) -> int | None:
    text = str(output.get("output_text_or_ref") or "")
    match = re.search(r"\bexit_code=(-?\d+)\b", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _native_tool_summary(*, tool: str, arguments: dict[str, Any], output: dict[str, Any]) -> Any:
    for key in ("command", "cmd", "path", "query", "pattern"):
        value = arguments.get(key)
        if value:
            return value
    text = str(output.get("output_text_or_ref") or "")
    if text:
        return text
    return tool


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
        if event.get("tool") in {"command_execution", "exec_command", "Bash", "run_command", "run_tests"}
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
    source_mutation_events = [event for event in tool_events if _event_has_source_mutation(event)]
    process_source_mutation_events = [
        event for event in source_mutation_events if _event_has_source_mutation_kind(event, "process_source_observation")
    ]
    source_mutation_invocations = _count_invocations(source_mutation_events)
    process_source_mutation_invocations = _count_invocations(process_source_mutation_events)
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
        "typed_edit_count": edit_invocations,
        "source_mutation_event_count": len(source_mutation_events),
        "source_mutation_count": source_mutation_invocations,
        "process_source_mutation_event_count": len(process_source_mutation_events),
        "process_source_mutation_count": process_source_mutation_invocations,
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
        "first_source_mutation_seconds": _first_elapsed_seconds(source_mutation_events),
        "first_process_source_mutation_seconds": _first_elapsed_seconds(process_source_mutation_events),
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
    if str(event.get("tool") or "").casefold() in {"run_tests", "verifier", "strict_verifier"}:
        return True
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


def _event_has_source_mutation(event: dict[str, Any]) -> bool:
    mutation = event.get("source_mutation")
    if isinstance(mutation, dict):
        changed_count = mutation.get("changed_count")
        try:
            if int(changed_count) > 0:
                return True
        except (TypeError, ValueError):
            pass
        if mutation.get("changed_paths") or mutation.get("mutation_refs"):
            return True
    return _event_has_source_mutation_kind(event, "source_tree_mutation") or _event_has_source_mutation_kind(
        event,
        "process_source_observation",
    )


def _event_has_source_mutation_kind(event: dict[str, Any], kind: str) -> bool:
    kinds = event.get("source_mutation_effect_kinds") or event.get("side_effect_kinds")
    if not isinstance(kinds, list):
        return False
    return kind in {str(item) for item in kinds}


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
