from mew.implement_lane.tool_registry import CODEX_HOT_PATH_PROFILE_ID, MEW_LEGACY_PROFILE_ID
from mew.implement_lane.tool_result_renderer import (
    CODEX_APPLY_PATCH_RENDERER_ID,
    CODEX_FINISH_RENDERER_ID,
    CODEX_TERMINAL_RENDERER_ID,
    MEW_LEGACY_RENDERER_ID,
    render_observability_record,
    render_tool_result_for_profile,
)
from mew.implement_lane.types import ToolResultEnvelope


def _result(tool_name: str, status: str = "completed", **payload: object) -> ToolResultEnvelope:
    return ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id="mew-call-1",
        tool_name=tool_name,
        status=status,
        is_error=status in {"failed", "invalid", "interrupted"},
        content=(payload,),
        content_refs=("implement-v2-exec://attempt-1/run-1/output",) if payload.get("output_ref") else (),
    )


def test_mew_legacy_renderer_preserves_natural_result_text_exactly() -> None:
    result = _result("run_command", stdout_tail="ok\n", exit_code=0, status="completed")

    rendered = render_tool_result_for_profile(result, profile_id=MEW_LEGACY_PROFILE_ID)

    assert rendered.renderer_id == MEW_LEGACY_RENDERER_ID
    assert rendered.text == result.natural_result_text()


def test_codex_terminal_renderer_sanitizes_guidance_markers() -> None:
    result = _result(
        "exec_command",
        status="failed",
        reason="failure with suggested_next_action and required_next metadata",
    )

    rendered = render_tool_result_for_profile(result, profile_id=CODEX_HOT_PATH_PROFILE_ID)

    assert rendered.renderer_id == CODEX_TERMINAL_RENDERER_ID
    assert "Process exited with code 1" in rendered.text
    assert "suggested_next_action" not in rendered.text
    assert "required_next" not in rendered.text
    assert rendered.leak_ok is True


def test_codex_terminal_renderer_preserves_stdout_head_when_tail_exists() -> None:
    result = _result(
        "exec_command",
        stdout="first source fact /app/src/main.c\n" + ("middle disassembly\n" * 1000) + "final runtime fact\n",
        stdout_tail="final runtime fact\n",
        output_ref="exec://attempt-1/cmd-1/output",
        output_bytes=18_000,
        provider_visible_output_chars=1200,
    )

    rendered = render_tool_result_for_profile(result, profile_id=CODEX_HOT_PATH_PROFILE_ID)

    assert "first source fact /app/src/main.c" in rendered.text
    assert "final runtime fact" in rendered.text
    assert "output clipped" in rendered.text
    assert "Refs: output=implement-v2-exec://attempt-1/run-1/output" in rendered.text


def test_codex_terminal_renderer_preserves_separate_tail_for_head_clipped_stdout() -> None:
    result = _result(
        "exec_command",
        stdout="first source fact /app/src/main.c\n" + ("head-only probe line\n" * 80),
        stdout_tail="final verifier fact DG_DrawFrame wrote /tmp/frame.bmp\n",
        output_ref="exec://attempt-1/cmd-1/output",
        output_bytes=24_000,
        provider_visible_output_chars=1200,
    )

    rendered = render_tool_result_for_profile(result, profile_id=CODEX_HOT_PATH_PROFILE_ID)

    assert "first source fact /app/src/main.c" in rendered.text
    assert "final verifier fact DG_DrawFrame wrote /tmp/frame.bmp" in rendered.text
    assert "tail:" in rendered.text


def test_codex_terminal_renderer_preserves_head_and_tail_without_stdout_tail() -> None:
    result = _result(
        "exec_command",
        stdout="first path /app/doomgeneric/doomgeneric.c\n" + ("middle symbol row\n" * 1000) + "last symbol DG_DrawFrame\n",
        output_ref="exec://attempt-1/cmd-1/output",
        output_bytes=18_000,
        provider_visible_output_chars=1200,
    )

    rendered = render_tool_result_for_profile(result, profile_id=CODEX_HOT_PATH_PROFILE_ID)

    assert "first path /app/doomgeneric/doomgeneric.c" in rendered.text
    assert "last symbol DG_DrawFrame" in rendered.text
    assert "output clipped" in rendered.text


def test_codex_apply_patch_failure_is_bounded_and_sanitized() -> None:
    result = _result(
        "apply_patch",
        status="failed",
        reason="apply_patch input must start with *** Begin Patch; suggested_next_action=retry",
    )

    rendered = render_tool_result_for_profile(result, profile_id=CODEX_HOT_PATH_PROFILE_ID)

    assert rendered.renderer_id == CODEX_APPLY_PATCH_RENDERER_ID
    assert rendered.text.startswith("apply_patch failed:")
    assert "suggested_next_action" not in rendered.text
    assert rendered.leak_ok is True


def test_codex_finish_renderer_hides_resolver_internals() -> None:
    accepted = _result(
        "finish",
        summary="done",
        outcome="completed",
        completion_resolver={"lane_status": "completed", "reason": "ok"},
    )
    blocked = _result(
        "finish",
        status="invalid",
        summary="needs verifier",
        outcome="blocked",
        completion_resolver={"lane_status": "blocked", "reason": "missing proof"},
    )

    accepted_rendered = render_tool_result_for_profile(accepted, profile_id=CODEX_HOT_PATH_PROFILE_ID)
    blocked_rendered = render_tool_result_for_profile(blocked, profile_id=CODEX_HOT_PATH_PROFILE_ID)

    assert accepted_rendered.renderer_id == CODEX_FINISH_RENDERER_ID
    assert accepted_rendered.text == "finish accepted: done"
    assert blocked_rendered.text == "finish blocked: needs verifier"
    assert "completion_resolver" not in accepted_rendered.text + blocked_rendered.text


def test_render_observability_record_reads_profile_from_metrics_ref() -> None:
    rendered = render_tool_result_for_profile(
        _result("exec_command", stdout_tail="ok\n", exit_code=0),
        profile_id=CODEX_HOT_PATH_PROFILE_ID,
    )

    record = render_observability_record(
        metrics_ref=rendered.metrics_ref(lane_attempt_id="attempt-1", call_id="call-1"),
        tool_name="exec_command",
        call_id="call-1",
        output_text=rendered.text,
    )

    assert record["profile_id"] == CODEX_HOT_PATH_PROFILE_ID
    assert record["renderer_id"] == CODEX_TERMINAL_RENDERER_ID
    assert record["output_bytes"] == len(rendered.text.encode("utf-8"))
    assert record["leak_ok"] is True
