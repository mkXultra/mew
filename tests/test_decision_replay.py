import json
from pathlib import Path

from mew.implement_lane.decision_replay import (
    DEFAULT_ANALYSIS_QUESTIONS,
    ask_decision_replay_model,
    build_decision_replay_packet,
    decision_replay_prompt,
    write_decision_replay_artifacts,
)


def test_decision_replay_packet_selects_first_mutation(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "native-provider-requests.json").write_text(
        json.dumps(
            {
                "requests": [
                    {
                        "request_body": {
                            "instructions": "system prompt",
                            "input": [{"role": "user", "content": [{"type": "input_text", "text": "raw task"}]}],
                            "tools": [{"name": "exec_command"}, {"type": "custom", "name": "apply_patch"}],
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (artifact / "response_transcript.json").write_text(
        json.dumps(
            {
                "items": [
                    {"sequence": 1, "kind": "function_call", "tool_name": "exec_command", "arguments_json_text": "{}"},
                    {"sequence": 2, "kind": "function_call_output", "tool_name": "exec_command", "output_text_or_ref": "no compiler"},
                    {
                        "sequence": 3,
                        "kind": "custom_tool_call",
                        "tool_name": "apply_patch",
                        "custom_input_text": "*** Begin Patch\n*** Add File: synthetic.py\n",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    packet = build_decision_replay_packet(
        artifact,
        analysis_questions=("Should this be fixed with prompt or tools?",),
    )

    assert packet["provider_visible"]["instructions"] == "system prompt"
    assert packet["decision"]["sequence"] == 3
    assert packet["decision"]["tool_name"] == "apply_patch"
    assert packet["context_before_decision"][-1]["text"] == "no compiler"
    assert packet["analysis_questions"][: len(DEFAULT_ANALYSIS_QUESTIONS)] == list(DEFAULT_ANALYSIS_QUESTIONS)
    assert packet["analysis_questions"][-1] == "Should this be fixed with prompt or tools?"
    prompt = decision_replay_prompt(packet)
    assert "synthetic.py" in prompt
    assert "answers object" in prompt


def test_write_decision_replay_artifacts(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "native-provider-requests.json").write_text(
        json.dumps({"requests": [{"request_body": {"instructions": "", "input": [], "tools": []}}]}),
        encoding="utf-8",
    )
    (artifact / "response_transcript.json").write_text(
        json.dumps({"items": [{"sequence": 9, "kind": "custom_tool_call", "tool_name": "apply_patch"}]}),
        encoding="utf-8",
    )
    out_json = tmp_path / "packet.json"
    out_prompt = tmp_path / "prompt.txt"

    packet = write_decision_replay_artifacts(
        artifact,
        out_json=out_json,
        out_prompt=out_prompt,
        analysis_questions=("What was expected?",),
    )

    assert packet["decision"]["sequence"] == 9
    assert json.loads(out_json.read_text(encoding="utf-8"))["decision"]["sequence"] == 9
    assert json.loads(out_json.read_text(encoding="utf-8"))["analysis_questions"][-1] == "What was expected?"
    prompt = out_prompt.read_text(encoding="utf-8")
    assert "PACKET:" in prompt
    assert "What was expected?" in prompt


def test_ask_decision_replay_model_requires_explicit_auth_and_delegates(monkeypatch, tmp_path: Path) -> None:
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
        return {"decision_summary": "ok"}

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
    packet = {"decision": {"sequence": 1, "tool_name": "apply_patch"}}
    result = ask_decision_replay_model(packet, auth_json=auth_json)

    assert result == {"decision_summary": "ok"}
    assert calls["auth"] == ("codex", str(auth_json))
    assert calls["default_base_url"] == "codex"
    assert calls["call"]["model"] == "gpt-5.5"
    assert calls["call"]["base_url"] == "https://example.invalid/codex"
    assert calls["call"]["timeout"] == 180.0
    assert "PACKET:" in calls["call"]["prompt"]
