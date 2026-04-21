import json
import os
from pathlib import Path
import socket
import time
import urllib.error
import urllib.request

from .config import DEFAULT_AUTH_PATHS, DEFAULT_CODEX_REASONING_EFFORT
from .errors import CodexApiError, CodexRefusalError, MewError


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

    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
    access_token = data.get("access") or tokens.get("access_token")
    account_id = data.get("accountId") or tokens.get("account_id")
    expires = data.get("expires")

    if not access_token:
        raise MewError(
            f"auth file does not contain a Codex OAuth access token: {path}"
        )

    return {
        "path": str(path),
        "access_token": access_token,
        "account_id": account_id,
        "expires": expires,
    }

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


def _socket_read_timeout(timeout):
    try:
        timeout_value = float(timeout)
    except (TypeError, ValueError):
        return 5.0
    if timeout_value <= 0:
        return 5.0
    return max(0.01, min(timeout_value, 5.0))


def _read_stream_body(response, deadline, on_text_delta=None):
    chunks = []
    while True:
        _raise_if_request_timed_out(deadline)
        try:
            raw_line = response.readline()
        except socket.timeout:
            _raise_if_request_timed_out(deadline)
            continue
        except TimeoutError:
            _raise_if_request_timed_out(deadline)
            continue
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


def call_codex_web_api(auth, prompt, model, base_url, timeout, on_text_delta=None):
    url = base_url.rstrip("/") + "/responses"
    reasoning_effort = os.environ.get("MEW_CODEX_REASONING_EFFORT", DEFAULT_CODEX_REASONING_EFFORT).strip()
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
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            }
        ],
        "stream": True,
        "store": False,
    }
    if reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort}
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=codex_headers(auth),
        method="POST",
    )
    deadline = _request_deadline(timeout)
    socket_timeout = _socket_read_timeout(timeout)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "")
            if on_text_delta or "text/event-stream" in content_type:
                _set_response_read_timeout(response, socket_timeout)
                raw = _read_stream_body(response, deadline, on_text_delta=on_text_delta)
            else:
                _raise_if_request_timed_out(deadline)
                raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        detail = body_text[:800].replace("\n", " ")
        raise CodexApiError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise CodexApiError(str(exc.reason)) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise CodexApiError("request timed out") from exc

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

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise CodexApiError("response did not contain JSON")

    return json.loads(stripped[start : end + 1])

def call_codex_json(auth, prompt, model, base_url, timeout, on_text_delta=None):
    text = call_codex_web_api(auth, prompt, model, base_url, timeout, on_text_delta=on_text_delta)
    try:
        return extract_json_object(text)
    except (json.JSONDecodeError, CodexApiError) as exc:
        raise CodexApiError(f"failed to parse JSON plan: {exc}; raw={text[:500]}") from exc
