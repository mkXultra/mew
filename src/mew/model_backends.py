from typing import Protocol

from .anthropic_api import call_anthropic_json, load_anthropic_auth
from .codex_api import call_codex_json, load_codex_oauth
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

    def call_json(self, auth, prompt, model, base_url, timeout):
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

    def call_json(self, auth, prompt, model, base_url, timeout):
        return call_codex_json(
            auth,
            prompt,
            model or self.default_model,
            base_url or self.default_base_url,
            timeout,
        )


class ClaudeModelBackend:
    name = "claude"
    aliases = ("anthropic",)
    label = "Claude Messages API"
    default_model = "claude-sonnet-4-5"
    default_base_url = DEFAULT_ANTHROPIC_BASE_URL

    def load_auth(self, auth_path=None):
        return load_anthropic_auth(auth_path)

    def call_json(self, auth, prompt, model, base_url, timeout):
        return call_anthropic_json(
            auth,
            prompt,
            model or self.default_model,
            base_url or self.default_base_url,
            timeout,
        )


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


def call_model_json(backend, auth, prompt, model, base_url, timeout):
    try:
        return get_model_backend(backend).call_json(auth, prompt, model, base_url, timeout)
    except ModelBackendError:
        raise
    except MewError:
        raise
    except Exception as exc:
        raise ModelBackendError(f"{model_backend_label(backend)} error: {exc}") from exc
