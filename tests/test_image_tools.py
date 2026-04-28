import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.image_tools import read_image_with_model, read_images_with_model
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

    def test_read_images_with_model_sends_ordered_images_in_one_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "frame_01.png"
            second = root / "frame_02.png"
            first.write_bytes(ONE_BY_ONE_PNG)
            second.write_bytes(ONE_BY_ONE_PNG)

            with patch("mew.image_tools.call_model_text", return_value="moves: north") as call:
                result = read_images_with_model(
                    [str(first), str(second)],
                    [str(root)],
                    model_backend="codex",
                    model_auth={"access_token": "token"},
                    model="gpt-5.5",
                    base_url="https://example.invalid",
                    timeout=12,
                    prompt="transcribe ordered frames",
                    detail="low",
                )

        self.assertEqual(result["type"], "images")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["detail"], "low")
        self.assertEqual(result["text"], "moves: north")
        self.assertEqual([Path(path).name for path in result["paths"]], ["frame_01.png", "frame_02.png"])
        image_inputs = call.call_args.kwargs["image_inputs"]
        self.assertEqual(len(image_inputs), 2)
        self.assertEqual([item["detail"] for item in image_inputs], ["low", "low"])
        prompt = call.call_args.args[2]
        self.assertIn("[1]", prompt)
        self.assertIn("frame_01.png", prompt)
        self.assertIn("[2]", prompt)
        self.assertIn("frame_02.png", prompt)
        call.assert_called_once()

    def test_read_images_rejects_outside_allowed_roots(self):
        with tempfile.TemporaryDirectory() as allowed:
            with tempfile.TemporaryDirectory() as outside:
                path = Path(outside) / "sample.png"
                path.write_bytes(ONE_BY_ONE_PNG)

                with self.assertRaisesRegex(ValueError, "outside allowed read roots"):
                    read_images_with_model(
                        [str(path)],
                        [allowed],
                        model_backend="codex",
                        model_auth={"access_token": "token"},
                        model="gpt-5.5",
                        base_url="https://example.invalid",
                        timeout=12,
                    )

    def test_read_images_truncates_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            image_path = root / "sample.png"
            image_path.write_bytes(ONE_BY_ONE_PNG)

            with patch("mew.image_tools.call_model_text", return_value="abcdef"):
                result = read_images_with_model(
                    [str(image_path)],
                    [str(root)],
                    model_backend="codex",
                    model_auth={"access_token": "token"},
                    model="gpt-5.5",
                    base_url="https://example.invalid",
                    timeout=12,
                    max_output_chars=3,
                )

        self.assertEqual(result["text"], "abc")
        self.assertTrue(result["truncated"])

    def test_read_images_rejects_aggregate_payload_too_large(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "frame_01.png"
            second = root / "frame_02.png"
            first.write_bytes(ONE_BY_ONE_PNG)
            second.write_bytes(ONE_BY_ONE_PNG)

            with self.assertRaisesRegex(ValueError, "payload is too large"):
                read_images_with_model(
                    [str(first), str(second)],
                    [str(root)],
                    model_backend="codex",
                    model_auth={"access_token": "token"},
                    model="gpt-5.5",
                    base_url="https://example.invalid",
                    timeout=12,
                    max_total_bytes=len(ONE_BY_ONE_PNG),
                )

    def test_read_images_rejects_too_many_paths_with_chunk_hint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = []
            for index in range(17):
                image_path = root / f"frame_{index:02d}.png"
                image_path.write_bytes(ONE_BY_ONE_PNG)
                paths.append(str(image_path))

            with self.assertRaisesRegex(ValueError, "split larger ordered sets into chunks"):
                read_images_with_model(
                    paths,
                    [str(root)],
                    model_backend="codex",
                    model_auth={"access_token": "token"},
                    model="gpt-5.5",
                    base_url="https://example.invalid",
                    timeout=12,
                )

    def test_execute_work_tool_read_images_uses_model_context_without_tool_auth_parameters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            image_path = root / "sample.png"
            image_path.write_bytes(ONE_BY_ONE_PNG)

            with patch("mew.work_session.read_images_with_model", return_value={"text": "seen"}) as read_images:
                result = execute_work_tool(
                    "read_images",
                    {"paths": ["sample.png"], "cwd": str(root), "detail": "auto", "max_output_chars": 2000},
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
        kwargs = read_images.call_args.kwargs
        self.assertEqual(kwargs["model_auth"], {"access_token": "token"})
        self.assertEqual(kwargs["detail"], "auto")
        self.assertEqual(kwargs["max_output_chars"], 2000)
        self.assertEqual(read_images.call_args.args[0], [str(image_path.resolve())])


if __name__ == "__main__":
    unittest.main()
