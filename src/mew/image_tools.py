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
DEFAULT_IMAGES_MAX_COUNT = 16
DEFAULT_IMAGES_MAX_TOTAL_BYTES = 24 * 1024 * 1024
DEFAULT_IMAGES_MAX_OUTPUT_CHARS = 12_000
DEFAULT_IMAGE_DETAIL = "high"
DEFAULT_IMAGE_PROMPT = (
    "Inspect this image as a work-session observation. Transcribe all visible "
    "text and code exactly. If it is a screenshot, diagram, board, puzzle, or "
    "data visualization, describe the relevant coordinates, labels, objects, "
    "relationships, and uncertainties. For code screenshots, preserve "
    "indentation, operators, numbers, and string literals. Return concise "
    "plain text only."
)
DEFAULT_IMAGES_PROMPT = (
    "Inspect these images as one ordered work-session observation. Treat them "
    "as pages, frames, screenshots, or contact sheets in the order listed. "
    "Extract only task-relevant content, deduplicate repeated frames, preserve "
    "visible text exactly when possible, and mark uncertainties with the image "
    "index. Return concise plain text only."
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


def _normalize_image_paths(paths):
    if paths is None:
        return []
    if isinstance(paths, str):
        paths = [item.strip() for item in paths.split(",")]
    if not isinstance(paths, list):
        raise ValueError("read_images paths must be a list")
    normalized = []
    for item in paths:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def read_images_with_model(
    paths,
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
    max_total_bytes=DEFAULT_IMAGES_MAX_TOTAL_BYTES,
    max_images=DEFAULT_IMAGES_MAX_COUNT,
    max_output_chars=DEFAULT_IMAGES_MAX_OUTPUT_CHARS,
):
    if not model_auth:
        raise MewError("read_images requires model auth")
    image_paths = _normalize_image_paths(paths)
    if not image_paths:
        raise ValueError("read_images requires at least one path")
    max_images = max(1, min(int(max_images or DEFAULT_IMAGES_MAX_COUNT), DEFAULT_IMAGES_MAX_COUNT))
    if len(image_paths) > max_images:
        raise ValueError(
            f"read_images supports at most {max_images} images per call; "
            "split larger ordered sets into chunks"
        )

    image_detail = _image_detail(detail)
    max_bytes = max(1, int(max_bytes or DEFAULT_IMAGE_MAX_BYTES))
    max_total_bytes = max(1, int(max_total_bytes or DEFAULT_IMAGES_MAX_TOTAL_BYTES))
    total_bytes = 0
    images = []
    image_inputs = []
    for index, path in enumerate(image_paths, start=1):
        resolved = resolve_allowed_path(path, allowed_read_roots)
        ensure_not_sensitive(resolved, verb="read image")
        if not resolved.is_file():
            raise ValueError(f"path is not a file: {resolved}")
        try:
            size = resolved.stat().st_size
        except OSError:
            size = 0
        if size > max_bytes:
            raise ValueError(f"image is too large: {size} bytes > {max_bytes} bytes")
        total_bytes += size
        if total_bytes > max_total_bytes:
            raise ValueError(f"read_images payload is too large: {total_bytes} bytes > {max_total_bytes} bytes")
        mime_type = _image_mime_type(resolved)
        data_url = f"data:{mime_type};base64,{base64.b64encode(resolved.read_bytes()).decode('ascii')}"
        images.append(
            {
                "index": index,
                "path": str(resolved),
                "mime_type": mime_type,
                "size": size,
            }
        )
        image_inputs.append(
            {
                "image_url": data_url,
                "detail": image_detail,
            }
        )

    image_list = "\n".join(f"[{item['index']}] {item['path']}" for item in images)
    observation_prompt = str(prompt or DEFAULT_IMAGES_PROMPT).strip() or DEFAULT_IMAGES_PROMPT
    observation_prompt = f"{observation_prompt}\n\nOrdered image paths:\n{image_list}"
    text = str(
        call_model_text(
            model_backend,
            model_auth,
            observation_prompt,
            model,
            base_url,
            timeout,
            image_inputs=image_inputs,
        )
        or ""
    ).strip()
    max_output_chars = max(1, int(max_output_chars or DEFAULT_IMAGES_MAX_OUTPUT_CHARS))
    truncated = len(text) > max_output_chars
    if truncated:
        text = text[:max_output_chars]
    return {
        "paths": [item["path"] for item in images],
        "images": images,
        "type": "images",
        "count": len(images),
        "total_size": total_bytes,
        "detail": image_detail,
        "prompt": observation_prompt,
        "text": text,
        "truncated": truncated,
    }
