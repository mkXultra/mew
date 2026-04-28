import base64
import mimetypes
from pathlib import Path

from .errors import MewError
from .model_backends import call_model_text
from .read_tools import ensure_not_sensitive, resolve_allowed_path


SUPPORTED_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
DEFAULT_IMAGE_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_IMAGE_DETAIL = "high"
DEFAULT_IMAGE_PROMPT = (
    "Inspect this image as a work-session observation. Transcribe all visible "
    "text and code exactly. If it is a screenshot, diagram, board, puzzle, or "
    "data visualization, describe the relevant coordinates, labels, objects, "
    "relationships, and uncertainties. For code screenshots, preserve "
    "indentation, operators, numbers, and string literals. Return concise "
    "plain text only."
)


def _image_mime_type(path):
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type == "image/jpg":
        mime_type = "image/jpeg"
    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        suffix = Path(path).suffix.lower()
        if suffix == ".png":
            mime_type = "image/png"
        elif suffix in {".jpg", ".jpeg"}:
            mime_type = "image/jpeg"
        elif suffix == ".webp":
            mime_type = "image/webp"
        elif suffix == ".gif":
            mime_type = "image/gif"
    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        supported = ", ".join(sorted(SUPPORTED_IMAGE_MIME_TYPES))
        raise ValueError(f"unsupported image type for {path}; supported={supported}")
    return mime_type


def _image_detail(value):
    detail = str(value or DEFAULT_IMAGE_DETAIL).strip().lower()
    if detail not in {"low", "high", "auto"}:
        raise ValueError("image detail must be one of: low, high, auto")
    return detail


def read_image_with_model(
    path,
    allowed_read_roots,
    *,
    model_backend,
    model_auth,
    model,
    base_url,
    timeout,
    prompt=None,
    detail=None,
    max_bytes=DEFAULT_IMAGE_MAX_BYTES,
):
    if not model_auth:
        raise MewError("read_image requires model auth")
    resolved = resolve_allowed_path(path, allowed_read_roots)
    ensure_not_sensitive(resolved, verb="read image")
    if not resolved.is_file():
        raise ValueError(f"path is not a file: {resolved}")
    try:
        size = resolved.stat().st_size
    except OSError:
        size = 0
    max_bytes = max(1, int(max_bytes or DEFAULT_IMAGE_MAX_BYTES))
    if size > max_bytes:
        raise ValueError(f"image is too large: {size} bytes > {max_bytes} bytes")

    mime_type = _image_mime_type(resolved)
    image_detail = _image_detail(detail)
    data = resolved.read_bytes()
    data_url = f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
    observation_prompt = str(prompt or DEFAULT_IMAGE_PROMPT).strip() or DEFAULT_IMAGE_PROMPT
    text = call_model_text(
        model_backend,
        model_auth,
        observation_prompt,
        model,
        base_url,
        timeout,
        image_inputs=[
            {
                "image_url": data_url,
                "detail": image_detail,
            }
        ],
    )
    return {
        "path": str(resolved),
        "type": "image",
        "mime_type": mime_type,
        "size": size,
        "detail": image_detail,
        "prompt": observation_prompt,
        "text": str(text or "").strip(),
    }
