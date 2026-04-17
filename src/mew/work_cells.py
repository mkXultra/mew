import shlex

from .tasks import clip_output
from .timeutil import parse_time
from .work_session import (
    GIT_WORK_TOOLS,
    WRITE_WORK_TOOLS,
    clip_inline_text,
    compact_work_tool_summary,
    diff_line_counts,
    format_diff_preview,
)


COMMAND_CELL_TOOLS = {"run_command"} | GIT_WORK_TOOLS
TEST_CELL_TOOLS = {"run_tests"}
TAIL_MAX_LINES = 8
TAIL_MAX_CHARS = 1200


def _duration_seconds(started_at, finished_at):
    start = parse_time(started_at)
    finish = parse_time(finished_at)
    if not start or not finish:
        return None
    return max(0.0, (finish - start).total_seconds())


def _duration_text(started_at, finished_at):
    duration = _duration_seconds(started_at, finished_at)
    if duration is None:
        return ""
    return f"{duration:.1f}s"


def _cell_base(session, source, kind, source_id, status, started_at, finished_at, preview):
    session_id = (session or {}).get("id")
    return {
        "id": f"s{session_id}:{kind}:{source_id}",
        "kind": kind,
        "status": status or "unknown",
        "started_at": started_at or "",
        "finished_at": finished_at or "",
        "preview": clip_inline_text(preview, 240),
        "detail": "",
        "tail": [],
        "source": source,
        "source_id": source_id,
        "session_id": session_id,
        "task_id": (session or {}).get("task_id"),
    }


def _action_type(action):
    return (action or {}).get("type") or (action or {}).get("tool") or "unknown"


def _model_turn_preview(turn):
    action = turn.get("action") or {}
    action_type = _action_type(action)
    summary = turn.get("finished_note") or turn.get("summary") or turn.get("error") or ""
    if summary:
        return f"{action_type}: {summary}"
    return action_type


def _model_turn_detail(turn):
    lines = []
    guidance = (turn.get("guidance_snapshot") or "").strip()
    if guidance:
        lines.append(f"guidance: {clip_inline_text(guidance, 240)}")
    tool_call_ids = turn.get("tool_call_ids") or []
    if tool_call_ids:
        lines.append("tool_calls: " + ",".join(f"#{value}" for value in tool_call_ids))
    elif turn.get("tool_call_id"):
        lines.append(f"tool_call: #{turn.get('tool_call_id')}")
    if turn.get("question_id"):
        lines.append(f"question: #{turn.get('question_id')}")
    if turn.get("outbox_message_id"):
        lines.append(f"message: #{turn.get('outbox_message_id')}")
    if turn.get("work_note"):
        note = turn.get("work_note") or {}
        lines.append(f"note: {clip_inline_text(note.get('text'), 240)}")
    if turn.get("error"):
        lines.append(f"error: {clip_inline_text(turn.get('error'), 240)}")
    return "\n".join(lines)


def model_turn_cell(session, turn):
    cell = _cell_base(
        session,
        "model_turn",
        "model_turn",
        turn.get("id"),
        turn.get("status"),
        turn.get("started_at"),
        turn.get("finished_at"),
        _model_turn_preview(turn),
    )
    cell["detail"] = _model_turn_detail(turn)
    return cell


def _command_result(call):
    return (call or {}).get("result") or {}


def _command_text(call):
    result = _command_result(call)
    parameters = (call or {}).get("parameters") or {}
    return result.get("command") or parameters.get("command") or (call or {}).get("tool") or ""


def _exit_text(result):
    if "exit_code" not in (result or {}):
        return ""
    exit_code = result.get("exit_code")
    return f"exit={exit_code if exit_code is not None else 'unavailable'}"


def _tail_lines(text, max_lines=TAIL_MAX_LINES, max_chars=TAIL_MAX_CHARS):
    text = str(text or "")
    if not text:
        return []
    clipped = clip_output(text, max_chars)
    lines = clipped.splitlines()
    if len(lines) > max_lines:
        lines = ["[...snip...]"] + lines[-max_lines:]
    return lines


def _command_tail(result):
    tail = []
    for stream in ("stdout", "stderr"):
        lines = _tail_lines((result or {}).get(stream) or "")
        if lines:
            tail.append({"stream": stream, "lines": lines})
    return tail


def _line_count(text):
    text = str(text or "")
    if not text:
        return 0
    return len(text.splitlines())


def _stream_metric(stream, text):
    text = str(text or "")
    return f"{stream}: {_line_count(text)} lines {len(text)} chars"


def _command_cell_kind(tool):
    if tool in TEST_CELL_TOOLS:
        return "test"
    if tool in COMMAND_CELL_TOOLS:
        return "command"
    return "tool_call"


def _command_preview(call):
    tool = call.get("tool") or "unknown"
    result = _command_result(call)
    command = _command_text(call)
    parts = [tool]
    exit_text = _exit_text(result)
    if exit_text:
        parts.append(exit_text)
    duration = _duration_text(call.get("started_at"), call.get("finished_at"))
    if duration:
        parts.append(f"duration={duration}")
    if command:
        parts.append(command)
    return " ".join(parts)


def _command_detail(session, call, kind):
    result = _command_result(call)
    parameters = (call or {}).get("parameters") or {}
    lines = []
    command = _command_text(call)
    if command:
        lines.append(f"command: {command}")
    cwd = result.get("cwd") or parameters.get("cwd")
    if cwd:
        lines.append(f"cwd: {cwd}")
    exit_text = _exit_text(result)
    if exit_text:
        lines.append(exit_text)
    if result.get("timed_out"):
        lines.append("timeout: yes")
    if result.get("error_type"):
        lines.append(f"error_type: {result.get('error_type')}")
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    if stdout or stderr:
        lines.append(_stream_metric("stdout", stdout))
        lines.append(_stream_metric("stderr", stderr))
    elif call.get("status") == "completed":
        lines.append("output: (no output)")
    task_id = (session or {}).get("task_id")
    pane = "--tests" if kind == "test" else "--commands"
    task_part = f" {task_id}" if task_id is not None else ""
    lines.append(f"full_output: mew work{task_part} {pane}")
    if call.get("error"):
        lines.append(f"error: {clip_inline_text(call.get('error'), 240)}")
    return "\n".join(lines)


def command_or_test_cell(session, call):
    tool = call.get("tool") or "unknown"
    kind = _command_cell_kind(tool)
    cell = _cell_base(
        session,
        "tool_call",
        kind,
        call.get("id"),
        call.get("status"),
        call.get("started_at"),
        call.get("finished_at"),
        _command_preview(call),
    )
    cell["detail"] = _command_detail(session, call, kind)
    cell["tail"] = _command_tail(_command_result(call))
    if not cell["tail"] and call.get("status") == "completed":
        cell["tail"] = [{"stream": "output", "lines": ["(no output)"]}]
    return cell


def _tool_preview(call):
    tool = call.get("tool") or "unknown"
    summary = compact_work_tool_summary(call) or call.get("summary") or call.get("error") or ""
    if summary:
        return f"{tool}: {summary}"
    return tool


def _tool_detail(call):
    parameters = call.get("parameters") or {}
    details = []
    for key in (
        "path",
        "query",
        "pattern",
        "base",
        "staged",
        "stat",
        "offset",
        "line_start",
        "line_count",
        "max_chars",
        "max_matches",
    ):
        value = parameters.get(key)
        if value not in (None, "", False):
            details.append(f"{key}: {clip_inline_text(value, 200)}")
    if call.get("error"):
        details.append(f"error: {clip_inline_text(call.get('error'), 240)}")
    return "\n".join(details)


def tool_call_cell(session, call):
    cell = _cell_base(
        session,
        "tool_call",
        "tool_call",
        call.get("id"),
        call.get("status"),
        call.get("started_at"),
        call.get("finished_at"),
        _tool_preview(call),
    )
    cell["detail"] = _tool_detail(call)
    return cell


def diff_cell(session, call):
    result = call.get("result") or {}
    parameters = call.get("parameters") or {}
    path = result.get("path") or parameters.get("path") or ""
    stats = result.get("diff_stats") or diff_line_counts(result.get("diff") or "")
    preview = (
        f"{call.get('tool') or 'write'} {path} "
        f"+{stats.get('added', 0)} -{stats.get('removed', 0)}"
    ).strip()
    cell = _cell_base(
        session,
        "tool_call",
        "diff",
        call.get("id"),
        call.get("status"),
        call.get("started_at"),
        call.get("finished_at"),
        preview,
    )
    cell["detail"] = format_diff_preview(
        result.get("diff") or "",
        max_chars=1200,
        diff_stats=result.get("diff_stats"),
    )
    return cell


def has_pending_write_approval(call):
    if (call or {}).get("tool") not in WRITE_WORK_TOOLS:
        return False
    result = (call or {}).get("result") or {}
    if not result.get("dry_run") or not result.get("changed"):
        return False
    return (call or {}).get("approval_status") not in ("applying", "applied", "rejected")


def approval_cell(session, call):
    result = call.get("result") or {}
    parameters = call.get("parameters") or {}
    path = result.get("path") or parameters.get("path") or ""
    task_ref = (session or {}).get("task_id") or "<task-id>"
    write_root = shlex.quote(path or "<path>")
    preview = f"approval needed for {call.get('tool')} #{call.get('id')} {path}".strip()
    cell = _cell_base(
        session,
        "tool_call",
        "approval",
        call.get("id"),
        "pending",
        call.get("finished_at") or call.get("started_at"),
        "",
        preview,
    )
    cell["detail"] = "\n".join(
        line
        for line in (
            f"path: {path}" if path else "",
            "dry_run: true",
            f"approve_once: mew work {task_ref} --approve-tool "
            f"{call.get('id')} --allow-write {write_root} --allow-verify --verify-command <cmd>",
            f"reject: mew work {task_ref} --reject-tool {call.get('id')}",
        )
        if line
    )
    return cell


def cells_for_tool_call(session, call):
    tool = call.get("tool") or ""
    cells = []
    if tool in COMMAND_CELL_TOOLS or tool in TEST_CELL_TOOLS:
        cells.append(command_or_test_cell(session, call))
    elif tool in WRITE_WORK_TOOLS and (call.get("result") or {}).get("diff"):
        cells.append(diff_cell(session, call))
    else:
        cells.append(tool_call_cell(session, call))
    if has_pending_write_approval(call):
        cells.append(approval_cell(session, call))
    return cells


def _cell_sort_key(index, cell):
    return (
        cell.get("started_at") or cell.get("finished_at") or "",
        index,
    )


def build_work_session_cells(session, limit=20):
    if not session:
        return []
    cells = []
    order = 0
    for turn in session.get("model_turns") or []:
        order += 1
        cells.append((order, model_turn_cell(session, turn)))
    for call in session.get("tool_calls") or []:
        for cell in cells_for_tool_call(session, call):
            order += 1
            cells.append((order, cell))
    cells.sort(key=lambda item: _cell_sort_key(item[0], item[1]))
    rendered = [cell for _order, cell in cells]
    if limit is None:
        return rendered
    count = max(0, int(limit))
    if count == 0:
        return []
    return rendered[-count:]


def format_work_cells(cells, header="Work cells"):
    lines = [header] if header else []
    cells = list(cells or [])
    if not cells:
        lines.append("(none)")
        return "\n".join(lines)
    for cell in cells:
        time_text = cell.get("started_at") or cell.get("finished_at") or ""
        elapsed = _duration_text(cell.get("started_at"), cell.get("finished_at"))
        prefix = f"- {cell.get('kind')} [{cell.get('status')}]"
        preview = cell.get("preview") or ""
        lines.append(f"{prefix} {preview}".rstrip())
        if cell.get("id"):
            lines.append(f"  id: {cell.get('id')}")
        if elapsed:
            lines.append(f"  elapsed: {elapsed}")
        if time_text:
            lines.append(f"  started_at: {time_text}")
        detail = cell.get("detail") or ""
        for detail_line in detail.splitlines():
            if detail_line.strip():
                lines.append(f"  {detail_line}")
        for tail in cell.get("tail") or []:
            stream = tail.get("stream") or "output"
            tail_lines = tail.get("lines") or []
            lines.append(f"  {stream}_tail:")
            lines.extend(f"    {line}" for line in tail_lines)
    return "\n".join(lines)


def format_work_session_cells(session, task=None, limit=20, header=None):
    if not session:
        return "No active work session."
    title = (session or {}).get("title") or (task or {}).get("title") or ""
    task_id = session.get("task_id")
    task_text = f" task=#{task_id}" if task_id is not None else ""
    default_header = f"Work cells #{session.get('id')} [{session.get('status')}]{task_text}"
    lines = [header or default_header]
    if title:
        lines.append(f"title: {title}")
    cell_text = format_work_cells(build_work_session_cells(session, limit=limit), header="")
    if cell_text:
        lines.append(cell_text)
    return "\n".join(lines)
