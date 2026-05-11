import json
import io
import os
import signal
import socket
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from mew.codex_api import (
    call_codex_json,
    call_codex_responses_raw,
    call_codex_web_api,
    decode_sse_data_line,
    extract_json_object,
    extract_response_refusal,
    extract_sse_text,
    extract_sse_response_parts,
    load_codex_oauth,
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

    def test_call_codex_responses_raw_sends_existing_body_without_prompt_wrapper(self):
        captured = {}
        request_body = {
            "model": "gpt-5.5",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
            "tools": [{"type": "function", "name": "finish", "parameters": {"type": "object"}}],
            "stream": True,
            "store": False,
        }

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["url"] = request.full_url
            return FakeUrlopenResponse(
                [b"data: {\"type\":\"response.completed\",\"response\":{\"id\":\"resp-1\"}}\n"],
                headers={"content-type": "text/event-stream"},
            )

        with patch("mew.codex_api.urllib.request.urlopen", side_effect=fake_urlopen):
            raw, content_type = call_codex_responses_raw(
                {"access_token": "token"},
                request_body,
                "https://example.invalid/api",
                1,
            )

        self.assertEqual(captured["body"], request_body)
        self.assertEqual(captured["url"], "https://example.invalid/api/responses")
        self.assertEqual(content_type, "text/event-stream")
        self.assertIn("response.completed", raw)

    def test_call_codex_web_api_sends_image_inputs(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeUrlopenResponse(
                [json.dumps({"output_text": "image text"}).encode("utf-8")],
                headers={"content-type": "application/json"},
            )

        with patch("mew.codex_api.urllib.request.urlopen", side_effect=fake_urlopen):
            text = call_codex_web_api(
                {"access_token": "token"},
                "describe",
                "gpt-5.5",
                "https://example.invalid",
                1,
                image_inputs=[
                    {
                        "image_url": "data:image/png;base64,AAAA",
                        "detail": "high",
                    }
                ],
            )

        self.assertEqual(text, "image text")
        content = captured["body"]["input"][0]["content"]
        self.assertEqual(content[0], {"type": "input_text", "text": "describe"})
        self.assertEqual(
            content[1],
            {
                "type": "input_image",
                "image_url": "data:image/png;base64,AAAA",
                "detail": "high",
            },
        )

    def test_call_codex_web_api_refreshes_expired_legacy_auth_before_request(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            auth_path = Path(temp_dir) / "auth.json"
            auth_path.write_text(
                json.dumps(
                    {
                        "type": "oauth",
                        "access": "old-access",
                        "refresh": "old-refresh",
                        "expires": 0,
                        "accountId": "acct",
                    }
                ),
                encoding="utf-8",
            )
            auth = load_codex_oauth(auth_path)
            seen = []

            def fake_urlopen(request, timeout):
                seen.append((request.full_url, request.get_header("Authorization")))
                if request.full_url == "https://auth.example/token":
                    content_type = request.get_header("Content-type") or request.get_header("Content-Type")
                    self.assertEqual(content_type, "application/x-www-form-urlencoded")
                    refresh_body = urllib.parse.parse_qs(request.data.decode("utf-8"))
                    self.assertEqual(refresh_body["refresh_token"], ["old-refresh"])
                    return FakeUrlopenResponse(
                        [
                            json.dumps(
                                {
                                    "access_token": "new-access",
                                    "refresh_token": "new-refresh",
                                    "id_token": "new-id",
                                }
                            ).encode("utf-8")
                        ],
                        headers={"content-type": "application/json"},
                    )
                self.assertEqual(request.get_header("Authorization"), "Bearer new-access")
                return FakeUrlopenResponse(
                    [json.dumps({"output_text": "ok"}).encode("utf-8")],
                    headers={"content-type": "application/json"},
                )

            with patch.dict(os.environ, {"CODEX_REFRESH_TOKEN_URL_OVERRIDE": "https://auth.example/token"}):
                with patch("mew.codex_api.urllib.request.urlopen", side_effect=fake_urlopen):
                    text = call_codex_web_api(
                        auth,
                        "prompt",
                        "model",
                        "https://example.invalid",
                        10,
                    )

            self.assertEqual(text, "ok")
            self.assertEqual(
                [url for url, _header in seen],
                ["https://auth.example/token", "https://example.invalid/responses"],
            )
            refreshed = json.loads(auth_path.read_text(encoding="utf-8"))
            self.assertEqual(refreshed["access"], "new-access")
            self.assertEqual(refreshed["refresh"], "new-refresh")
            self.assertEqual(auth["access_token"], "new-access")
            self.assertEqual(auth["refresh_token"], "new-refresh")

    def test_call_codex_web_api_refreshes_and_retries_after_401(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            auth_path = Path(temp_dir) / "auth.json"
            auth_path.write_text(
                json.dumps(
                    {
                        "auth_mode": "chatgpt",
                        "tokens": {
                            "id_token": "old-id",
                            "access_token": "old-access",
                            "refresh_token": "old-refresh",
                            "account_id": "acct",
                        },
                        "last_refresh": "2026-04-30T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            auth = load_codex_oauth(auth_path)
            response_auth_headers = []

            def fake_urlopen(request, timeout):
                if request.full_url == "https://auth.example/token":
                    content_type = request.get_header("Content-type") or request.get_header("Content-Type")
                    self.assertEqual(content_type, "application/x-www-form-urlencoded")
                    refresh_body = urllib.parse.parse_qs(request.data.decode("utf-8"))
                    self.assertEqual(refresh_body["refresh_token"], ["old-refresh"])
                    return FakeUrlopenResponse(
                        [
                            json.dumps(
                                {
                                    "access_token": "new-access",
                                    "refresh_token": "new-refresh",
                                    "id_token": "new-id",
                                }
                            ).encode("utf-8")
                        ],
                        headers={"content-type": "application/json"},
                    )
                response_auth_headers.append(request.get_header("Authorization"))
                if request.get_header("Authorization") == "Bearer old-access":
                    raise urllib.error.HTTPError(
                        request.full_url,
                        401,
                        "Unauthorized",
                        hdrs=None,
                        fp=io.BytesIO(b'{"detail":"token_expired"}'),
                    )
                return FakeUrlopenResponse(
                    [json.dumps({"output_text": "ok"}).encode("utf-8")],
                    headers={"content-type": "application/json"},
                )

            with patch.dict(os.environ, {"CODEX_REFRESH_TOKEN_URL_OVERRIDE": "https://auth.example/token"}):
                with patch("mew.codex_api.urllib.request.urlopen", side_effect=fake_urlopen):
                    text = call_codex_web_api(
                        auth,
                        "prompt",
                        "model",
                        "https://example.invalid",
                        10,
                    )

            self.assertEqual(text, "ok")
            self.assertEqual(response_auth_headers, ["Bearer old-access", "Bearer new-access"])
            refreshed = json.loads(auth_path.read_text(encoding="utf-8"))
            self.assertEqual(refreshed["tokens"]["id_token"], "new-id")
            self.assertEqual(refreshed["tokens"]["access_token"], "new-access")
            self.assertEqual(refreshed["tokens"]["refresh_token"], "new-refresh")
            self.assertRegex(refreshed["last_refresh"], r"^\d{4}-\d{2}-\d{2}T")
            self.assertEqual(auth["access_token"], "new-access")

    def test_call_codex_web_api_rejects_refresh_response_without_access_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            auth_path = Path(temp_dir) / "auth.json"
            auth_path.write_text(
                json.dumps(
                    {
                        "auth_mode": "chatgpt",
                        "tokens": {
                            "id_token": "old-id",
                            "access_token": "old-access",
                            "refresh_token": "old-refresh",
                            "account_id": "acct",
                        },
                    }
                ),
                encoding="utf-8",
            )
            auth = load_codex_oauth(auth_path)

            def fake_urlopen(request, timeout):
                if request.full_url == "https://auth.example/token":
                    return FakeUrlopenResponse(
                        [json.dumps({"refresh_token": "new-refresh"}).encode("utf-8")],
                        headers={"content-type": "application/json"},
                    )
                raise urllib.error.HTTPError(
                    request.full_url,
                    401,
                    "Unauthorized",
                    hdrs=None,
                    fp=io.BytesIO(b'{"detail":"token_expired"}'),
                )

            with patch.dict(os.environ, {"CODEX_REFRESH_TOKEN_URL_OVERRIDE": "https://auth.example/token"}):
                with patch("mew.codex_api.urllib.request.urlopen", side_effect=fake_urlopen):
                    with self.assertRaisesRegex(CodexApiError, "HTTP 401"):
                        call_codex_web_api(
                            auth,
                            "prompt",
                            "model",
                            "https://example.invalid",
                            10,
                        )

            unchanged = json.loads(auth_path.read_text(encoding="utf-8"))
            self.assertEqual(unchanged["tokens"]["access_token"], "old-access")

    def test_call_codex_web_api_converts_second_401_after_refresh_to_codex_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            auth_path = Path(temp_dir) / "auth.json"
            auth_path.write_text(
                json.dumps(
                    {
                        "auth_mode": "chatgpt",
                        "tokens": {
                            "id_token": "old-id",
                            "access_token": "old-access",
                            "refresh_token": "old-refresh",
                            "account_id": "acct",
                        },
                    }
                ),
                encoding="utf-8",
            )
            auth = load_codex_oauth(auth_path)

            def fake_urlopen(request, timeout):
                if request.full_url == "https://auth.example/token":
                    return FakeUrlopenResponse(
                        [
                            json.dumps(
                                {
                                    "access_token": "new-access",
                                    "refresh_token": "new-refresh",
                                }
                            ).encode("utf-8")
                        ],
                        headers={"content-type": "application/json"},
                    )
                raise urllib.error.HTTPError(
                    request.full_url,
                    401,
                    "Unauthorized",
                    hdrs=None,
                    fp=io.BytesIO(b'{"detail":"still_expired"}'),
                )

            with patch.dict(os.environ, {"CODEX_REFRESH_TOKEN_URL_OVERRIDE": "https://auth.example/token"}):
                with patch("mew.codex_api.urllib.request.urlopen", side_effect=fake_urlopen):
                    with self.assertRaisesRegex(CodexApiError, "HTTP 401"):
                        call_codex_web_api(
                            auth,
                            "prompt",
                            "model",
                            "https://example.invalid",
                            10,
                        )

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

    def test_extract_json_object_accepts_valid_object_before_trailing_text(self):
        payload = extract_json_object('{"summary":"ok","tool_calls":[]} trailing note {"ignored": true}')

        self.assertEqual(payload, {"summary": "ok", "tool_calls": []})

    def test_extract_json_object_does_not_skip_malformed_outer_object_for_nested_object(self):
        with self.assertRaisesRegex(CodexApiError, "response did not contain valid JSON object"):
            extract_json_object('{"summary": {"nested": true} trailing')

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
            with patch("mew.codex_api.time.monotonic", side_effect=[0.0, 0.0, 0.0]):
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

    def test_call_codex_web_api_hard_deadline_interrupts_blocked_stream_read(self):
        class BlockingReadResponse(FakeUrlopenResponse):
            def readline(self):
                handler = signal.getsignal(signal.SIGALRM)
                handler(signal.SIGALRM, None)
                return b""

        response = BlockingReadResponse([], headers={"content-type": "text/event-stream"})

        with patch("mew.codex_api.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(CodexApiError, "request timed out"):
                call_codex_web_api(
                    {"access_token": "token"},
                    "prompt",
                    "model",
                    "https://example.invalid",
                    45,
                )

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
        self.assertEqual(response.socket_timeouts, [44.0, 43.5, 43.0])

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
