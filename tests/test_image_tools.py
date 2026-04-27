import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.image_tools import read_image_with_model
from mew.work_session import execute_work_tool


ONE_BY_ONE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/ax7j6kAAAAASUVORK5CYII="
)


class ImageToolsTests(unittest.TestCase):
    def test_read_image_with_model_sends_allowed_image_as_data_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            image_path = root / "sample.png"
            image_path.write_bytes(ONE_BY_ONE_PNG)

            with patch("mew.image_tools.call_model_text", return_value="a tiny image") as call:
                result = read_image_with_model(
                    str(image_path),
                    [str(root)],
                    model_backend="codex",
                    model_auth={"access_token": "token"},
                    model="gpt-5.5",
                    base_url="https://example.invalid",
                    timeout=12,
                    prompt="transcribe",
                    detail="high",
                )

        self.assertEqual(result["type"], "image")
        self.assertEqual(result["mime_type"], "image/png")
        self.assertEqual(result["detail"], "high")
        self.assertEqual(result["text"], "a tiny image")
        image_inputs = call.call_args.kwargs["image_inputs"]
        self.assertEqual(image_inputs[0]["detail"], "high")
        self.assertTrue(image_inputs[0]["image_url"].startswith("data:image/png;base64,"))
        call.assert_called_once()

    def test_read_image_rejects_outside_allowed_roots(self):
        with tempfile.TemporaryDirectory() as allowed:
            with tempfile.TemporaryDirectory() as outside:
                path = Path(outside) / "sample.png"
                path.write_bytes(ONE_BY_ONE_PNG)

                with self.assertRaisesRegex(ValueError, "outside allowed read roots"):
                    read_image_with_model(
                        str(path),
                        [allowed],
                        model_backend="codex",
                        model_auth={"access_token": "token"},
                        model="gpt-5.5",
                        base_url="https://example.invalid",
                        timeout=12,
                    )

    def test_execute_work_tool_read_image_uses_model_context_without_tool_auth_parameters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            image_path = root / "sample.png"
            image_path.write_bytes(ONE_BY_ONE_PNG)

            with patch("mew.work_session.read_image_with_model", return_value={"text": "seen"}) as read_image:
                result = execute_work_tool(
                    "read_image",
                    {"path": "sample.png", "cwd": str(root), "detail": "low"},
                    [str(root)],
                    model_context={
                        "model_backend": "codex",
                        "model_auth": {"access_token": "token"},
                        "model": "gpt-5.5",
                        "base_url": "https://example.invalid",
                        "timeout": 10,
                    },
                )

        self.assertEqual(result, {"text": "seen"})
        kwargs = read_image.call_args.kwargs
        self.assertEqual(kwargs["model_auth"], {"access_token": "token"})
        self.assertEqual(kwargs["detail"], "low")
        self.assertEqual(read_image.call_args.args[0], str(image_path.resolve()))


if __name__ == "__main__":
    unittest.main()
