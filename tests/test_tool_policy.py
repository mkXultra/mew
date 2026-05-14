from mew.implement_lane.tool_policy import (
    is_hard_runtime_artifact_task,
    list_v2_base_tool_specs,
    list_v2_tool_specs_for_task,
)


def _names(specs):
    return [spec.name for spec in specs]


def test_mutation_tools_prefer_patch_and_edit_before_write_file() -> None:
    names = _names(list_v2_base_tool_specs())

    assert names.index("apply_patch") < names.index("edit_file") < names.index("write_file")


def test_hard_runtime_artifact_task_keeps_complete_file_creation_surface() -> None:
    task_contract = {
        "goal": (
            "Build a MIPS ELF interpreter runtime from provided source and write "
            "a /tmp/frame.bmp artifact."
        )
    }

    names = set(_names(list_v2_tool_specs_for_task("full", task_contract=task_contract)))

    assert is_hard_runtime_artifact_task(task_contract) is True
    assert {"write_file", "apply_patch", "edit_file", "run_command", "run_tests"}.issubset(names)


def test_non_hard_runtime_write_mode_keeps_small_file_creation_surface() -> None:
    task_contract = {"goal": "Create a short README note in the workspace."}

    names = set(_names(list_v2_tool_specs_for_task("write", task_contract=task_contract)))

    assert "write_file" in names
    assert {"apply_patch", "edit_file"}.issubset(names)
