from .codex_api import call_codex_json, load_codex_oauth
from .config import DEFAULT_MODEL_BACKEND
from .errors import CodexApiError, MewError


SUPPORTED_MODEL_BACKENDS = ("codex",)


def normalize_model_backend(backend):
    value = (backend or DEFAULT_MODEL_BACKEND).strip().casefold()
    if value in ("codex", "codex-web", "codex_web"):
        return "codex"
    raise MewError(f"unsupported model backend: {backend}")


def model_backend_label(backend):
    value = normalize_model_backend(backend)
    if value == "codex":
        return "Codex Web API"
    return value


def load_model_auth(backend, auth_path=None):
    value = normalize_model_backend(backend)
    if value == "codex":
        return load_codex_oauth(auth_path)
    raise MewError(f"unsupported model backend: {backend}")


def call_model_json(backend, auth, prompt, model, base_url, timeout):
    value = normalize_model_backend(backend)
    if value == "codex":
        return call_codex_json(auth, prompt, model, base_url, timeout)
    raise CodexApiError(f"unsupported model backend: {backend}")
