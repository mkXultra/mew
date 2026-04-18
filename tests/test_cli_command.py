import os
from pathlib import Path
import tempfile
import unittest

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
