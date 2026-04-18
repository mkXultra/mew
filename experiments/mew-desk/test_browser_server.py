from __future__ import annotations

import importlib.util
import http.client
import json
import sys
import threading
import urllib.request
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("browser_server.py")
if str(MODULE_PATH.parent) not in sys.path:
    sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("browser_server", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
browser_server = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = browser_server
SPEC.loader.exec_module(browser_server)


def test_file_source_loads_view_model(tmp_path: Path) -> None:
    path = tmp_path / "desk.json"
    path.write_text(json.dumps({"pet_state": "typing", "counts": {"open_tasks": 2}}), encoding="utf-8")

    source = browser_server.FileViewModelSource(path)

    assert source.load()["pet_state"] == "typing"


def test_command_source_loads_view_model() -> None:
    source = browser_server.CommandViewModelSource(
        [
            sys.executable,
            "-c",
            'import json; print(json.dumps({"pet_state":"thinking","counts":{}}))',
        ]
    )

    assert source.load()["pet_state"] == "thinking"


def test_render_live_page_adds_meta_refresh() -> None:
    html = browser_server.render_live_page({"pet_state": "sleeping", "counts": {}}, refresh_seconds=12)

    assert '<meta http-equiv="refresh" content="12">' in html


def test_loopback_host_validation() -> None:
    assert browser_server.is_loopback_host("127.0.0.1:8765")
    assert browser_server.is_loopback_host("localhost:8765")
    assert browser_server.is_loopback_host("[::1]:8765")
    assert not browser_server.is_loopback_host("example.com")
    assert not browser_server.is_loopback_host("0.0.0.0")


def test_validate_bind_host_rejects_non_loopback() -> None:
    try:
        browser_server.validate_bind_host("0.0.0.0", allow_non_loopback=False)
    except ValueError as exc:
        assert "loopback" in str(exc)
    else:
        raise AssertionError("expected non-loopback host to be rejected")

    browser_server.validate_bind_host("0.0.0.0", allow_non_loopback=True)


def test_handler_serves_html_and_json(tmp_path: Path) -> None:
    path = tmp_path / "desk.json"
    path.write_text(
        json.dumps({"date": "2026-04-19", "pet_state": "alerting", "focus": "Need input", "counts": {}}),
        encoding="utf-8",
    )
    source = browser_server.FileViewModelSource(path)
    handler = browser_server.make_handler(source, refresh_seconds=5)
    server = browser_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base_url, timeout=5) as response:
            html = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/view-model", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert '<main data-state="alerting">' in html
    assert payload["focus"] == "Need input"


def test_handler_rejects_unknown_path_without_loading_source() -> None:
    class FailingSource:
        def load(self) -> dict[str, object]:
            raise AssertionError("source should not load for unknown paths")

    handler = browser_server.make_handler(FailingSource(), refresh_seconds=5)
    server = browser_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/favicon.ico", headers={"Host": f"127.0.0.1:{server.server_port}"})
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert response.status == 404
    assert body == "not found\n"


def test_handler_rejects_non_loopback_host_header(tmp_path: Path) -> None:
    path = tmp_path / "desk.json"
    path.write_text(json.dumps({"pet_state": "sleeping", "counts": {}}), encoding="utf-8")
    handler = browser_server.make_handler(browser_server.FileViewModelSource(path), refresh_seconds=5)
    server = browser_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/", headers={"Host": "example.com"})
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert response.status == 403
    assert body == "loopback host required\n"


def test_handler_allows_non_loopback_host_when_explicit(tmp_path: Path) -> None:
    path = tmp_path / "desk.json"
    path.write_text(json.dumps({"pet_state": "sleeping", "counts": {}}), encoding="utf-8")
    handler = browser_server.make_handler(
        browser_server.FileViewModelSource(path),
        refresh_seconds=5,
        allow_non_loopback=True,
    )
    server = browser_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/", headers={"Host": "example.com"})
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert response.status == 200
    assert '<main data-state="sleeping">' in body
