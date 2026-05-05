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
    }


def _count_invocations(events: Sequence[dict[str, Any]]) -> int:
    started = sum(1 for event in events if event.get("phase") == "started")
    if started:
        return started
    return len(events)


def _is_verifier_event(event: dict[str, Any]) -> bool:
    summary = str(event.get("summary", "")).lower()
    if any(token in summary for token in ("pytest", "verifier", "verify", "cargo test", "npm test", "go test")):
        return True
    if "coqc" in summary and "--version" not in summary:
        return True
    return False


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
