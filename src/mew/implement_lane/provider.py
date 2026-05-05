"""Provider adapter primitives for the explicit implement_v2 lane."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .transcript import build_transcript_event
from .types import ImplementLaneTranscriptEvent, ToolCallEnvelope, ToolResultEnvelope


@dataclass(frozen=True)
class FakeProviderToolCall:
    """A deterministic provider-native tool call fixture."""

    provider_call_id: str
    tool_name: str
    arguments: dict[str, object] = field(default_factory=dict)
    provider_message_id: str = "fake-message"


class FakeProviderAdapter:
    """Small provider adapter used by Phase 2 tests.

    It does not call a model. It only normalizes provider-like tool-call shapes
    and serializes tool results so replay invariants can be tested without
    filesystem or command side effects.
    """

    provider = "fake"

    def normalize_tool_calls(
        self,
        *,
        lane_attempt_id: str,
        turn_index: int,
        calls: Iterable[FakeProviderToolCall | Mapping[str, object]],
    ) -> tuple[ToolCallEnvelope, ...]:
        normalized = []
        for sequence_index, raw_call in enumerate(calls, start=1):
            call = _coerce_fake_tool_call(raw_call)
            normalized.append(
                ToolCallEnvelope(
                    lane_attempt_id=lane_attempt_id,
                    provider=self.provider,
                    provider_message_id=call.provider_message_id,
                    provider_call_id=call.provider_call_id,
                    mew_tool_call_id=f"{lane_attempt_id}:tool:{turn_index}:{sequence_index}",
                    turn_index=turn_index,
                    sequence_index=sequence_index,
                    tool_name=call.tool_name,
                    arguments=call.arguments,
                )
            )
        return tuple(normalized)

    def transcript_events_for_turn(
        self,
        *,
        lane: str,
        lane_attempt_id: str,
        turn_id: str,
        text: str = "",
        tool_calls: Iterable[ToolCallEnvelope] = (),
    ) -> tuple[ImplementLaneTranscriptEvent, ...]:
        events = []
        index = 0
        if text:
            events.append(
                build_transcript_event(
                    kind="model_message",
                    lane=lane,
                    turn_id=turn_id,
                    index=index,
                    lane_attempt_id=lane_attempt_id,
                    payload={"provider": self.provider, "lane_attempt_id": lane_attempt_id, "text": text},
                )
            )
            index += 1
        for call in tool_calls:
            events.append(
                build_transcript_event(
                    kind="tool_call",
                    lane=lane,
                    turn_id=turn_id,
                    index=index,
                    lane_attempt_id=lane_attempt_id,
                    payload=call.as_dict(),
                )
            )
            index += 1
        if not events:
            events.append(
                build_transcript_event(
                    kind="model_message",
                    lane=lane,
                    turn_id=turn_id,
                    index=0,
                    lane_attempt_id=lane_attempt_id,
                    payload={"provider": self.provider, "lane_attempt_id": lane_attempt_id, "text": ""},
                )
            )
        return tuple(events)

    def finish_event_for_turn(
        self,
        *,
        lane: str,
        lane_attempt_id: str,
        turn_id: str,
        finish_arguments: dict[str, object],
    ) -> ImplementLaneTranscriptEvent:
        """Build a fake provider finish event for Phase 2 replay tests."""

        return build_transcript_event(
            kind="finish",
            lane=lane,
            turn_id=turn_id,
            index=0,
            lane_attempt_id=lane_attempt_id,
            payload={
                "provider": self.provider,
                "lane_attempt_id": lane_attempt_id,
                "finish_arguments": dict(finish_arguments),
            },
        )

    def provider_tool_result_payload(self, result: ToolResultEnvelope) -> dict[str, object]:
        """Serialize a result as a provider-visible tool_result payload."""

        return {
            "tool_result": {
                "tool_use_id": result.provider_call_id,
                "is_error": result.is_error,
                "content": result.provider_visible_content(),
            }
        }


class JsonModelProviderAdapter(FakeProviderAdapter):
    """Provider adapter for the live v2 JSON transport.

    This is not provider-specific function calling yet. It gives the v2 lane a
    real model-driven tool loop with provider-shaped call/result envelopes while
    keeping the provider transport explicit in replay artifacts.
    """

    provider = "model_json"


def _coerce_fake_tool_call(raw_call: FakeProviderToolCall | Mapping[str, object]) -> FakeProviderToolCall:
    if isinstance(raw_call, FakeProviderToolCall):
        return raw_call
    arguments = raw_call.get("arguments") if isinstance(raw_call.get("arguments"), dict) else {}
    return FakeProviderToolCall(
        provider_call_id=str(raw_call.get("provider_call_id") or raw_call.get("id") or ""),
        provider_message_id=str(raw_call.get("provider_message_id") or "fake-message"),
        tool_name=str(raw_call.get("tool_name") or raw_call.get("name") or ""),
        arguments=dict(arguments),
    )


__all__ = ["FakeProviderAdapter", "FakeProviderToolCall", "JsonModelProviderAdapter"]
