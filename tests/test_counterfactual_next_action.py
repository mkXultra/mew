from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from mew.implement_lane.decision_replay import (
    ask_counterfactual_next_action_model,
    build_counterfactual_next_action_packet,
    counterfactual_next_action_prompt,
    write_counterfactual_next_action_artifacts,
)

ROOT = Path(__file__).resolve().parents[1]


def test_counterfactual_packet_builds_without_model_call(tmp_path: Path) -> None:
    artifact = _write_artifact(
        tmp_path,
        items=[
            {
                "sequence": 1,
                "kind": "function_call",
                "tool_name": "exec_command",
                "arguments_json_text": json.dumps({"cmd": "make"}),
            },
            {
                "sequence": 2,
                "kind": "function_call_output",
                "tool_name": "exec_command",
                "output_text_or_ref": "ld: cannot find -lSDL2",
                "is_error": True,
            },
            {
                "sequence": 3,
                "kind": "function_call",
                "tool_name": "exec_command",
                "arguments_json_text": json.dumps({"cmd": "pkg-config --libs sdl2"}),
            },
        ],
    )

    packet = build_counterfactual_next_action_packet(
        artifact,
        decision_sequence=3,
        context_items=2,
        counterfactual_instructions=(
            "After linker failure, inspect dependency discovery before editing build files.",
        ),
        expected_good=("shell_command",),
        expected_bad=("workspace_mutation",),
    )

    assert packet["diagnostic"] == "counterfactual_next_action"
    assert packet["selected_sequence"] == 3
    assert packet["original_decision"]["tool_name"] == "exec_command"
    assert packet["original_decision"]["command_or_patch_summary"] == "pkg-config --libs sdl2"
    assert packet["original_decision"]["category"] == "shell_command"
    assert packet["expected_good_categories"] == ["shell_command"]
    assert packet["expected_bad_categories"] == ["workspace_mutation"]
    assert packet["counterfactual_prompt_digest"].startswith("sha256:")


def test_counterfactual_prompt_includes_context_and_instructions(tmp_path: Path) -> None:
    artifact = _write_artifact(
        tmp_path,
        instructions="existing system instruction",
        input_text="fix the C build",
        items=[
            {
                "sequence": 5,
                "kind": "function_call_output",
                "tool_name": "exec_command",
                "output_text_or_ref": "undefined reference to init_graphics",
            },
            {
                "sequence": 6,
                "kind": "custom_tool_call",
                "tool_name": "apply_patch",
                "custom_input_text": "*** Begin Patch\n*** Update File: Makefile\n",
            },
            {
                "sequence": 7,
                "kind": "function_call_output",
                "tool_name": "apply_patch",
                "output_text_or_ref": "POST_DECISION_ONLY: later patch failed",
                "is_error": True,
            },
        ],
    )

    packet = build_counterfactual_next_action_packet(
        artifact,
        decision_sequence=6,
        counterfactual_instructions=("Prefer inspecting link flags before patching.",),
        analysis_question="Would the next action still patch the Makefile?",
    )
    prompt = counterfactual_next_action_prompt(packet)

    assert "existing system instruction" in prompt
    assert "fix the C build" in prompt
    assert "undefined reference to init_graphics" in prompt
    assert "Prefer inspecting link flags before patching." in prompt
    assert "Would the next action still patch the Makefile?" in prompt
    assert "context_after_decision" not in packet
    assert "POST_DECISION_ONLY" not in prompt
    assert "Do not provide hidden chain-of-thought" in prompt
    assert "predicted_next_action" in prompt


def test_counterfactual_write_artifacts_writes_prompt_only(tmp_path: Path) -> None:
    artifact = _write_artifact(
        tmp_path,
        items=[
            {
                "sequence": 9,
                "kind": "custom_tool_call",
                "tool_name": "apply_patch",
                "custom_input_text": "*** Begin Patch\n*** Add File: build.sh\n",
            },
        ],
    )
    out_prompt = tmp_path / "counterfactual.prompt.txt"

    packet = write_counterfactual_next_action_artifacts(
        artifact,
        out_prompt=out_prompt,
        counterfactual_instructions=("Always inspect existing build scripts first.",),
    )

    assert packet["selected_sequence"] == 9
    assert out_prompt.exists()
    assert "Always inspect existing build scripts first." in out_prompt.read_text(encoding="utf-8")


def test_ask_counterfactual_model_uses_decision_replay_backend_path(monkeypatch, tmp_path: Path) -> None:
    calls = {}

    def fake_load_model_auth(model_backend: str, auth_path: str) -> dict[str, str]:
        calls["auth"] = (model_backend, auth_path)
        return {"access_token": "token"}

    def fake_model_backend_default_base_url(model_backend: str) -> str:
        calls["default_base_url"] = model_backend
        return "https://example.invalid/codex"

    def fake_call_model_json(
        model_backend: str,
        auth: dict[str, str],
        prompt: str,
        model: str,
        base_url: str,
        timeout: float,
    ) -> dict[str, object]:
        calls["call"] = {
            "model_backend": model_backend,
            "auth": auth,
            "prompt": prompt,
            "model": model,
            "base_url": base_url,
            "timeout": timeout,
        }
        return {
            "predicted_next_action": {
                "tool_name": "exec_command",
                "command_or_patch_summary": "pkg-config --libs sdl2",
                "target_paths": [],
                "category": "shell_command",
            },
            "expected_category_match": "good",
            "likely_effect": "The next action would remain dependency inspection.",
            "evidence_from_context": ["linker failure"],
            "confidence": "medium",
        }

    monkeypatch.setattr(
        "mew.implement_lane.decision_replay.load_model_auth",
        fake_load_model_auth,
    )
    monkeypatch.setattr(
        "mew.implement_lane.decision_replay.model_backend_default_base_url",
        fake_model_backend_default_base_url,
    )
    monkeypatch.setattr(
        "mew.implement_lane.decision_replay.call_model_json",
        fake_call_model_json,
    )

    auth_json = tmp_path / "auth.json"
    packet = {
        "selected_sequence": 3,
        "original_decision": {"tool_name": "exec_command"},
        "counterfactual_prompt_digest": "sha256:abc",
    }
    result = ask_counterfactual_next_action_model(packet, auth_json=auth_json)

    assert result["selected_sequence"] == 3
    assert result["original_decision"] == {"tool_name": "exec_command"}
    assert result["counterfactual_prompt_digest"] == "sha256:abc"
    assert result["expected_category_match"] == "good"
    assert calls["auth"] == ("codex", str(auth_json))
    assert calls["default_base_url"] == "codex"
    assert calls["call"]["model"] == "gpt-5.5"
    assert calls["call"]["base_url"] == "https://example.invalid/codex"
    assert calls["call"]["timeout"] == 180.0
    assert "PACKET:" in calls["call"]["prompt"]


def test_counterfactual_cli_parser_accepts_required_arguments(tmp_path: Path) -> None:
    module = _load_counterfactual_cli_module()

    args = module.build_parser().parse_args(
        [
            "--mew-artifact-root",
            str(tmp_path / "artifact"),
            "--decision-sequence",
            "11",
            "--context-items",
            "4",
            "--counterfactual-instruction",
            "Inspect linker flags first.",
            "--counterfactual-instruction",
            "Prefer narrow shell probes before patching.",
            "--analysis-question",
            "Would the next action remain an exec command?",
            "--expected-good",
            "shell_command",
            "--auth-json",
            str(tmp_path / "auth.json"),
            "--out-json",
            str(tmp_path / "prediction.json"),
            "--out-prompt",
            str(tmp_path / "prompt.txt"),
        ]
    )

    assert args.decision_sequence == 11
    assert args.context_items == 4
    assert args.counterfactual_instruction == [
        "Inspect linker flags first.",
        "Prefer narrow shell probes before patching.",
    ]
    assert args.analysis_question == "Would the next action remain an exec command?"
    assert args.expected_good == ["shell_command"]
    assert args.model == "gpt-5.5"


def _write_artifact(
    tmp_path: Path,
    *,
    items: list[dict[str, object]],
    instructions: str = "system prompt",
    input_text: str = "raw task",
) -> Path:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "native-provider-requests.json").write_text(
        json.dumps(
            {
                "requests": [
                    {
                        "request_body": {
                            "instructions": instructions,
                            "input": [
                                {
                                    "role": "user",
                                    "content": [{"type": "input_text", "text": input_text}],
                                }
                            ],
                            "tools": [{"name": "exec_command"}, {"type": "custom", "name": "apply_patch"}],
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (artifact / "response_transcript.json").write_text(
        json.dumps({"items": items}),
        encoding="utf-8",
    )
    return artifact


def _load_counterfactual_cli_module():
    path = ROOT / "scripts" / "run_counterfactual_next_action.py"
    spec = importlib.util.spec_from_file_location("run_counterfactual_next_action", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
