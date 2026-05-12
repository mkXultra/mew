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
        "description": "Read a workspace file through the existing read substrate.",
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


def test_write_file_tool_contract_discourages_huge_native_payloads() -> None:
    lowered = lower_implement_lane_tool_specs(list_v2_base_tool_specs())
    write_file = {tool.name: tool for tool in lowered}["write_file"].provider_tool

    description = str(write_file["description"])
    content_lines_description = str(
        write_file["parameters"]["properties"]["content_lines"]["description"]  # type: ignore[index]
    )

    assert "Do not emit a single huge provider-native write_file JSON payload" in description
    assert "small and medium writes" in description
    assert "avoid large generated source payloads in one provider-native call" in content_lines_description


def test_apply_patch_lowers_to_custom_grammar_tool_when_supported() -> None:
    lowered = lower_implement_lane_tool_specs(list_v2_base_tool_specs())
    apply_patch = {tool.name: tool for tool in lowered}["apply_patch"]

    assert apply_patch.strict is None
    assert apply_patch.provider_tool["type"] == "custom"
    assert apply_patch.provider_tool["name"] == "apply_patch"
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
