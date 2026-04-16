import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from .codex_api import extract_json_object
from .config import DEFAULT_ANTHROPIC_BASE_URL
from .errors import AnthropicApiError, MewError, ModelBackendError


ANTHROPIC_VERSION = "2023-06-01"


def load_anthropic_auth(auth_path=None):
    if auth_path:
        path = Path(auth_path).expanduser()
        if not path.exists():
            raise MewError(f"Anthropic auth file not found: {path}")
        text = path.read_text(encoding="utf-8").strip()
        api_key = ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            api_key = text
        else:
            api_key = (
                data.get("api_key")
                or data.get("key")
                or data.get("ANTHROPIC_API_KEY")
                or data.get("anthropic_api_key")
                or ""
            )
        if not api_key:
            raise MewError(f"Anthropic auth file does not contain an API key: {path}")
        return {"path": str(path), "api_key": api_key}

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise MewError("ANTHROPIC_API_KEY is not set; pass --auth PATH for claude backend")
    return {"path": "$ANTHROPIC_API_KEY", "api_key": api_key}


def anthropic_headers(auth):
    return {
        "x-api-key": auth["api_key"],
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
        "User-Agent": "mew-core-prototype/0.1",
    }


def extract_anthropic_text(data):
    chunks = []
    if not isinstance(data, dict):
        return ""
    for item in data.get("content", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            chunks.append(item["text"])
    return "".join(chunks).strip()


def call_anthropic_messages_api(auth, prompt, model, base_url, timeout):
    url = (base_url or DEFAULT_ANTHROPIC_BASE_URL).rstrip("/") + "/messages"
    body = {
        "model": model,
        "max_tokens": 4096,
        "system": (
            "You are mew, a passive personal task-management agent. "
            "Return only the JSON object requested by the user prompt."
        ),
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=anthropic_headers(auth),
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        detail = body_text[:800].replace("\n", " ")
        raise AnthropicApiError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AnthropicApiError(str(exc.reason)) from exc
    except TimeoutError as exc:
        raise AnthropicApiError("request timed out") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AnthropicApiError(f"non-JSON response: {raw[:200]}") from exc

    text = extract_anthropic_text(data)
    if not text:
        raise AnthropicApiError("response did not contain assistant text")
    return text


def call_anthropic_json(auth, prompt, model, base_url, timeout, on_text_delta=None):
    text = call_anthropic_messages_api(auth, prompt, model, base_url, timeout)
    try:
        return extract_json_object(text)
    except (json.JSONDecodeError, ModelBackendError) as exc:
        raise AnthropicApiError(f"failed to parse JSON plan: {exc}; raw={text[:500]}") from exc
