import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.anthropic_api import call_anthropic_json, extract_anthropic_text, load_anthropic_auth


class FakeHTTPResponse:
    def __init__(self, body):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class AnthropicApiTests(unittest.TestCase):
    def test_load_anthropic_auth_from_env(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            auth = load_anthropic_auth()

        self.assertEqual(auth, {"path": "$ANTHROPIC_API_KEY", "api_key": "env-key"})

    def test_load_anthropic_auth_from_plain_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "anthropic.key"
            path.write_text("file-key\n", encoding="utf-8")
            auth = load_anthropic_auth(str(path))

        self.assertEqual(auth["api_key"], "file-key")
        self.assertTrue(auth["path"].endswith("anthropic.key"))

    def test_load_anthropic_auth_from_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "anthropic.json"
            path.write_text('{"api_key": "json-key"}', encoding="utf-8")
            auth = load_anthropic_auth(str(path))

        self.assertEqual(auth["api_key"], "json-key")

    def test_extract_anthropic_text_concatenates_text_blocks(self):
        text = extract_anthropic_text(
            {
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "text", "text": " world"},
                    {"type": "tool_use", "name": "ignored"},
                ]
            }
        )

        self.assertEqual(text, "hello world")

    def test_call_anthropic_json_posts_messages_request(self):
        body = {"content": [{"type": "text", "text": '{"summary": "ok"}'}]}
        with patch(
            "mew.anthropic_api.urllib.request.urlopen",
            return_value=FakeHTTPResponse(json.dumps(body)),
        ) as urlopen:
            result = call_anthropic_json(
                {"api_key": "key"},
                "prompt",
                "claude-sonnet-4-5",
                "https://api.anthropic.com/v1",
                5,
            )

        self.assertEqual(result, {"summary": "ok"})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.anthropic.com/v1/messages")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "claude-sonnet-4-5")
        self.assertEqual(payload["messages"][0]["content"], "prompt")


if __name__ == "__main__":
    unittest.main()
