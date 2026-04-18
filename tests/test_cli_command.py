import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mew.cli_command import mew_command, mew_executable


class CliCommandTests(unittest.TestCase):
    def test_mew_executable_can_be_overridden_for_subprocess_workspaces(self):
        source_script = Path(__file__).resolve().parents[1] / "mew"
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                old_override = os.environ.get("MEW_EXECUTABLE")
                os.environ["MEW_EXECUTABLE"] = str(source_script)
                try:
                    self.assertEqual(mew_executable(), str(source_script))
                    self.assertIn(str(source_script), mew_command("status"))
                finally:
                    if old_override is None:
                        os.environ.pop("MEW_EXECUTABLE", None)
                    else:
                        os.environ["MEW_EXECUTABLE"] = old_override
            finally:
                os.chdir(old_cwd)

    def test_mew_executable_preserves_path_launcher_outside_repo(self):
        source_script = Path(__file__).resolve().parents[1] / "mew"
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("MEW_EXECUTABLE", None)
                    with patch("sys.argv", [str(source_script), "self-improve"]):
                        self.assertEqual(mew_executable(), str(source_script))
                        self.assertIn(str(source_script), mew_command("work", 1, "--follow-status", "--json"))
            finally:
                os.chdir(old_cwd)

    def test_mew_executable_env_override_wins_over_path_launcher(self):
        source_script = Path(__file__).resolve().parents[1] / "mew"
        with patch.dict(os.environ, {"MEW_EXECUTABLE": "/tmp/custom-mew"}):
            with patch("sys.argv", [str(source_script), "self-improve"]):
                self.assertEqual(mew_executable(), "/tmp/custom-mew")

    def test_mew_executable_ignores_non_mew_path_launcher(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("MEW_EXECUTABLE", None)
                    with patch("sys.argv", ["/usr/local/bin/pytest"]):
                        self.assertEqual(mew_executable(), "mew")
            finally:
                os.chdir(old_cwd)
