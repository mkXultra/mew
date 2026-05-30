"""Fake provider-native item source for Phase 3 native harness tests.

The fake provider deliberately emits provider-shaped response items, not the
legacy model-JSON response contract.  It is not wired into the production lane;
the Phase 3 harness consumes it through the same NativeTranscriptItem
normalization path expected for live native adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Iterable, Mapping


FAKE_NATIVE_PROVIDER_NAME = "fake-native"
FAKE_NATIVE_MODEL_NAME = "fake-native-model"
PHASE3_TRANSPORT_CHANGE = "yes"


@dataclass(frozen=True)
class FakeNativeResponse:
    """One fake provider response made of provider-native output items."""

    response_id: str
    items: tuple[dict[str, object], ...]
    latency_ms: int = 0


@dataclass
class NativeFakeProvider:
    """Deterministic fake provider for native tool-loop fixtures."""

    responses: tuple[FakeNativeResponse, ...]
    provider: str = FAKE_NATIVE_PROVIDER_NAME
    model: str = FAKE_NATIVE_MODEL_NAME
    supports_native_tool_calls: bool = True
    requests: list[dict[str, object]] = field(default_factory=list)
    _index: int = 0

    @classmethod
    def from_item_batches(
        cls,
        batches: Iterable[Iterable[Mapping[str, object]]],
        *,
        provider: str = FAKE_NATIVE_PROVIDER_NAME,
        model: str = FAKE_NATIVE_MODEL_NAME,
    ) -> "NativeFakeProvider":
        responses = []
        for index, batch in enumerate(batches, 1):
            response_id = f"fake-response-{index}"
            responses.append(
                FakeNativeResponse(
                    response_id=response_id,
                    items=tuple(_provider_item(dict(item), response_id=response_id) for item in batch),
                )
            )
        return cls(tuple(responses), provider=provider, model=model)

    def next_response(self, request_descriptor: Mapping[str, object]) -> FakeNativeResponse | None:
        self.requests.append(dict(request_descriptor))
        if self._index >= len(self.responses):
            return None
        response = self.responses[self._index]
        self._index += 1
        return response


def fake_message(text: str, *, item_id: str = "msg-1") -> dict[str, object]:
    return {"type": "message", "id": item_id, "role": "assistant", "content": text}


def fake_reasoning(summary: str, *, item_id: str = "reasoning-1") -> dict[str, object]:
    return {"type": "reasoning", "id": item_id, "summary": summary}


def fake_call(
    call_id: str,
    name: str,
    arguments: Mapping[str, object] | str | None = None,
    *,
    item_id: str | None = None,
    output_index: int = 0,
) -> dict[str, object]:
    payload: object
    if isinstance(arguments, str):
        payload = arguments
    else:
        payload = dict(arguments or {})
    return {
        "type": "function_call",
        "id": item_id or f"item-{call_id}",
        "call_id": call_id,
        "name": name,
        "arguments": payload,
        "output_index": output_index,
    }


def fake_finish(
    call_id: str = "finish-1",
    arguments: Mapping[str, object] | None = None,
    *,
    output_index: int = 0,
) -> dict[str, object]:
    return fake_call(
        call_id,
        "finish",
        dict(arguments or {"outcome": "completed", "summary": "done"}),
        item_id=f"item-{call_id}",
        output_index=output_index,
    )


def model_json_text_non_control_item(*, item_id: str = "json-text") -> dict[str, object]:
    return fake_message(
        json.dumps(
            {
                "summary": "legacy shape as plain text",
                "tool_calls": [{"id": "not-a-native-call", "name": "read_file", "arguments": {"path": "x"}}],
                "finish": {"outcome": "completed"},
            },
            sort_keys=True,
        ),
        item_id=item_id,
    )


def _provider_item(item: dict[str, object], *, response_id: str) -> dict[str, object]:
    item.setdefault("response_id", response_id)
    return item
