import copy

from mew.implement_lane.native_tool_schema import (
    NativeToolSchemaCapabilities,
    lower_implement_lane_tool_spec,
    lower_implement_lane_tool_specs,
    provider_tool_spec_hash,
    strict_false_reasons,
    structured_tool_json_schema,
    validate_strict_json_schema,
)
from mew.implement_lane.tool_policy import (
    ImplementLaneToolSpec,
    list_v2_base_tool_specs,
)


def test_base_tool_specs_lower_to_responses_tools_with_strict_read_file_schema() -> (
    None
):
    lowered = lower_implement_lane_tool_specs(list_v2_base_tool_specs())
    by_name = {tool.name: tool for tool in lowered}

    read_file = by_name["read_file"].provider_tool
    assert read_file == {
        "type": "function",
        "name": "read_file",
        "description": "Read only the bounded workspace excerpt needed to choose or validate a patch; returns line anchors.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative path to read.",
                },
                "offset": {
                    "type": ["integer", "null"],
                    "description": "Character offset to start reading from.",
                },
                "max_chars": {
                    "type": ["integer", "null"],
                    "description": "Maximum characters to return.",
                },
            },
            "required": ["path", "offset", "max_chars"],
            "additionalProperties": False,
        },
        "strict": True,
    }
    assert by_name["read_file"].validation.valid is True
    assert strict_false_reasons(lowered) == {}


def test_base_tool_specs_order_prefers_mutation_then_execution_then_context() -> None:
    names = [spec.name for spec in list_v2_base_tool_specs()]

    assert names == [
        "apply_patch",
        "edit_file",
        "write_file",
        "run_command",
        "run_tests",
        "poll_command",
        "cancel_command",
        "read_command_output",
        "read_file",
        "search_text",
        "glob",
        "inspect_dir",
        "git_status",
        "git_diff",
        "finish",
    ]


def test_base_tool_specs_descriptions_remove_probe_frontier_salience() -> None:
    descriptions = "\n".join(spec.description for spec in list_v2_base_tool_specs())

    assert "cheap probe" not in descriptions
    assert "fallback-probe" not in descriptions
    assert "fallback probe" not in descriptions
    assert "frontier" not in descriptions
    assert "broad recursive source exploration" not in descriptions
    assert "apply_patch" in descriptions
    assert "bounded path:line matches" in descriptions


def test_lowered_provider_tool_descriptions_remove_probe_frontier_salience() -> None:
    lowered = lower_implement_lane_tool_specs(list_v2_base_tool_specs())
    descriptions = "\n".join(str(tool.provider_tool.get("description") or "") for tool in lowered)

    assert "cheap probe" not in descriptions
    assert "fallback-probe" not in descriptions
    assert "fallback probe" not in descriptions
    assert "frontier" not in descriptions
    assert "broad recursive source exploration" not in descriptions
    assert "Primary source mutation tool" in descriptions
    assert "custom/freeform patch input" in descriptions


def test_execute_tool_schemas_do_not_expose_command_self_labeling() -> None:
    lowered = lower_implement_lane_tool_specs(list_v2_base_tool_specs())
    by_name = {tool.name: tool for tool in lowered}

    for tool_name in ("run_command", "run_tests"):
        provider_tool = by_name[tool_name].provider_tool
        serialized = str(provider_tool)
        properties = provider_tool["parameters"]["properties"]  # type: ignore[index]

        assert "max_output_chars" in properties
        assert "max_output_tokens" in properties
        assert "command_intent" not in properties
        assert "justification" not in properties
        assert "command_intent" not in serialized
        assert "justification" not in serialized
        assert "probe" not in serialized
        assert "diagnostic" not in serialized


def test_write_file_tool_contract_discourages_large_source_payloads() -> None:
    lowered = lower_implement_lane_tool_specs(list_v2_base_tool_specs())
    write_file = {tool.name: tool for tool in lowered}["write_file"].provider_tool

    description = str(write_file["description"])
    content_lines_description = str(
        write_file["parameters"]["properties"]["content_lines"]["description"]  # type: ignore[index]
    )

    assert "small complete file" in description
    assert "Prefer apply_patch or edit_file" in description
    assert "avoid large generated source payloads in one provider-native call" in content_lines_description


def test_apply_patch_lowers_to_custom_grammar_tool_when_supported() -> None:
    lowered = lower_implement_lane_tool_specs(list_v2_base_tool_specs())
    apply_patch = {tool.name: tool for tool in lowered}["apply_patch"]

    assert apply_patch.strict is None
    assert apply_patch.provider_tool["type"] == "custom"
    assert apply_patch.provider_tool["name"] == "apply_patch"
    assert "Primary source mutation tool" in apply_patch.provider_tool["description"]
    assert "smallest runnable candidate" in apply_patch.provider_tool["description"]
    assert "custom/freeform patch input" in apply_patch.provider_tool["description"]
    assert apply_patch.provider_tool["format"]["type"] == "grammar"  # type: ignore[index]
    assert apply_patch.provider_tool["format"]["syntax"] == "lark"  # type: ignore[index]
    assert (
        "start: begin_patch hunk+ end_patch"
        in apply_patch.provider_tool["format"]["definition"]
    )  # type: ignore[index]


def test_strict_schema_validation_requires_every_property_and_rejects_extra_properties() -> (
    None
):
    schema = copy.deepcopy(structured_tool_json_schema("read_file"))
    assert schema is not None
    schema["required"] = ["path"]
    schema["additionalProperties"] = True

    validation = validate_strict_json_schema(schema)

    assert validation.valid is False
    assert "$:required_missing_properties:max_chars,offset" in validation.errors
    assert "$:additionalProperties_not_false" in validation.errors


def test_non_strict_fallback_records_reason_when_custom_apply_patch_is_unsupported() -> (
    None
):
    spec = next(
        tool for tool in list_v2_base_tool_specs() if tool.name == "apply_patch"
    )
    lowered = lower_implement_lane_tool_spec(
        spec,
        capabilities=NativeToolSchemaCapabilities(supports_custom_freeform_tools=False),
    )

    assert lowered.provider_tool["type"] == "function"
    assert lowered.provider_tool["strict"] is False
    assert lowered.strict_false_reason == "custom_freeform_apply_patch_not_supported"
    assert "patch" in lowered.validation.errors[0]


def test_unknown_structured_tool_lowers_non_strict_with_reason() -> None:
    lowered = lower_implement_lane_tool_spec(
        ImplementLaneToolSpec(
            name="legacy_probe",
            access="read",
            description="Legacy probe without a strict schema.",
        )
    )

    assert lowered.provider_tool["type"] == "function"
    assert lowered.provider_tool["strict"] is False
    assert lowered.strict_false_reason == "no_strict_schema_for_tool:legacy_probe"


def test_tool_spec_hash_is_stable_for_same_lowering() -> None:
    first = lower_implement_lane_tool_specs(list_v2_base_tool_specs())
    second = lower_implement_lane_tool_specs(list_v2_base_tool_specs())

    assert provider_tool_spec_hash(first) == provider_tool_spec_hash(second)
