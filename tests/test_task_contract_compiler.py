import json

from mew.task_contract_compiler import (
    apply_compiled_task_contract,
    build_task_contract_compiler_prompt,
    compile_task_contract_with_model,
    normalize_compiled_task_contract,
    task_contract_compiler_failure_contract,
    task_contract_compiler_is_compiled,
)
from mew.implement_lane.execution_evidence import build_oracle_bundle
from mew.commands import (
    _work_guidance_task_contract_compiler_enabled,
    _work_guidance_task_contract_guidance,
)


def test_normalize_compiled_task_contract_keeps_structured_artifacts():
    compiled = normalize_compiled_task_contract(
        {
            "goal": "Render a frame",
            "completion_criteria": ["frame is written"],
            "expected_artifacts": [
                {
                    "id": "artifact:frame",
                    "kind": "image",
                    "path": "/tmp/frame.bmp",
                    "freshness": "created_after_run_start",
                    "checks": [{"type": "exists"}, {"type": "non_empty"}],
                }
            ],
            "verifier": {"command": "node vm.js && test -s /tmp/frame.bmp", "must_pass": True},
        }
    )

    assert compiled["schema_version"] == 1
    assert compiled["expected_artifacts"] == [
        {
            "id": "artifact:frame",
            "kind": "image",
            "required": True,
            "source": "model_declared",
            "confidence": "high",
            "freshness": "created_after_run_start",
            "checks": [{"type": "exists"}, {"type": "non_empty"}, {"type": "mtime_after"}],
            "path": "/tmp/frame.bmp",
        }
    ]
    assert compiled["verifier"]["command"].startswith("node vm.js")


def test_apply_compiled_task_contract_disables_legacy_acceptance_constraints():
    base = {
        "description": "Render a frame. The output must be /tmp/frame.bmp.",
        "verify_command": "node vm.js",
        "acceptance_constraints": ["The output must be /tmp/frame.bmp."],
    }
    updated = apply_compiled_task_contract(
        base,
        {
            "completion_criteria": ["final verifier creates the frame"],
            "expected_artifacts": [{"id": "frame", "path": "/tmp/frame.bmp", "kind": "image"}],
            "verifier": {"command": "ignored because explicit verify_command wins", "must_pass": True},
        },
    )

    assert updated["verify_command"] == "node vm.js"
    assert updated["acceptance_constraints"] == []
    assert updated["legacy_acceptance_constraints"] == ["The output must be /tmp/frame.bmp."]
    assert updated["legacy_string_gate_mode"] == "disabled_by_task_contract_compiler"
    assert updated["task_contract_compiler"]["status"] == "compiled"
    assert updated["expected_artifacts"][0]["path"] == "/tmp/frame.bmp"
    assert updated["compiled_task_contract"]["verifier"]["command"] == "node vm.js"
    assert updated["compiled_task_contract"]["verifier"]["must_pass"] is True


def test_normalize_compiled_task_contract_preserves_unsupported_glob_artifacts_as_blockers():
    compiled = normalize_compiled_task_contract(
        {
            "expected_artifacts": [
                {"id": "frames", "kind": "glob", "path": "/tmp/frame*.bmp"},
                {"id": "frame", "kind": "image", "path": "/tmp/frame.bmp"},
            ],
        }
    )

    assert [artifact["id"] for artifact in compiled["expected_artifacts"]] == ["frames", "frame"]
    unsupported = compiled["expected_artifacts"][0]
    assert unsupported["checks"][0]["type"] == "unsupported_artifact_contract"
    assert unsupported["checks"][0]["severity"] == "blocking"


def test_compiled_task_contract_adds_oracle_obligations():
    task_contract = apply_compiled_task_contract(
        {"verify_command": "node vm.js"},
        {
            "expected_artifacts": [{"id": "frame", "path": "/tmp/frame.bmp", "kind": "image"}],
            "verifier": {"command": "pytest -q", "must_pass": False},
        },
    )

    bundle = build_oracle_bundle(task_contract=task_contract)

    assert bundle is not None
    kinds = {obligation.kind for obligation in bundle.obligations}
    assert "artifact_exists" in kinds
    assert "verifier_pass" in kinds
    verifier_obligations = [obligation for obligation in bundle.obligations if obligation.kind == "verifier_pass"]
    assert any(obligation.subject.get("any_verifier") for obligation in verifier_obligations)
    assert any(obligation.subject.get("verify_command") == "node vm.js" for obligation in verifier_obligations)


def test_task_contract_compiler_prompt_requests_json_only():
    prompt = build_task_contract_compiler_prompt({"description": "Fix app.py and run pytest."})

    assert "Return JSON only" in prompt
    assert "expected_artifacts" in prompt
    assert "Raw task contract" in prompt


def test_task_contract_compiler_is_default_enabled_with_legacy_opt_in():
    assert _work_guidance_task_contract_compiler_enabled("selected_lane=implement_v2") is True
    assert _work_guidance_task_contract_compiler_enabled("task_contract_compiler=legacy") is False
    assert _work_guidance_task_contract_compiler_enabled('{"task_contract_compiler":false}') is False

    sanitized = _work_guidance_task_contract_guidance(
        "selected_lane=implement_v2 task_contract_compiler=legacy task_contract_compiler_model=gpt-test"
    )
    assert "task_contract_compiler" not in sanitized
    assert "selected_lane" in sanitized


def test_task_contract_guidance_strips_finish_verifier_external_failure_json():
    sanitized = _work_guidance_task_contract_guidance(
        json.dumps(
            {
                "selected_lane": "implement_v2",
                "finish_verifier_external_failure": {"test_stdout_tail": "hidden oracle output"},
                "lane_config": {
                    "external_verifier_failure": {"test_stdout_tail": "nested hidden oracle output"},
                    "finish_verifier_planner": True,
                },
            }
        )
    )

    assert "hidden oracle output" not in sanitized
    assert "finish_verifier_external_failure" not in sanitized
    assert "external_verifier_failure" not in sanitized
    assert json.loads(sanitized) == {"selected_lane": "implement_v2"}


def test_task_contract_guidance_strips_finish_verifier_external_failure_string_options():
    sanitized = _work_guidance_task_contract_guidance(
        "selected_lane=implement_v2 "
        "finish_verifier_external_failure=hidden-oracle-output "
        "external_verifier_failure='nested hidden oracle output' "
        "finish_verifier_planner=true"
    )

    assert sanitized == "selected_lane=implement_v2"


def test_task_contract_guidance_strips_finish_verifier_external_failure_brace_options():
    sanitized = _work_guidance_task_contract_guidance(
        'selected_lane=implement_v2 '
        'external_verifier_failure={"test_stdout_tail":"nested hidden oracle output"} '
        'finish_verifier_external_failure={"test_stdout_tail":"more hidden oracle output"} '
        'finish_verifier_planner=true'
    )

    assert sanitized == "selected_lane=implement_v2"


def test_task_contract_compiler_failure_uses_typed_fallback_not_legacy_gate():
    updated, report = task_contract_compiler_failure_contract(
        {
            "title": "Render frame",
            "description": "Render /tmp/frame.bmp.",
            "verify_command": "node vm.js",
            "acceptance_constraints": ["Render /tmp/frame.bmp."],
        },
        error=RuntimeError("model unavailable"),
    )

    assert report["status"] == "typed_fallback"
    assert updated["task_contract_compiler"]["status"] == "typed_fallback"
    assert task_contract_compiler_is_compiled(updated) is True
    assert updated["acceptance_constraints"] == []
    assert updated["legacy_acceptance_constraints"] == ["Render /tmp/frame.bmp."]
    assert updated["legacy_string_gate_mode"] == "disabled_by_task_contract_compiler"
    assert updated["compiled_task_contract"]["fallback_reason"] == "compiler_failed"
    assert updated["verify_command"] == "node vm.js"


def test_compile_task_contract_with_model_calls_json_backend():
    calls = []

    def fake_call_json(model_backend, model_auth, prompt, model, base_url, timeout):
        calls.append((model_backend, model_auth, prompt, model, base_url, timeout))
        return {
            "goal": "Fix app.py",
            "completion_criteria": ["pytest passes"],
            "verifier": {"command": "pytest", "must_pass": True},
        }

    updated, report = compile_task_contract_with_model(
        {"description": "Fix app.py", "verify_command": "pytest"},
        model_backend="codex",
        model_auth={"token": "x"},
        model="gpt-test",
        base_url="https://example.invalid",
        timeout=12,
        call_json=fake_call_json,
    )

    assert len(calls) == 1
    assert "Raw task contract" in calls[0][2]
    assert updated["task_contract_compiler"]["status"] == "compiled"
    assert updated["completion_criteria"] == ["pytest passes"]
    assert report["status"] == "compiled"
