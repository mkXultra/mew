import json
import os
import socket
import unittest
from unittest.mock import patch

from mew.codex_api import (
    call_codex_json,
    call_codex_web_api,
    decode_sse_data_line,
    extract_response_refusal,
    extract_sse_text,
    extract_sse_response_parts,
    sse_text_delta,
)
from mew.errors import CodexApiError, CodexRefusalError


class FakeUrlopenResponse:
    def __init__(self, lines, headers=None, readline_side_effects=None):
        self._lines = list(lines)
        self.headers = headers or {}
        self._readline_index = 0
        self._readline_side_effects = list(readline_side_effects or [])
        self.socket_timeouts = []
        self.fp = _FakeResponseStream(self.socket_timeouts)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        while True:
            line = self.readline()
            if not line:
                break
            yield line

    def readline(self):
        if self._readline_side_effects:
            effect = self._readline_side_effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            return effect
        if self._readline_index >= len(self._lines):
            return b""
        line = self._lines[self._readline_index]
        self._readline_index += 1
        return line

    def read(self):
        if self._readline_index >= len(self._lines):
            return b""
        remaining = self._lines[self._readline_index :]
        self._readline_index = len(self._lines)
        return b"".join(remaining)


def sse_line(data):
    return f"data: {json.dumps(data)}\n".encode("utf-8")


class _FakeSocket:
    def __init__(self, recorded):
        self._recorded = recorded

    def settimeout(self, value):
        self._recorded.append(value)


class _FakeResponseRaw:
    def __init__(self, recorded):
        self._sock = _FakeSocket(recorded)


class _FakeResponseStream:
    def __init__(self, recorded):
        self.raw = _FakeResponseRaw(recorded)


class CodexApiTests(unittest.TestCase):
    def test_sse_text_delta_helpers_extract_streaming_text(self):
        raw = "\n".join(
            [
                'data: {"type":"response.output_text.delta","delta":"hel"}',
                'data: {"type":"response.output_text.delta","delta":"lo"}',
                "data: [DONE]",
            ]
        )

        self.assertEqual(extract_sse_text(raw), "hello")
        deltas = []
        for line in raw.splitlines():
            delta = sse_text_delta(decode_sse_data_line(line))
            if delta:
                deltas.append(delta)
        self.assertEqual(deltas, ["hel", "lo"])

    def test_extract_sse_response_parts_separates_refusal_from_text(self):
        raw = "\n".join(
            [
                'data: {"type":"response.refusal.delta","delta":"no"}',
                'data: {"type":"response.refusal.delta","delta":"pe"}',
                "data: [DONE]",
            ]
        )

        parts = extract_sse_response_parts(raw)

        self.assertEqual(parts["text"], "")
        self.assertEqual(parts["refusal"], "nope")
        self.assertEqual(extract_sse_text(raw), "")

    def test_extract_response_refusal_reads_completed_response_payload(self):
        payload = {
            "response": {
                "output": [
                    {
                        "content": [
                            {
                                "type": "refusal",
                                "text": "cannot comply",
                            }
                        ]
                    }
                ]
            }
        }

        self.assertEqual(extract_response_refusal(payload), "cannot comply")

    def test_call_codex_web_api_streams_deltas_when_content_type_is_missing(self):
        lines = [
            sse_line({"type": "response.output_text.delta", "delta": "hel"}),
            sse_line({"type": "response.output_text.delta", "delta": "lo"}),
            b"data: [DONE]\n",
        ]
        deltas = []

        with patch(
            "mew.codex_api.urllib.request.urlopen",
            return_value=FakeUrlopenResponse(lines, headers={}),
        ):
            text = call_codex_web_api(
                {"access_token": "token"},
                "prompt",
                "model",
                "https://example.invalid",
                1,
                on_text_delta=deltas.append,
            )

        self.assertEqual(text, "hello")
        self.assertEqual(deltas, ["hel", "lo"])

    def test_call_codex_web_api_sends_default_high_reasoning_effort(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeUrlopenResponse(
                [json.dumps({"output_text": "ok"}).encode("utf-8")],
                headers={"content-type": "application/json"},
            )

        with patch.dict(os.environ, {}, clear=True):
            with patch("mew.codex_api.urllib.request.urlopen", side_effect=fake_urlopen):
                text = call_codex_web_api(
                    {"access_token": "token"},
                    "prompt",
                    "gpt-5.4",
                    "https://example.invalid",
                    1,
                )

        self.assertEqual(text, "ok")
        self.assertEqual(captured["body"]["reasoning"], {"effort": "high"})
        self.assertTrue(captured["body"]["stream"])

    def test_call_codex_web_api_raises_refusal_for_streamed_refusal_only(self):
        response = FakeUrlopenResponse(
            [
                sse_line({"type": "response.refusal.delta", "delta": "cannot"}),
                sse_line({"type": "response.refusal.delta", "delta": " comply"}),
                b"data: [DONE]\n",
            ],
            headers={"content-type": "text/event-stream"},
        )

        with patch("mew.codex_api.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(CodexRefusalError, "model returned refusal: cannot comply"):
                call_codex_web_api(
                    {"access_token": "token"},
                    "prompt",
                    "model",
                    "https://example.invalid",
                    5,
                )

    def test_call_codex_web_api_raises_refusal_for_completed_response_fallback(self):
        response = FakeUrlopenResponse(
            [
                sse_line(
                    {
                        "type": "response.completed",
                        "response": {
                            "output": [
                                {
                                    "content": [
                                        {
                                            "type": "refusal",
                                            "text": "fallback refusal",
                                        }
                                    ]
                                }
                            ]
                        },
                    }
                ),
                b"data: [DONE]\n",
            ],
            headers={"content-type": "text/event-stream"},
        )

        with patch("mew.codex_api.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(CodexRefusalError, "model returned refusal: fallback refusal"):
                call_codex_web_api(
                    {"access_token": "token"},
                    "prompt",
                    "model",
                    "https://example.invalid",
                    5,
                )

    def test_call_codex_web_api_raises_refusal_for_non_stream_json_payload(self):
        payload = {
            "response": {
                "output": [
                    {
                        "content": [
                            {
                                "type": "refusal",
                                "text": "json refusal",
                            }
                        ]
                    }
                ]
            }
        }
        response = FakeUrlopenResponse(
            [json.dumps(payload).encode("utf-8")],
            headers={"content-type": "application/json"},
        )

        with patch("mew.codex_api.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(CodexRefusalError, "model returned refusal: json refusal"):
                call_codex_web_api(
                    {"access_token": "token"},
                    "prompt",
                    "model",
                    "https://example.invalid",
                    5,
                )

    def test_call_codex_json_preserves_refusal_instead_of_parse_failure(self):
        response = FakeUrlopenResponse(
            [
                sse_line({"type": "response.refusal.delta", "delta": "need approval"}),
                b"data: [DONE]\n",
            ],
            headers={"content-type": "text/event-stream"},
        )

        with patch("mew.codex_api.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(CodexRefusalError, "model returned refusal: need approval"):
                call_codex_json(
                    {"access_token": "token"},
                    "prompt",
                    "model",
                    "https://example.invalid",
                    5,
                )

    def test_call_codex_web_api_enforces_total_timeout_while_streaming(self):
        lines = [
            sse_line({"type": "response.output_text.delta", "delta": "hel"}),
            sse_line({"type": "response.output_text.delta", "delta": "lo"}),
            b"data: [DONE]\n",
        ]
        deltas = []

        with patch(
            "mew.codex_api.urllib.request.urlopen",
            return_value=FakeUrlopenResponse(lines, headers={"content-type": "text/event-stream"}),
        ):
            with patch("mew.codex_api.time.monotonic", side_effect=[0.0, 0.0, 0.0, 1.1, 1.1]):
                with self.assertRaisesRegex(CodexApiError, "request timed out"):
                    call_codex_web_api(
                        {"access_token": "token"},
                        "prompt",
                        "model",
                        "https://example.invalid",
                        1,
                        on_text_delta=deltas.append,
                    )

        self.assertLessEqual(len(deltas), 1)

    def test_call_codex_web_api_enforces_timeout_before_first_stream_chunk(self):
        deltas = []
        response = FakeUrlopenResponse(
            [],
            headers={"content-type": "text/event-stream"},
            readline_side_effects=[socket.timeout("idle")],
        )
        with patch("mew.codex_api.urllib.request.urlopen", return_value=response):
            with patch("mew.codex_api.time.monotonic", side_effect=[0.0, 0.0]):
                with self.assertRaisesRegex(CodexApiError, "request timed out"):
                    call_codex_web_api(
                        {"access_token": "token"},
                        "prompt",
                        "model",
                        "https://example.invalid",
                        1,
                        on_text_delta=deltas.append,
                    )

        self.assertEqual(deltas, [])

    def test_call_codex_web_api_enforces_timeout_when_keepalives_arrive_without_deltas(self):
        deltas = []
        response = FakeUrlopenResponse(
            [b": keepalive\n"],
            headers={"content-type": "text/event-stream"},
        )
        with patch("mew.codex_api.urllib.request.urlopen", return_value=response):
            with patch("mew.codex_api.time.monotonic", side_effect=[0.0, 0.0, 1.1]):
                with self.assertRaisesRegex(CodexApiError, "request timed out"):
                    call_codex_web_api(
                        {"access_token": "token"},
                        "prompt",
                        "model",
                        "https://example.invalid",
                        1,
                        on_text_delta=deltas.append,
                    )

        self.assertEqual(deltas, [])

    def test_call_codex_web_api_uses_remaining_request_timeout_for_stream_reads(self):
        deltas = []
        response = FakeUrlopenResponse(
            [sse_line({"type": "response.output_text.delta", "delta": "ok"}), b"data: [DONE]\n"],
            headers={"content-type": "text/event-stream"},
        )
        captured = {}

        def fake_urlopen(request, timeout):
            captured["timeout"] = timeout
            return response

        with patch("mew.codex_api.urllib.request.urlopen", side_effect=fake_urlopen):
            with patch(
                "mew.codex_api.time.monotonic",
                side_effect=[0.0, 0.0, 1.0, 1.0, 1.5, 1.5, 2.0, 2.0, 2.0],
            ):
                text = call_codex_web_api(
                    {"access_token": "token"},
                    "prompt",
                    "model",
                    "https://example.invalid",
                    45,
                    on_text_delta=deltas.append,
                )

        self.assertEqual(text, "ok")
        self.assertEqual(deltas, ["ok"])
        self.assertEqual(captured["timeout"], 45)
        self.assertEqual(response.socket_timeouts, [45.0, 44.0, 43.5])

    def test_call_codex_web_api_wraps_timed_out_response_reader_oserror(self):
        response = FakeUrlopenResponse(
            [],
            headers={"content-type": "text/event-stream"},
            readline_side_effects=[OSError("cannot read from timed out object")],
        )

        with patch("mew.codex_api.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(CodexApiError, "request timed out"):
                call_codex_web_api(
                    {"access_token": "token"},
                    "prompt",
                    "model",
                    "https://example.invalid",
                    45,
                )
