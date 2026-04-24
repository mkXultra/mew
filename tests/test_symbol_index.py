import json
import tempfile
import unittest
from pathlib import Path

from mew.symbol_index import rebuild_symbol_index, resolve_source_path, resolve_test_path
from mew.typed_memory import FileMemoryBackend


class SymbolIndexTests(unittest.TestCase):
    def test_rebuild_symbol_index_persists_file_pair_source_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FileMemoryBackend(tmp)

            entry = backend.write(
                "symbol_index.py changes should keep tests/test_symbol_index.py aligned.",
                scope="private",
                memory_type="project",
                memory_kind="file-pair",
                name="symbol index pair",
                source_path=" src/mew/symbol_index.py ",
                test_path=" tests/test_symbol_index.py ",
                structural_evidence="same-session read of source and test plus co-edit plan",
                focused_test_green=True,
                created_at="2026-04-21T19:00:00Z",
            )
            backend.write(
                "General preference note that should not enter the symbol index.",
                scope="private",
                memory_type="user",
                name="ignore me",
                created_at="2026-04-21T19:00:01Z",
            )

            index = rebuild_symbol_index(tmp)

            self.assertEqual(index["schema_version"], 1)
            record = index["sources"]["src/mew/symbol_index.py"]
            self.assertEqual(record["source_path"], "src/mew/symbol_index.py")
            self.assertEqual(record["test_path"], "tests/test_symbol_index.py")
            self.assertEqual(record["memory_ids"], [entry.id])

            saved_path = Path(tmp) / ".mew" / "durable" / "symbol_index.json"
            self.assertTrue(saved_path.exists())
            saved = json.loads(saved_path.read_text(encoding="utf-8"))
            self.assertEqual(saved, index)

            resolved = resolve_source_path("src/mew/symbol_index.py", tmp)
            self.assertEqual(resolved, record)

            reverse_resolved = resolve_test_path("tests/test_symbol_index.py", tmp)
            self.assertEqual(reverse_resolved, record)
