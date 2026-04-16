import unittest

from mew.codex_api import decode_sse_data_line, extract_sse_text, sse_text_delta


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
