import json
from pathlib import Path
import urllib.error
import urllib.request

from .config import DEFAULT_AUTH_PATHS
from .errors import CodexApiError, MewError


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

def extract_sse_text(raw_text):
    chunks = []
    completed_response = None

    for line in raw_text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue

        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue

        event_type = data.get("type")
        if event_type in ("response.output_text.delta", "response.refusal.delta"):
            delta = data.get("delta")
            if isinstance(delta, str):
                chunks.append(delta)
        elif event_type == "response.completed":
            completed_response = data.get("response")
        elif "response" in data and isinstance(data["response"], dict):
            completed_response = data["response"]

    if chunks:
        return "".join(chunks).strip()
    if completed_response:
        return extract_response_text(completed_response)
    return ""

def call_codex_web_api(auth, prompt, model, base_url, timeout):
    url = base_url.rstrip("/") + "/responses"
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
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=codex_headers(auth),
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            content_type = response.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        detail = body_text[:800].replace("\n", " ")
        raise CodexApiError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise CodexApiError(str(exc.reason)) from exc
    except TimeoutError as exc:
        raise CodexApiError("request timed out") from exc

    if "text/event-stream" in content_type or raw.lstrip().startswith(("event:", "data:")):
        text = extract_sse_text(raw)
    else:
        try:
            text = extract_response_text(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise CodexApiError(f"non-JSON response: {raw[:200]}") from exc

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

def call_codex_json(auth, prompt, model, base_url, timeout):
    text = call_codex_web_api(auth, prompt, model, base_url, timeout)
    try:
        return extract_json_object(text)
    except (json.JSONDecodeError, CodexApiError) as exc:
        raise CodexApiError(f"failed to parse JSON plan: {exc}; raw={text[:500]}") from exc
