import json
import http.client
import os
from pathlib import Path
import socket
import ssl
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
import base64
import errno
import hashlib
import signal
import threading
from contextlib import contextmanager

from .config import DEFAULT_AUTH_PATHS, DEFAULT_CODEX_REASONING_EFFORT
from .errors import CodexApiError, CodexRefusalError, MewError

CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_REFRESH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR = "CODEX_REFRESH_TOKEN_URL_OVERRIDE"
CODEX_TOKEN_REFRESH_SKEW_SECONDS = 300
CODEX_RESPONSES_WEBSOCKET_BETA = "responses_websockets=2026-02-06"
CODEX_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class CodexTransientTransportError(CodexApiError):
    """Retryable provider transport failure before a terminal response event."""


def find_auth_path(auth_path=None):
    if auth_path:
        path = Path(auth_path).expanduser()
        if not path.exists():
            raise MewError(f"auth file not found: {path}")
        return path

    for path in DEFAULT_AUTH_PATHS:
        if path.exists():
            return path
    raise MewError("auth.json not found; expected ./auth.json or ~/.codex/auth.json")

def load_codex_oauth(auth_path=None):
    path = find_auth_path(auth_path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise MewError(f"failed to parse auth file: {path}") from exc

    auth = _auth_from_data(data, path)

    if not auth.get("access_token"):
        raise MewError(
            f"auth file does not contain a Codex OAuth access token: {path}"
        )

    return auth


def _auth_from_data(data, path):
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
    access_token = data.get("access") or tokens.get("access_token")
    refresh_token = data.get("refresh") or tokens.get("refresh_token")
    account_id = data.get("accountId") or tokens.get("account_id")
    expires = data.get("expires") if "expires" in data else _jwt_expiry_millis(access_token)
    return {
        "path": str(path),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "account_id": account_id,
        "expires": expires,
    }


def _jwt_expiry_millis(token):
    payload = _decode_jwt_payload(token)
    if not payload:
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    return int(exp * 1000)


def _decode_jwt_payload(token):
    if not isinstance(token, str):
        return None
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        data = json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _coerce_epoch_seconds(value):
    if value is None:
        return None
    try:
        epoch = float(value)
    except (TypeError, ValueError):
        return None
    if epoch > 10_000_000_000:
        epoch /= 1000
    return epoch


def _auth_expires_soon(auth, skew_seconds=CODEX_TOKEN_REFRESH_SKEW_SECONDS):
    expires = _coerce_epoch_seconds(auth.get("expires"))
    if expires is None:
        return False
    return expires <= time.time() + skew_seconds


def _refresh_endpoint():
    return os.environ.get(CODEX_REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR, CODEX_REFRESH_TOKEN_URL)


def maybe_refresh_codex_oauth(auth, timeout=30):
    if not _auth_expires_soon(auth):
        return auth
    return refresh_codex_oauth(auth, timeout=timeout)


def refresh_codex_oauth(auth, timeout=30):
    path_text = auth.get("path")
    refresh_token = auth.get("refresh_token")
    if not path_text or not refresh_token:
        raise CodexApiError("Codex OAuth token expired and no refresh token is available")

    path = Path(path_text).expanduser()
    current_data = _load_auth_json(path)
    current_auth = _auth_from_data(current_data, path)
    if (
        current_auth.get("access_token")
        and current_auth.get("access_token") != auth.get("access_token")
        and _account_ids_compatible(auth.get("account_id"), current_auth.get("account_id"))
    ):
        auth.update(current_auth)
        return auth

    body = {
        "client_id": CODEX_OAUTH_CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    request = urllib.request.Request(
        _refresh_endpoint(),
        data=urllib.parse.urlencode(body).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "mew-core-prototype/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        detail = body_text[:800].replace("\n", " ")
        raise CodexApiError(f"failed to refresh Codex OAuth token: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise CodexApiError(f"failed to refresh Codex OAuth token: {exc.reason}") from exc
    except (socket.timeout, TimeoutError) as exc:
        raise CodexApiError("failed to refresh Codex OAuth token: request timed out") from exc

    try:
        refresh_data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CodexApiError(f"failed to refresh Codex OAuth token: non-JSON response: {raw[:200]}") from exc
    if not isinstance(refresh_data, dict):
        raise CodexApiError("failed to refresh Codex OAuth token: invalid response")

    updated_data = _apply_refreshed_tokens(current_data, refresh_data)
    _save_auth_json(path, updated_data)
    refreshed = _auth_from_data(updated_data, path)
    if not refreshed.get("access_token"):
        raise CodexApiError("failed to refresh Codex OAuth token: missing access token")
    auth.update(refreshed)
    return auth


def _load_auth_json(path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise CodexApiError(f"auth file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CodexApiError(f"failed to parse auth file: {path}") from exc
    if not isinstance(data, dict):
        raise CodexApiError(f"auth file must contain a JSON object: {path}")
    return data


def _account_ids_compatible(expected, actual):
    return not expected or not actual or expected == actual


def _apply_refreshed_tokens(data, refresh_data):
    access_token = refresh_data.get("access_token")
    refresh_token = refresh_data.get("refresh_token")
    id_token = refresh_data.get("id_token")
    if not isinstance(access_token, str) or not access_token:
        raise CodexApiError("failed to refresh Codex OAuth token: response did not contain access_token")

    updated = dict(data)
    tokens = updated.get("tokens")
    if isinstance(tokens, dict):
        tokens = dict(tokens)
        if isinstance(id_token, str) and id_token:
            tokens["id_token"] = id_token
        if isinstance(access_token, str) and access_token:
            tokens["access_token"] = access_token
        if isinstance(refresh_token, str) and refresh_token:
            tokens["refresh_token"] = refresh_token
        updated["tokens"] = tokens
        updated["last_refresh"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return updated

    if isinstance(access_token, str) and access_token:
        updated["access"] = access_token
        expires = _jwt_expiry_millis(access_token)
        if expires is not None:
            updated["expires"] = expires
    if isinstance(refresh_token, str) and refresh_token:
        updated["refresh"] = refresh_token
    if isinstance(id_token, str) and id_token:
        updated["id"] = id_token
    return updated


def _save_auth_json(path, data):
    mode = None
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        pass
    secure_mode = (mode or 0o600) & 0o600 or 0o600
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    temp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, secure_mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(temp_path, secure_mode)
        os.replace(temp_path, path)
    except OSError as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        if exc.errno not in (errno.EBUSY, errno.EXDEV, errno.EPERM, errno.EACCES):
            raise
        with path.open("w", encoding="utf-8") as handle:
            handle.write(text)
        try:
            os.chmod(path, secure_mode)
        except OSError:
            pass

def codex_headers(auth):
    headers = {
        "Authorization": f"Bearer {auth['access_token']}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "mew-core-prototype/0.1",
    }
    if auth.get("account_id"):
        headers["chatgpt-account-id"] = auth["account_id"]
    return headers


def codex_websocket_headers(auth, *, conversation_id=""):
    headers = {
        "Authorization": f"Bearer {auth['access_token']}",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "mew-core-prototype/0.1",
        "OpenAI-Beta": CODEX_RESPONSES_WEBSOCKET_BETA,
    }
    if conversation_id:
        headers["x-client-request-id"] = str(conversation_id)
    if auth.get("account_id"):
        headers["chatgpt-account-id"] = auth["account_id"]
    return headers


class CodexResponsesWebSocketSession:
    """Small blocking Responses WebSocket client for Codex OAuth transport.

    Codex exposes ``previous_response_id`` on the Responses WebSocket transport,
    not on the current ChatGPT backend HTTP endpoint.  This session intentionally
    implements only the text-frame subset needed by implement_v2: send a
    ``response.create`` frame, stream JSON response events until a terminal
    response event, and keep the connection open for the next turn.
    """

    def __init__(self, *, auth, base_url, timeout, conversation_id=""):
        self.auth = auth
        self.base_url = str(base_url or "").rstrip("/")
        self.timeout = timeout
        self.conversation_id = str(conversation_id or "")
        self._socket = None
        self._connected_url = ""

    def close(self):
        sock = self._socket
        self._socket = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def request(self, body, *, timeout=None, on_text_delta=None):
        deadline = _request_deadline(timeout if timeout is not None else self.timeout)
        if _auth_expires_soon(self.auth):
            refresh_codex_oauth(self.auth, timeout=_refresh_timeout(deadline))
        try:
            self._ensure_connected(deadline)
        except _CodexUnauthorizedError as exc:
            try:
                refresh_codex_oauth(self.auth, timeout=_refresh_timeout(deadline))
            except CodexApiError as refresh_error:
                raise CodexApiError(f"HTTP {exc.code}: {exc.detail}") from refresh_error
            self.close()
            try:
                self._ensure_connected(deadline)
            except _CodexUnauthorizedError as retry_exc:
                raise CodexApiError(f"HTTP {retry_exc.code}: {retry_exc.detail}") from retry_exc

        request_body = dict(body)
        request_body.setdefault("stream", True)
        request_body = {"type": "response.create", **request_body}
        payload = json.dumps(request_body, ensure_ascii=False, separators=(",", ":"))
        try:
            self._send_text(payload, deadline)
        except (OSError, TimeoutError) as exc:
            self.close()
            raise CodexTransientTransportError(
                f"websocket send failed: {exc}"
            ) from exc

        events = []
        while True:
            try:
                event = self._recv_json_event(deadline)
            except CodexTransientTransportError:
                self.close()
                raise
            except (OSError, TimeoutError) as exc:
                self.close()
                raise CodexTransientTransportError(
                    f"websocket receive failed: {exc}"
                ) from exc
            if event is None:
                continue
            event_type = str(event.get("type") or "")
            if event_type == "error":
                raise CodexApiError(_websocket_error_detail(event))
            events.append(event)
            if on_text_delta and event_type == "response.output_text.delta":
                delta = event.get("delta")
                if isinstance(delta, str) and delta:
                    on_text_delta(delta)
            if event_type in {
                "response.completed",
                "response.failed",
                "response.incomplete",
            }:
                return tuple(events)

    def _ensure_connected(self, deadline):
        if self._socket is not None:
            return
        url = _responses_websocket_url(self.base_url)
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        if not host:
            raise CodexApiError(f"invalid websocket URL: {url}")
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        raw_sock = socket.create_connection(
            (host, port), timeout=_deadline_read_timeout(deadline) or self.timeout
        )
        try:
            raw_sock.settimeout(_deadline_read_timeout(deadline) or self.timeout)
            if parsed.scheme == "wss":
                context = ssl.create_default_context()
                sock = context.wrap_socket(raw_sock, server_hostname=host)
            else:
                sock = raw_sock
            sock.settimeout(_deadline_read_timeout(deadline) or self.timeout)
            self._handshake(sock, parsed, deadline)
        except Exception:
            try:
                raw_sock.close()
            except OSError:
                pass
            raise
        self._socket = sock
        self._connected_url = url

    def _handshake(self, sock, parsed, deadline):
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        host = parsed.hostname or ""
        port = parsed.port
        if port and not (
            (parsed.scheme == "wss" and port == 443)
            or (parsed.scheme == "ws" and port == 80)
        ):
            host = f"{host}:{port}"
        headers = {
            "Host": host,
            "Upgrade": "websocket",
            "Connection": "Upgrade",
            "Sec-WebSocket-Key": key,
            "Sec-WebSocket-Version": "13",
            **codex_websocket_headers(self.auth, conversation_id=self.conversation_id),
        }
        request = (
            f"GET {path} HTTP/1.1\r\n"
            + "".join(f"{name}: {value}\r\n" for name, value in headers.items())
            + "\r\n"
        )
        sock.sendall(request.encode("utf-8"))
        raw_headers, remainder = _read_http_response_headers(sock, deadline)
        status, response_headers = _parse_http_response_headers(raw_headers)
        if status == 401:
            detail = _read_http_error_body(sock, response_headers, remainder, deadline)
            raise _CodexUnauthorizedError(status, detail or "websocket unauthorized")
        if status != 101:
            detail = _read_http_error_body(sock, response_headers, remainder, deadline)
            raise CodexApiError(
                f"websocket handshake HTTP {status}: {detail[:800].replace(chr(10), ' ')}"
            )
        expected_accept = base64.b64encode(
            hashlib.sha1((key + CODEX_WEBSOCKET_GUID).encode("ascii")).digest()
        ).decode("ascii")
        actual_accept = response_headers.get("sec-websocket-accept", "")
        if actual_accept and actual_accept != expected_accept:
            raise CodexApiError("websocket handshake returned invalid accept key")

    def _send_text(self, text, deadline):
        sock = self._socket
        if sock is None:
            raise CodexApiError("websocket is not connected")
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        sock.settimeout(_deadline_read_timeout(deadline) or self.timeout)
        sock.sendall(bytes(header) + mask + masked)

    def _recv_json_event(self, deadline):
        opcode, payload = self._recv_frame(deadline)
        if opcode == 0x1:
            text = payload.decode("utf-8", errors="replace")
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                return None
            return event if isinstance(event, dict) else None
        if opcode == 0x8:
            self.close()
            raise CodexTransientTransportError("websocket closed before response.completed")
        if opcode == 0x9:
            self._send_control_frame(0xA, payload, deadline)
            return None
        if opcode == 0xA:
            return None
        if opcode == 0x2:
            raise CodexApiError("unexpected binary websocket event")
        return None

    def _recv_frame(self, deadline):
        sock = self._socket
        if sock is None:
            raise CodexApiError("websocket is not connected")
        fragments = []
        first_opcode = None
        while True:
            sock.settimeout(_deadline_read_timeout(deadline) or self.timeout)
            first_two = _recv_exact(sock, 2)
            b1, b2 = first_two[0], first_two[1]
            fin = bool(b1 & 0x80)
            opcode = b1 & 0x0F
            masked = bool(b2 & 0x80)
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack("!H", _recv_exact(sock, 2))[0]
            elif length == 127:
                length = struct.unpack("!Q", _recv_exact(sock, 8))[0]
            mask = _recv_exact(sock, 4) if masked else b""
            payload = _recv_exact(sock, length) if length else b""
            if masked:
                payload = bytes(
                    byte ^ mask[index % 4] for index, byte in enumerate(payload)
                )
            if opcode in {0x8, 0x9, 0xA}:
                return opcode, payload
            if opcode == 0x0:
                if first_opcode is None:
                    raise CodexApiError("websocket continuation without initial frame")
                fragments.append(payload)
            else:
                first_opcode = opcode
                fragments = [payload]
            if fin:
                return first_opcode or opcode, b"".join(fragments)

    def _send_control_frame(self, opcode, payload, deadline):
        sock = self._socket
        if sock is None:
            return
        payload = bytes(payload[:125])
        header = bytearray([0x80 | opcode, 0x80 | len(payload)])
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        sock.settimeout(_deadline_read_timeout(deadline) or self.timeout)
        sock.sendall(bytes(header) + mask + masked)


def _responses_websocket_url(base_url):
    url = str(base_url or "").rstrip("/") + "/responses"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "https":
        return urllib.parse.urlunparse(parsed._replace(scheme="wss"))
    if parsed.scheme == "http":
        return urllib.parse.urlunparse(parsed._replace(scheme="ws"))
    return url


def _read_http_response_headers(sock, deadline):
    chunks = []
    data = b""
    while b"\r\n\r\n" not in data:
        sock.settimeout(_deadline_read_timeout(deadline))
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        data = b"".join(chunks)
        if len(data) > 65536:
            raise CodexApiError("websocket handshake headers too large")
    header_bytes, _sep, remainder = data.partition(b"\r\n\r\n")
    return header_bytes.decode("iso-8859-1", errors="replace"), remainder


def _parse_http_response_headers(raw_headers):
    lines = raw_headers.split("\r\n")
    status_line = lines[0] if lines else ""
    try:
        status = int(status_line.split()[1])
    except (IndexError, ValueError):
        raise CodexApiError(f"invalid websocket handshake response: {status_line}")
    headers = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return status, headers


def _read_http_error_body(sock, headers, remainder, deadline):
    body = bytearray(remainder)
    try:
        content_length = int(headers.get("content-length") or 0)
    except ValueError:
        content_length = 0
    while content_length and len(body) < content_length:
        sock.settimeout(_deadline_read_timeout(deadline))
        chunk = sock.recv(content_length - len(body))
        if not chunk:
            break
        body.extend(chunk)
    return body.decode("utf-8", errors="replace")


def _recv_exact(sock, size):
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise CodexTransientTransportError("websocket closed while reading frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _websocket_error_detail(event):
    status = event.get("status") or event.get("status_code")
    error = event.get("error")
    message = ""
    code = ""
    if isinstance(error, dict):
        message = str(error.get("message") or "")
        code = str(error.get("code") or error.get("type") or "")
    return f"websocket error status={status or 'unknown'} code={code or 'unknown'}: {message or json.dumps(event, ensure_ascii=False)[:800]}"


class _CodexUnauthorizedError(Exception):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code
        self.detail = detail

def extract_response_text(data):
    if isinstance(data, dict):
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        chunks = []
        for item in data.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                text = content.get("text") or content.get("output_text")
                if isinstance(text, str):
                    chunks.append(text)
        if chunks:
            return "".join(chunks).strip()

        response = data.get("response")
        if isinstance(response, dict):
            return extract_response_text(response)

    return ""


def extract_response_refusal(data):
    if isinstance(data, dict):
        refusal = data.get("refusal")
        if isinstance(refusal, str) and refusal.strip():
            return refusal.strip()

        chunks = []
        for item in data.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            item_refusal = item.get("refusal")
            if isinstance(item_refusal, str) and item_refusal.strip():
                chunks.append(item_refusal)
            for content in item.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                text = content.get("refusal")
                if not isinstance(text, str):
                    content_type = str(content.get("type") or "").strip().casefold()
                    if content_type == "refusal":
                        text = content.get("text") or content.get("output_text")
                if isinstance(text, str):
                    chunks.append(text)
        if chunks:
            return "".join(chunks).strip()

        response = data.get("response")
        if isinstance(response, dict):
            return extract_response_refusal(response)

    return ""


def extract_sse_response_parts(raw_text):
    text_chunks = []
    refusal_chunks = []
    completed_response = None

    for line in raw_text.splitlines():
        data = decode_sse_data_line(line)
        if not data:
            continue

        event_type = data.get("type")
        if event_type == "response.output_text.delta":
            delta = data.get("delta")
            if isinstance(delta, str):
                text_chunks.append(delta)
        elif event_type == "response.refusal.delta":
            delta = data.get("delta")
            if isinstance(delta, str):
                refusal_chunks.append(delta)
        elif event_type == "response.completed":
            completed_response = data.get("response")
        elif "response" in data and isinstance(data["response"], dict):
            completed_response = data["response"]

    if completed_response:
        if not text_chunks:
            completed_text = extract_response_text(completed_response)
            if completed_text:
                text_chunks.append(completed_text)
        if not refusal_chunks:
            completed_refusal = extract_response_refusal(completed_response)
            if completed_refusal:
                refusal_chunks.append(completed_refusal)

    return {
        "text": "".join(text_chunks).strip(),
        "refusal": "".join(refusal_chunks).strip(),
    }

def extract_sse_text(raw_text):
    return extract_sse_response_parts(raw_text).get("text") or ""


def decode_sse_data_line(line):
    line = line.strip()
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def sse_text_delta(data):
    if not isinstance(data, dict):
        return ""
    if data.get("type") == "response.output_text.delta":
        delta = data.get("delta")
        return delta if isinstance(delta, str) else ""
    return ""


def _request_deadline(timeout):
    try:
        timeout_value = float(timeout)
    except (TypeError, ValueError):
        return None
    if timeout_value <= 0:
        return None
    return time.monotonic() + timeout_value


def _raise_if_request_timed_out(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise CodexApiError("request timed out")


def _deadline_read_timeout(deadline):
    if deadline is None:
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CodexApiError("request timed out")
    return max(0.01, remaining)


@contextmanager
def _hard_request_deadline(deadline):
    if deadline is None:
        yield
        return
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    if not hasattr(signal, "SIGALRM") or not hasattr(signal, "setitimer"):
        yield
        return
    try:
        previous_timer = signal.getitimer(signal.ITIMER_REAL)
    except (AttributeError, OSError, ValueError):
        yield
        return
    if previous_timer and previous_timer[0] > 0:
        yield
        return
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CodexApiError("request timed out")
    previous_handler = signal.getsignal(signal.SIGALRM)

    def timeout_handler(signum, frame):
        raise CodexApiError("request timed out")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, max(0.01, remaining))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _read_stream_body(response, deadline, on_text_delta=None):
    chunks = []
    while True:
        socket_timeout = _deadline_read_timeout(deadline)
        if socket_timeout is not None:
            _set_response_read_timeout(response, socket_timeout)
        try:
            raw_line = response.readline()
        except http.client.IncompleteRead as exc:
            partial = exc.partial or b""
            if partial:
                chunks.append(partial.decode("utf-8", errors="replace"))
                break
            raise
        except (socket.timeout, TimeoutError) as exc:
            raise CodexApiError("request timed out") from exc
        except OSError as exc:
            if "cannot read from timed out object" in str(exc).casefold():
                raise CodexApiError("request timed out") from exc
            raise
        if not raw_line:
            break
        _raise_if_request_timed_out(deadline)
        line = raw_line.decode("utf-8", errors="replace")
        chunks.append(line)
        if on_text_delta:
            delta = sse_text_delta(decode_sse_data_line(line))
            if delta:
                on_text_delta(delta)
    return "".join(chunks)


def _set_response_read_timeout(response, timeout):
    stream = getattr(response, "fp", None)
    visited = set()
    while stream is not None and id(stream) not in visited:
        visited.add(id(stream))
        sock = getattr(stream, "_sock", None) or getattr(stream, "sock", None)
        if sock is not None and hasattr(sock, "settimeout"):
            sock.settimeout(timeout)
            return True
        stream = getattr(stream, "raw", None) or getattr(stream, "fp", None)
    return False


def _refresh_timeout(deadline):
    if deadline is None:
        return 30
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CodexApiError("request timed out")
    return max(0.01, min(30, remaining))


def _send_codex_responses_request(auth, url, body, timeout, deadline, on_text_delta=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=codex_headers(auth),
        method="POST",
    )
    try:
        with _hard_request_deadline(deadline):
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get("content-type", "")
                if on_text_delta or "text/event-stream" in content_type:
                    raw = _read_stream_body(response, deadline, on_text_delta=on_text_delta)
                else:
                    _raise_if_request_timed_out(deadline)
                    raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        detail = body_text[:800].replace("\n", " ")
        if exc.code == 401:
            raise _CodexUnauthorizedError(exc.code, detail) from exc
        raise CodexApiError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise CodexApiError(str(exc.reason)) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise CodexApiError("request timed out") from exc
    return raw, content_type


def call_codex_web_api(
    auth,
    prompt,
    model,
    base_url,
    timeout,
    on_text_delta=None,
    image_inputs=None,
):
    url = base_url.rstrip("/") + "/responses"
    reasoning_effort = os.environ.get("MEW_CODEX_REASONING_EFFORT", DEFAULT_CODEX_REASONING_EFFORT).strip()
    content = [
        {
            "type": "input_text",
            "text": prompt,
        }
    ]
    for image in image_inputs or []:
        if not isinstance(image, dict):
            continue
        image_item = {"type": "input_image"}
        image_url = image.get("image_url")
        file_id = image.get("file_id")
        if image_url:
            image_item["image_url"] = image_url
        elif file_id:
            image_item["file_id"] = file_id
        else:
            continue
        detail = str(image.get("detail") or "").strip()
        if detail:
            image_item["detail"] = detail
        content.append(image_item)
    body = {
        "model": model,
        "instructions": (
            "You are mew, a passive personal task-management agent. "
            "Use the provided local state only. Be concise. "
            "If the user writes Japanese, answer in Japanese."
        ),
        "input": [
            {
                "role": "user",
                "content": content,
            }
        ],
        "stream": True,
        "store": False,
    }
    if reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort}
    deadline = _request_deadline(timeout)

    try:
        if _auth_expires_soon(auth):
            refresh_codex_oauth(auth, timeout=_refresh_timeout(deadline))
        raw, content_type = _send_codex_responses_request(
            auth,
            url,
            body,
            timeout,
            deadline,
            on_text_delta=on_text_delta,
        )
    except _CodexUnauthorizedError as exc:
        try:
            refresh_codex_oauth(auth, timeout=_refresh_timeout(deadline))
        except CodexApiError as refresh_error:
            raise CodexApiError(f"HTTP {exc.code}: {exc.detail}") from refresh_error
        try:
            raw, content_type = _send_codex_responses_request(
                auth,
                url,
                body,
                timeout,
                deadline,
                on_text_delta=on_text_delta,
            )
        except _CodexUnauthorizedError as retry_exc:
            raise CodexApiError(f"HTTP {retry_exc.code}: {retry_exc.detail}") from retry_exc

    if "text/event-stream" in content_type or raw.lstrip().startswith(("event:", "data:")):
        response_parts = extract_sse_response_parts(raw)
        text = response_parts.get("text") or ""
        refusal = response_parts.get("refusal") or ""
    else:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CodexApiError(f"non-JSON response: {raw[:200]}") from exc
        text = extract_response_text(payload)
        refusal = extract_response_refusal(payload)

    if refusal:
        raise CodexRefusalError(f"model returned refusal: {refusal}")
    if not text:
        raise CodexApiError("response did not contain assistant text")
    return text


def call_codex_responses_raw(auth, body, base_url, timeout, on_text_delta=None):
    """Send an already-built Responses API body and return raw response bytes as text.

    This is the provider-native escape hatch used by implement_v2. It reuses the
    same OAuth refresh, timeout, SSE, and 401 retry behavior as
    ``call_codex_web_api`` without imposing the legacy text/JSON prompt wrapper.
    """

    url = base_url.rstrip("/") + "/responses"
    deadline = _request_deadline(timeout)
    try:
        if _auth_expires_soon(auth):
            refresh_codex_oauth(auth, timeout=_refresh_timeout(deadline))
        raw, content_type = _send_codex_responses_request(
            auth,
            url,
            body,
            timeout,
            deadline,
            on_text_delta=on_text_delta,
        )
    except _CodexUnauthorizedError as exc:
        try:
            refresh_codex_oauth(auth, timeout=_refresh_timeout(deadline))
        except CodexApiError as refresh_error:
            raise CodexApiError(f"HTTP {exc.code}: {exc.detail}") from refresh_error
        try:
            raw, content_type = _send_codex_responses_request(
                auth,
                url,
                body,
                timeout,
                deadline,
                on_text_delta=on_text_delta,
            )
        except _CodexUnauthorizedError as retry_exc:
            raise CodexApiError(f"HTTP {retry_exc.code}: {retry_exc.detail}") from retry_exc
    return raw, content_type


def extract_json_object(text):
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    start = 0 if stripped.startswith("{") else stripped.find("{")
    if start != -1:
        try:
            value, _end = decoder.raw_decode(stripped[start:])
        except json.JSONDecodeError as exc:
            raise CodexApiError("response did not contain valid JSON object") from exc
        return value

    raise CodexApiError("response did not contain JSON")

def call_codex_json(auth, prompt, model, base_url, timeout, on_text_delta=None):
    text = call_codex_web_api(auth, prompt, model, base_url, timeout, on_text_delta=on_text_delta)
    try:
        return extract_json_object(text)
    except (json.JSONDecodeError, CodexApiError) as exc:
        raise CodexApiError(f"failed to parse JSON plan: {exc}; raw={text[:500]}") from exc
