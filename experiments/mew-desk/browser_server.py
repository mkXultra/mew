from __future__ import annotations

import argparse
import ipaddress
import json
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from browser_pet import load_view_model, render_browser_pet  # noqa: E402


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_REFRESH_SECONDS = 10
DEFAULT_COMMAND_TIMEOUT = 10.0
LOOPBACK_HOSTNAMES = {"localhost"}


class ViewModelSource(Protocol):
    def load(self) -> dict[str, Any]:
        pass


class FileViewModelSource:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        return load_view_model(self.path)


class CommandViewModelSource:
    def __init__(self, command: list[str], timeout: float = DEFAULT_COMMAND_TIMEOUT) -> None:
        self.command = command
        self.timeout = timeout

    def load(self) -> dict[str, Any]:
        completed = subprocess.run(
            self.command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            raise RuntimeError(f"source command exited {completed.returncode}: {stderr}")
        data = json.loads(completed.stdout)
        if not isinstance(data, dict):
            raise ValueError("source command must print a JSON object")
        return data


def render_live_page(view_model: dict[str, Any], refresh_seconds: int) -> str:
    if refresh_seconds <= 0:
        return render_browser_pet(view_model)
    return render_browser_pet(view_model, refresh_seconds=refresh_seconds)


def split_host_header(value: str) -> str:
    host = value.strip()
    if not host:
        return ""
    if host.startswith("["):
        end = host.find("]")
        if end != -1:
            return host[1:end].casefold()
    if host.count(":") == 1:
        host = host.rsplit(":", 1)[0]
    return host.casefold()


def is_loopback_host(value: str) -> bool:
    host = split_host_header(value)
    if host in LOOPBACK_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_bind_host(host: str, allow_non_loopback: bool) -> None:
    if allow_non_loopback or is_loopback_host(host):
        return
    raise ValueError("browser server host must be loopback unless --allow-non-loopback is set")


def write_response(handler: BaseHTTPRequestHandler, status: HTTPStatus, content_type: str, body: str) -> None:
    encoded = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(encoded)


def make_handler(
    source: ViewModelSource,
    refresh_seconds: int,
    *,
    allow_non_loopback: bool = False,
) -> type[BaseHTTPRequestHandler]:
    class MewDeskHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path not in {"/", "/index.html", "/view-model"}:
                write_response(self, HTTPStatus.NOT_FOUND, "text/plain", "not found\n")
                return
            if not allow_non_loopback and not is_loopback_host(self.headers.get("Host", "")):
                write_response(self, HTTPStatus.FORBIDDEN, "text/plain", "loopback host required\n")
                return
            try:
                view_model = source.load()
            except Exception as exc:  # pragma: no cover - exercised through response contract
                write_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain", f"{type(exc).__name__}: {exc}\n")
                return
            if path in {"/", "/index.html"}:
                write_response(self, HTTPStatus.OK, "text/html", render_live_page(view_model, refresh_seconds))
                return
            if path == "/view-model":
                write_response(self, HTTPStatus.OK, "application/json", json.dumps(view_model, ensure_ascii=False) + "\n")
                return

    return MewDeskHandler


def run_server(
    source: ViewModelSource,
    host: str,
    port: int,
    refresh_seconds: int,
    *,
    allow_non_loopback: bool = False,
) -> None:
    server = ThreadingHTTPServer(
        (host, port),
        make_handler(source, refresh_seconds, allow_non_loopback=allow_non_loopback),
    )
    url = f"http://{host}:{server.server_port}/"
    print(url, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_source(args: argparse.Namespace) -> ViewModelSource:
    if args.source_command:
        return CommandViewModelSource(args.source_command, timeout=args.command_timeout)
    if args.view_model:
        return FileViewModelSource(args.view_model)
    raise ValueError("provide a view_model path or --source-command")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve a live mew desk browser shell")
    parser.add_argument("view_model", nargs="?", type=Path, help="path to a mew desk JSON view model")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--refresh-seconds", type=int, default=DEFAULT_REFRESH_SECONDS)
    parser.add_argument("--command-timeout", type=float, default=DEFAULT_COMMAND_TIMEOUT)
    parser.add_argument(
        "--allow-non-loopback",
        action="store_true",
        help="allow binding beyond localhost; this may expose private mew state",
    )
    parser.add_argument(
        "--source-command",
        nargs=argparse.REMAINDER,
        help="command that prints a mew desk JSON object; put this option last",
    )
    args = parser.parse_args(argv)

    try:
        source = build_source(args)
        validate_bind_host(args.host, args.allow_non_loopback)
    except ValueError as exc:
        parser.error(str(exc))
    run_server(source, args.host, args.port, args.refresh_seconds, allow_non_loopback=args.allow_non_loopback)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
