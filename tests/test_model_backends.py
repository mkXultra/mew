import unittest
from unittest.mock import patch

import mew.model_backends as backends
from mew.errors import ModelBackendError, MewError
from mew.model_backends import (
    call_model_json,
    load_model_auth,
    model_backend_default_base_url,
    model_backend_default_model,
    model_backend_label,
    normalize_model_backend,
)


class ModelBackendTests(unittest.TestCase):
    def test_normalizes_codex_aliases(self):
        self.assertEqual(normalize_model_backend(None), "codex")
        self.assertEqual(normalize_model_backend("codex"), "codex")
        self.assertEqual(normalize_model_backend("CODEX-WEB"), "codex")
        self.assertEqual(normalize_model_backend("codex_web"), "codex")

    def test_normalizes_claude_aliases(self):
        self.assertIn("claude", backends.supported_model_backends())
        self.assertEqual(normalize_model_backend("claude"), "claude")
        self.assertEqual(normalize_model_backend("anthropic"), "claude")

    def test_rejects_unknown_backend(self):
        with self.assertRaises(MewError):
            normalize_model_backend("unknown")

    def test_labels_codex_backend(self):
        self.assertEqual(model_backend_label("codex"), "Codex Web API")

    def test_labels_claude_backend(self):
        self.assertEqual(model_backend_label("anthropic"), "Claude Messages API")

    def test_backend_defaults_are_backend_specific(self):
        self.assertEqual(model_backend_default_model("codex"), "gpt-5.4")
        self.assertEqual(model_backend_default_model("claude"), "claude-sonnet-4-5")
        self.assertIn("chatgpt.com", model_backend_default_base_url("codex"))
        self.assertIn("anthropic.com", model_backend_default_base_url("claude"))

    def test_load_model_auth_delegates_to_codex_oauth_loader(self):
        with patch("mew.model_backends.load_codex_oauth", return_value={"path": "auth.json"}) as loader:
            auth = load_model_auth("codex", "auth.json")

        self.assertEqual(auth["path"], "auth.json")
        loader.assert_called_once_with("auth.json")

    def test_call_model_json_delegates_to_codex_json_call(self):
        expected = {"summary": "ok"}
        with patch("mew.model_backends.call_codex_json", return_value=expected) as call:
            result = call_model_json("codex", {"access_token": "x"}, "prompt", "model", "url", 10)

        self.assertEqual(result, expected)
        call.assert_called_once_with({"access_token": "x"}, "prompt", "model", "url", 10)

    def test_call_model_json_forwards_stream_callback_to_codex(self):
        expected = {"summary": "ok"}

        def callback(delta):
            return None

        with patch("mew.model_backends.call_codex_json", return_value=expected) as call:
            result = call_model_json(
                "codex",
                {"access_token": "x"},
                "prompt",
                "model",
                "url",
                10,
                on_text_delta=callback,
            )

        self.assertEqual(result, expected)
        call.assert_called_once_with(
            {"access_token": "x"},
            "prompt",
            "model",
            "url",
            10,
            on_text_delta=callback,
        )

    def test_load_model_auth_delegates_to_claude_auth_loader(self):
        with patch("mew.model_backends.load_anthropic_auth", return_value={"path": "key.txt"}) as loader:
            auth = load_model_auth("claude", "key.txt")

        self.assertEqual(auth["path"], "key.txt")
        loader.assert_called_once_with("key.txt")

    def test_call_model_json_delegates_to_claude_json_call(self):
        expected = {"summary": "ok"}
        with patch("mew.model_backends.call_anthropic_json", return_value=expected) as call:
            result = call_model_json("claude", {"api_key": "x"}, "prompt", "model", "url", 10)

        self.assertEqual(result, expected)
        call.assert_called_once_with({"api_key": "x"}, "prompt", "model", "url", 10)

    def test_can_register_backend_without_changing_dispatcher(self):
        class FakeBackend:
            name = "fake"
            aliases = ("fake-alias",)
            label = "Fake Backend"

            def load_auth(self, auth_path=None):
                return {"path": auth_path}

            def call_json(self, auth, prompt, model, base_url, timeout):
                return {"summary": prompt}

        previous_backends = dict(backends._BACKENDS)
        previous_names = list(backends._CANONICAL_NAMES)
        try:
            backends.register_model_backend(FakeBackend())
            self.assertEqual(normalize_model_backend("fake-alias"), "fake")
            self.assertEqual(load_model_auth("fake", "fake.auth"), {"path": "fake.auth"})
            self.assertEqual(
                call_model_json("fake", {}, "hello", "model", "url", 1),
                {"summary": "hello"},
            )
        finally:
            backends._BACKENDS.clear()
            backends._BACKENDS.update(previous_backends)
            backends._CANONICAL_NAMES[:] = previous_names

    def test_call_model_json_rejects_unknown_backend(self):
        with self.assertRaises((ModelBackendError, MewError)):
            call_model_json("unknown", {}, "prompt", "model", "url", 10)


if __name__ == "__main__":
    unittest.main()
