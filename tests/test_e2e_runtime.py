import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import ThreadingHTTPServer
from io import StringIO
from urllib.request import Request, urlopen
from unittest.mock import patch

from mew.cli import main
from mew.commands import make_webhook_handler
from mew.state import load_state, state_lock


class RuntimeE2ETests(unittest.TestCase):
    def test_webhook_event_runs_through_ai_outbox_and_notify(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                server = ThreadingHTTPServer(("127.0.0.1", 0), make_webhook_handler(token="secret"))
                server.timeout = 1
                thread = threading.Thread(target=server.handle_request)
                thread.daemon = True
                thread.start()
                try:
                    request = Request(
                        f"http://127.0.0.1:{server.server_port}/event/github_webhook?source=test",
                        data=b'{"ref":"main"}',
                        headers={
                            "Authorization": "Bearer secret",
                            "Content-Type": "application/json",
                        },
                        method="POST",
                    )
                    with urlopen(request, timeout=5) as response:
                        self.assertEqual(json.loads(response.read().decode("utf-8"))["event_id"], 1)
                finally:
                    server.server_close()
                    thread.join(timeout=5)

                prompts = []

                def fake_call_model_json(model_backend, model_auth, prompt, model, base_url, timeout):
                    prompts.append(prompt)
                    self.assertIn("github_webhook", prompt)
                    self.assertIn('"source": "test"', prompt)
                    self.assertIn('"ref": "main"', prompt)
                    if len(prompts) == 1:
                        return {
                            "summary": "saw github webhook",
                            "decisions": [
                                {
                                    "type": "send_message",
                                    "message_type": "assistant",
                                    "text": "handled github webhook",
                                }
                            ],
                        }
                    return {
                        "summary": "notify user",
                        "actions": [
                            {
                                "type": "send_message",
                                "message_type": "assistant",
                                "text": "handled github webhook",
                            }
                        ],
                    }

                with patch("mew.runtime.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.agent.call_model_json", side_effect=fake_call_model_json) as call_model:
                        with patch(
                            "mew.runtime.run_command_record",
                            return_value={"exit_code": 0, "stderr": ""},
                        ) as notify:
                            with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                                code = main(
                                    [
                                        "run",
                                        "--once",
                                        "--ai",
                                        "--auth",
                                        "auth.json",
                                        "--interval",
                                        "999",
                                        "--poll-interval",
                                        "0.01",
                                        "--notify-command",
                                        "notify-tool",
                                    ]
                                )

                self.assertEqual(code, 0)
                self.assertIn("reason=external_event", stdout.getvalue())
                self.assertEqual(call_model.call_count, 2)
                notify.assert_called_once()
                self.assertEqual(notify.call_args.kwargs["extra_env"]["MEW_OUTBOX_TEXT"], "handled github webhook")

                with state_lock():
                    state = load_state()
                self.assertEqual(state["inbox"][0]["type"], "github_webhook")
                self.assertIsNotNone(state["inbox"][0]["processed_at"])
                self.assertEqual(state["outbox"][0]["text"], "handled github webhook")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
