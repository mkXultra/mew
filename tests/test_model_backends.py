import unittest
from unittest.mock import patch

from mew.errors import CodexApiError, MewError
from mew.model_backends import (
    call_model_json,
    load_model_auth,
    model_backend_label,
    normalize_model_backend,
)


class ModelBackendTests(unittest.TestCase):
    def test_normalizes_codex_aliases(self):
        self.assertEqual(normalize_model_backend(None), "codex")
        self.assertEqual(normalize_model_backend("codex"), "codex")
        self.assertEqual(normalize_model_backend("CODEX-WEB"), "codex")
        self.assertEqual(normalize_model_backend("codex_web"), "codex")

    def test_rejects_unknown_backend(self):
        with self.assertRaises(MewError):
            normalize_model_backend("unknown")

    def test_labels_codex_backend(self):
        self.assertEqual(model_backend_label("codex"), "Codex Web API")

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

    def test_call_model_json_rejects_unknown_backend(self):
        with self.assertRaises((CodexApiError, MewError)):
            call_model_json("unknown", {}, "prompt", "model", "url", 10)


if __name__ == "__main__":
    unittest.main()
