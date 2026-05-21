from __future__ import annotations

import json

from mew.short_term_memory import (
    ShortTermMemoryBuffer,
    ShortTermMemoryCard,
    ShortTermMemoryCompressionRequest,
    compress_short_term_memory_with_model,
    normalize_short_term_memory_payload,
    short_term_memory_compression_prompt,
)


def test_short_term_memory_prompt_requests_schema_without_raw_storage():
    request = ShortTermMemoryCompressionRequest(
        raw_text="Turn 1 inspected a failing verifier. Reviewer decided to fix the source file first.",
        source_refs=("turn:1", "tool:verifier"),
        current_turn=3,
        max_cards=3,
    )

    prompt = short_term_memory_compression_prompt(request)
    payload = json.loads(prompt)

    assert payload["task"].startswith("Compress recent")
    assert "Do not copy raw transcript; compress it." in payload["rules"]
    assert payload["limits"]["max_cards"] == 3
    assert payload["source_refs"] == ["turn:1", "tool:verifier"]


def test_normalize_short_term_memory_payload_bounds_cards_and_refs():
    request = ShortTermMemoryCompressionRequest(
        raw_text="raw text",
        source_refs=("turn:1", "tool:abc"),
        current_turn=4,
        max_cards=1,
        max_summary_chars=40,
    )

    result = normalize_short_term_memory_payload(
        {
            "cards": [
                {
                    "kind": "decision",
                    "summary": "Use apply_patch for source edits and avoid shell heredocs in this repository.",
                    "why_it_matters": "This prevents source writes through shell command side effects.",
                    "source_refs": ["turn:1", "not-allowed"],
                    "expires": "turns:2",
                    "confidence": 0.9,
                },
                {
                    "kind": "fact",
                    "summary": "ignored by max_cards",
                    "source_refs": ["tool:abc"],
                },
            ],
            "dropped": [{"reason": "raw_detail", "summary": "large stdout omitted"}],
        },
        request,
    )

    assert len(result.cards) == 1
    card = result.cards[0]
    assert card.kind == "decision"
    assert len(card.summary) <= 80
    assert card.source_refs == ("turn:1",)
    assert card.created_turn == 4
    assert result.dropped == ({"reason": "raw_detail", "summary": "large stdout omitted"},)


def test_short_term_memory_buffer_recalls_by_query_and_expires_by_turns():
    fresh = ShortTermMemoryCard(
        kind="constraint",
        summary="Use apply_patch for source edits.",
        why_it_matters="Manual source edits should not go through shell heredocs.",
        source_refs=("turn:1",),
        expires="turns:5",
        created_turn=10,
        confidence=0.9,
    )
    expired = ShortTermMemoryCard(
        kind="warning",
        summary="Old verifier result mentioned pytest.",
        why_it_matters="This was only useful in an earlier branch.",
        source_refs=("turn:2",),
        expires="turns:1",
        created_turn=1,
        confidence=1.0,
    )
    buffer = ShortTermMemoryBuffer([fresh, expired])

    result = buffer.recall("apply_patch source edit", current_turn=11, limit=3)

    assert [card.card_id for card in result.cards] == [fresh.card_id]
    assert result.dropped["expired"] == 1


def test_short_term_memory_llm_compressor_uses_model_payload():
    calls = []

    def fake_call_json(model_backend, model_auth, prompt, model, base_url, timeout):
        calls.append(
            {
                "model_backend": model_backend,
                "model_auth": model_auth,
                "prompt": prompt,
                "model": model,
                "base_url": base_url,
                "timeout": timeout,
            }
        )
        return {
            "cards": [
                {
                    "kind": "blocker",
                    "summary": "Verifier failed because cleanup ran before final output was checked.",
                    "why_it_matters": "The next turn should keep verifier side effects visible until closeout.",
                    "source_refs": ["tool:pytest"],
                    "expires": "turns:4",
                    "confidence": 0.8,
                }
            ]
        }

    request = ShortTermMemoryCompressionRequest(
        raw_text="pytest failed after cleanup removed the output before final closeout.",
        source_refs=("tool:pytest",),
        current_turn=7,
    )

    result = compress_short_term_memory_with_model(
        request,
        model_auth={"path": "auth.json", "access_token": "redacted"},
        call_json=fake_call_json,
        timeout=30,
    )

    assert calls
    assert "raw_text" in calls[0]["prompt"]
    assert result.cards[0].kind == "blocker"
    assert result.cards[0].created_turn == 7
    assert result.prompt_hash
