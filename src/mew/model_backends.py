from typing import Protocol

from .anthropic_api import call_anthropic_json, load_anthropic_auth
from .codex_api import call_codex_json, call_codex_web_api, load_codex_oauth
from .config import (
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_WEB_BASE_URL,
    DEFAULT_MODEL_BACKEND,
)
from .errors import ModelBackendError, MewError


class ModelBackend(Protocol):
    name: str
    aliases: tuple
    label: str
    default_model: str
    default_base_url: str

    def load_auth(self, auth_path=None):
        pass

    def call_json(self, auth, prompt, model, base_url, timeout, on_text_delta=None):
        pass

    def call_text(self, auth, prompt, model, base_url, timeout, on_text_delta=None, image_inputs=None):
        pass


_BACKENDS = {}
_CANONICAL_NAMES = []


def register_model_backend(backend):
    name = backend.name.strip().casefold()
    if not name:
        raise ValueError("model backend name is empty")
    if name not in _CANONICAL_NAMES:
        _CANONICAL_NAMES.append(name)
    for alias in (name, *getattr(backend, "aliases", ())):
        normalized = str(alias).strip().casefold()
        if normalized:
            _BACKENDS[normalized] = backend
    return backend


def supported_model_backends():
    return tuple(_CANONICAL_NAMES)


class CodexModelBackend:
    name = "codex"
    aliases = ("codex-web", "codex_web")
    label = "Codex Web API"
    default_model = DEFAULT_CODEX_MODEL
    default_base_url = DEFAULT_CODEX_WEB_BASE_URL

    def load_auth(self, auth_path=None):
        return load_codex_oauth(auth_path)

    def call_json(self, auth, prompt, model, base_url, timeout, on_text_delta=None):
        args = (auth, prompt, model or self.default_model, base_url or self.default_base_url, timeout)
        if on_text_delta:
            return call_codex_json(*args, on_text_delta=on_text_delta)
        return call_codex_json(*args)

    def call_text(self, auth, prompt, model, base_url, timeout, on_text_delta=None, image_inputs=None):
        args = (auth, prompt, model or self.default_model, base_url or self.default_base_url, timeout)
        kwargs = {}
        if on_text_delta:
            kwargs["on_text_delta"] = on_text_delta
        if image_inputs:
            kwargs["image_inputs"] = image_inputs
        return call_codex_web_api(*args, **kwargs)


class ClaudeModelBackend:
    name = "claude"
    aliases = ("anthropic",)
    label = "Claude Messages API"
    default_model = "claude-sonnet-4-5"
    default_base_url = DEFAULT_ANTHROPIC_BASE_URL

    def load_auth(self, auth_path=None):
        return load_anthropic_auth(auth_path)

    def call_json(self, auth, prompt, model, base_url, timeout, on_text_delta=None):
        args = (auth, prompt, model or self.default_model, base_url or self.default_base_url, timeout)
        if on_text_delta:
            return call_anthropic_json(*args, on_text_delta=on_text_delta)
        return call_anthropic_json(*args)

    def call_text(self, auth, prompt, model, base_url, timeout, on_text_delta=None, image_inputs=None):
        if image_inputs:
            raise MewError("image inputs are currently supported only for the Codex backend")
        payload = self.call_json(auth, prompt, model, base_url, timeout, on_text_delta=on_text_delta)
        if isinstance(payload, dict):
            for key in ("text", "summary", "message"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return str(payload)


register_model_backend(CodexModelBackend())
register_model_backend(ClaudeModelBackend())

SUPPORTED_MODEL_BACKENDS = supported_model_backends()


def get_model_backend(backend):
    value = (backend or DEFAULT_MODEL_BACKEND).strip().casefold()
    try:
        return _BACKENDS[value]
    except KeyError as exc:
        supported = ", ".join(supported_model_backends())
        raise MewError(f"unsupported model backend: {backend}; supported={supported}") from exc


def normalize_model_backend(backend):
    return get_model_backend(backend).name


def model_backend_label(backend):
    return get_model_backend(backend).label


def model_backend_default_model(backend):
    return get_model_backend(backend).default_model


def model_backend_default_base_url(backend):
    return get_model_backend(backend).default_base_url


def load_model_auth(backend, auth_path=None):
    return get_model_backend(backend).load_auth(auth_path)


def call_model_json(backend, auth, prompt, model, base_url, timeout, on_text_delta=None):
    try:
        model_backend = get_model_backend(backend)
        if on_text_delta:
            return model_backend.call_json(auth, prompt, model, base_url, timeout, on_text_delta=on_text_delta)
        return model_backend.call_json(auth, prompt, model, base_url, timeout)
    except ModelBackendError:
        raise
    except MewError:
        raise
    except Exception as exc:
        raise ModelBackendError(f"{model_backend_label(backend)} error: {exc}") from exc


def call_model_text(
    backend,
    auth,
    prompt,
    model,
    base_url,
    timeout,
    on_text_delta=None,
    image_inputs=None,
):
    try:
        model_backend = get_model_backend(backend)
        return model_backend.call_text(
            auth,
            prompt,
            model,
            base_url,
            timeout,
            on_text_delta=on_text_delta,
            image_inputs=image_inputs,
        )
    except ModelBackendError:
        raise
    except MewError:
        raise
    except Exception as exc:
        raise ModelBackendError(f"{model_backend_label(backend)} error: {exc}") from exc
