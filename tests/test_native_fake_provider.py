import json

from mew.implement_lane.native_fake_provider import (
    FAKE_NATIVE_MODEL_NAME,
    FAKE_NATIVE_PROVIDER_NAME,
    PHASE3_TRANSPORT_CHANGE,
    NativeFakeProvider,
    fake_call,
    fake_finish,
    model_json_text_non_control_item,
)


def test_fake_provider_marks_phase3_transport_change_and_native_capability() -> None:
    provider = NativeFakeProvider.from_item_batches([[fake_call("read-1", "read_file", {"path": "a.txt"})]])

    assert PHASE3_TRANSPORT_CHANGE == "yes"
    assert provider.provider == FAKE_NATIVE_PROVIDER_NAME
    assert provider.model == FAKE_NATIVE_MODEL_NAME
    assert provider.supports_native_tool_calls is True


def test_fake_provider_emits_provider_native_items_not_legacy_model_json_envelope() -> None:
    provider = NativeFakeProvider.from_item_batches(
        [[fake_call("finish-1", "finish", {"outcome": "completed"})]]
    )

    response = provider.next_response({"transport_kind": "provider_native"})

    assert response is not None
    assert response.items[0]["type"] == "function_call"
    assert response.items[0]["name"] == "finish"
    assert "tool_calls" not in response.items[0]
    assert "finish" not in response.items[0]


def test_model_json_text_fixture_is_assistant_text_only() -> None:
    item = model_json_text_non_control_item()

    assert item["type"] == "message"
    decoded = json.loads(str(item["content"]))
    assert decoded["tool_calls"][0]["id"] == "not-a-native-call"
    assert fake_finish("finish-ok")["name"] == "finish"
