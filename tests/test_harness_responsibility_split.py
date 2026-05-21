import ast
from pathlib import Path


HARNESS = Path("src/mew/implement_lane/native_tool_harness.py")
REQUEST_BUILDER = Path("src/mew/implement_lane/native_request_builder.py")
ARTIFACT_WRITER = Path("src/mew/implement_lane/native_artifact_writer.py")
CLOSEOUT_POLICY = Path("src/mew/implement_lane/native_finish_closeout_policy.py")


def _harness_tree() -> ast.Module:
    return ast.parse(HARNESS.read_text(encoding="utf-8"))


def test_native_harness_does_not_define_finish_verifier_planner_component() -> None:
    tree = _harness_tree()
    class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    function_names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

    assert not {name for name in class_names if name.startswith("FinishVerifierPlanner")}
    assert not {name for name in function_names if name.startswith("_finish_verifier_planner_")}
    assert not {name for name in function_names if name.startswith("_coerce_native_finish_verifier_plan")}
    assert "run_finish_verifier_planner_loop" not in function_names


def test_native_harness_delegates_completion_resolver_input_construction() -> None:
    tree = _harness_tree()
    imported_names: set[str] = set()
    called_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)

    assert "CompletionResolverInput" not in imported_names
    assert "FinishClaim" not in imported_names
    assert "CompletionResolverInput" not in called_names
    assert "build_completion_resolver_input_from_finish" in called_names


def _function_defs(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def _is_single_return_component_call(node: ast.FunctionDef, *, component_names: set[str]) -> bool:
    body = [item for item in node.body if not isinstance(item, ast.Expr) or not isinstance(item.value, ast.Constant)]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    call = body[0].value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return False
    owner = call.func.value
    return isinstance(owner, ast.Name) and owner.id in component_names


def _returns_component_call(node: ast.FunctionDef, *, component_names: set[str]) -> bool:
    for item in ast.walk(node):
        if not isinstance(item, ast.Return):
            continue
        call = item.value
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            continue
        owner = call.func.value
        if isinstance(owner, ast.Name) and owner.id in component_names:
            return True
    return False


def test_native_harness_delegates_finish_closeout_policy_entrypoints() -> None:
    tree = _harness_tree()
    classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    functions = _function_defs(tree)
    source = HARNESS.read_text(encoding="utf-8")

    assert "_NativeCloseoutEvent" not in classes
    assert "_NativeCloseoutContext" not in classes
    assert "_native_finish_gate_decision" not in functions
    assert "_native_finish_gate_decision_from_closeout_events" not in functions
    assert "_native_finish_gate_decision_from_done_candidate" not in functions
    assert "_native_finish_gate_decision_from_controller_closeout_event" not in functions
    assert "_native_finish_closeout_result_from_event" not in functions
    assert "_native_finish_closeout_result_from_context" not in functions
    assert _is_single_return_component_call(
        functions["_run_native_finish_time_closeouts"],
        component_names={"_closeout_policy"},
    )
    assert _is_single_return_component_call(
        functions["_native_apply_ng_resume_policy"],
        component_names={"_closeout_policy"},
    )
    assert "_harness_ops" not in source


def test_native_harness_delegates_request_and_artifact_writer_entrypoints() -> None:
    tree = _harness_tree()
    functions = _function_defs(tree)
    source = HARNESS.read_text(encoding="utf-8")

    for name, component in (
        ("_request_descriptor", "_request_builder"),
        ("_live_responses_request_descriptor", "_request_builder"),
        ("_native_instructions", "_request_builder"),
        ("_tool_specs_from_request_descriptor", "_request_builder"),
        ("_native_tool_specs_for_request", "_request_builder"),
        ("_tool_surface_snapshot_for_request", "_request_builder"),
        ("_responses_input_items", "_request_builder"),
        ("_compact_sidecar_digest_for_request", "_request_builder"),
        ("_profile_developer_transport", "_request_builder"),
        ("_provider_visible_native_item", "_request_builder"),
        ("_write_native_artifacts", "_artifact_writer"),
        ("_route_records_with_tool_surface", "_artifact_writer"),
        ("_write_native_tool_result_sidecars", "_artifact_writer"),
        ("_write_native_render_output_sidecar", "_artifact_writer"),
        ("_provider_request_records", "_artifact_writer"),
        ("_write_provider_request_artifacts", "_artifact_writer"),
    ):
        assert _is_single_return_component_call(functions[name], component_names={component}), name
    assert _returns_component_call(functions["_write_live_failure_artifacts"], component_names={"_artifact_writer"})
    assert "NativeRequestBuilderDeps(" not in source
    assert "NativeArtifactWriterDeps(" not in source
    assert "NativeFinishCloseoutDeps(" not in source
    assert "_request_builder_deps" not in functions


def test_native_responsibility_components_do_not_use_harness_callback_deps() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REQUEST_BUILDER, ARTIFACT_WRITER, CLOSEOUT_POLICY)
    )
    for forbidden in (
        "NativeRequestBuilderDeps",
        "NativeArtifactWriterDeps",
        "NativeFinishCloseoutDeps",
        "default_request_builder_deps",
        "default_finish_closeout_deps",
        "_harness_ops",
        "native_tool_harness as harness",
    ):
        assert forbidden not in combined
