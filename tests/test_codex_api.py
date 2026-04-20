import json
import os
import unittest
from unittest.mock import patch

from mew.codex_api import (
    call_codex_web_api,
    decode_sse_data_line,
    extract_sse_text,
    sse_text_delta,
)


class FakeUrlopenResponse:
    def __init__(self, lines, headers=None):
        self._lines = lines
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self._lines)

    def read(self):
        return b"".join(self._lines)


def sse_line(data):
    return f"data: {json.dumps(data)}\n".encode("utf-8")


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
