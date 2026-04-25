from mew import memory_explore
from mew.memory_explore import HANDOFF_KEYS, MemoryExploreProvider, explore_memory


def test_memory_explore_provider_returns_handoff_from_active_and_typed_memory(monkeypatch, tmp_path):
    calls = []

    def fake_recall_memory(state, query, **kwargs):
        calls.append((query, kwargs))
        if kwargs.get("memory_kind") == "file-pair":
            return [
                {
                    "id": "private/project/pair",
                    "memory_scope": "private",
                    "memory_type": "project",
                    "memory_kind": "file-pair",
                    "name": "work session pair",
                    "description": "Pair src/mew/work_session.py with tests/test_work_session.py",
                    "source_path": "src/mew/work_session.py",
                    "test_path": "tests/test_work_session.py",
                    "body": "Do not expose this body in refs.",
                }
            ]
        return [
            {
                "id": "team/reference/symbol",
                "memory_scope": "team",
                "memory_type": "reference",
                "memory_kind": "",
                "name": "symbol hit",
                "description": "The symbol is implemented in src/mew/memory.py and covered by tests/test_work_session.py.",
                "path": ".mew/memory/private/project/hidden.md",
                "text": "Do not expose this text in refs.",
            }
        ]

    monkeypatch.setattr(memory_explore, "recall_memory", fake_recall_memory)
    active_memory = {
        "terms": ["memory", "explore"],
        "items": [
            {
                "id": "private/project/active",
                "memory_type": "project",
                "memory_kind": "",
                "name": "active handoff hint",
                "description": "Review src/mew/commands.py before editing tests/test_commands.py.",
                "path": ".mew/memory/private/project/active.md",
                "text": "Sensitive body should not be copied into memory_refs.",
            }
        ],
    }

    result = MemoryExploreProvider(base_dir=tmp_path).explore(
        {"memory": {}},
        query="memory explore",
        active_memory=active_memory,
    )

    assert tuple(result.keys()) == HANDOFF_KEYS
    assert result["exact_blockers"] == []
    assert result["cached_window_refs"] == []
    assert "src/mew/commands.py" in result["target_paths"]
    assert "src/mew/memory.py" in result["target_paths"]
    assert "src/mew/work_session.py" in result["target_paths"]
    assert "tests/test_work_session.py" in result["candidate_edit_paths"]
    assert ".mew/memory/private/project/hidden.md" not in result["target_paths"]
    assert any(kwargs.get("memory_kind") == "file-pair" for _, kwargs in calls)
    assert all("body" not in ref and "text" not in ref for ref in result["memory_refs"])
    assert any(ref.get("memory_kind") == "file-pair" for ref in result["memory_refs"])
    assert all(not str(ref.get("path", "")).startswith(".mew/memory/private/") for ref in result["memory_refs"])


def test_memory_explore_provider_preserves_cached_window_refs_without_file_reads(monkeypatch):
    monkeypatch.setattr(memory_explore, "recall_memory", lambda *args, **kwargs: [])
    active_memory = {
        "items": [
            {
                "id": "private/project/window",
                "memory_type": "project",
                "memory_kind": "file-pair",
                "source_path": "src/mew/foo.py",
                "test_path": "tests/test_foo.py",
                "cached_window_refs": [
                    {
                        "path": "src/mew/foo.py",
                        "line_start": 10,
                        "line_end": 20,
                        "source": "memory",
                    }
                ],
            }
        ]
    }

    result = explore_memory({"memory": {}}, query="", active_memory=active_memory)

    assert result["cached_window_refs"] == [
        {"path": "src/mew/foo.py", "line_start": 10, "line_end": 20, "source": "memory"}
    ]
    assert result["target_paths"] == ["src/mew/foo.py", "tests/test_foo.py"]
    assert result["candidate_edit_paths"] == ["src/mew/foo.py", "tests/test_foo.py"]
    assert result["memory_refs"] == [
        {
            "id": "private/project/window",
            "memory_type": "project",
            "memory_kind": "file-pair",
            "source_path": "src/mew/foo.py",
            "test_path": "tests/test_foo.py",
        }
    ]


def test_memory_explore_provider_rejects_traversal_and_tilde_paths(monkeypatch):
    monkeypatch.setattr(memory_explore, "recall_memory", lambda *args, **kwargs: [])
    active_memory = {
        "items": [
            {
                "id": "private/project/unsafe",
                "memory_type": "project",
                "memory_kind": "file-pair",
                "source_path": "../secret.py",
                "test_path": "tests/test_good.py",
                "target_paths": [
                    "src/mew/../secret.py",
                    "C:\\Users\\mk\\secret.py",
                    "~/secret.py",
                    "src/mew/~user.py",
                    "src/mew/good.py",
                ],
                "candidate_edit_paths": [
                    "tests/../secret.py",
                    "C:\\Users\\mk\\test_secret.py",
                    "tests/test_good.py",
                ],
                "key": "unsafe key mentions ../from-key.py",
                "name": "unsafe name mentions ~/from-name.py",
                "description": "Ignore src/mew/../../secret.py and docs/~secret.md.",
                "reason": "unsafe reason mentions C:\\Users\\mk\\reason.py",
                "matched_terms": ["../from-matched.py", "~/from-matched.py"],
                "path": "~/.mew/private.md",
                "cached_window_refs": [
                    {"path": "../secret.py", "line_start": 1},
                    {"path": "src/mew/../secret.py", "line_start": 2},
                    {"path": "~/.ssh/config", "line_start": 3},
                    {"path": "C:\\Users\\mk\\secret.py", "line_start": 4},
                    {"path": "src/mew/good.py", "line_start": 5},
                ],
            }
        ]
    }

    result = explore_memory({"memory": {}}, query="", active_memory=active_memory)

    def assert_safe_paths(paths):
        for path in paths:
            parts = path.split("/")
            assert ".." not in parts
            assert all(not part.startswith("~") for part in parts)
            assert not path.startswith("C:/")

    assert "tests/test_good.py" in result["target_paths"]
    assert "src/mew/good.py" in result["target_paths"]
    assert "tests/test_good.py" in result["candidate_edit_paths"]
    assert "src/mew/good.py" in result["candidate_edit_paths"]
    assert_safe_paths(result["target_paths"])
    assert_safe_paths(result["candidate_edit_paths"])
    cached_paths = [ref["path"] for ref in result["cached_window_refs"]]
    assert "src/mew/good.py" in cached_paths
    assert_safe_paths(cached_paths)
    ref = result["memory_refs"][0]
    assert ref["id"] == "private/project/unsafe"
    assert ref["memory_type"] == "project"
    assert ref["memory_kind"] == "file-pair"
    assert ref.get("test_path") == "tests/test_good.py"
    assert "source_path" not in ref
    assert "path" not in ref
    for key in ("key", "name", "description", "reason", "matched_terms"):
        assert key not in ref
    serialized_refs = repr(result["memory_refs"])
    for unsafe in ("..", "~", "Users", "from-key.py", "from-name.py", "from-matched.py", "reason.py"):
        assert unsafe not in serialized_refs
