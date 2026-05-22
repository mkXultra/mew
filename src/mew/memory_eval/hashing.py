"""Canonical JSON hashing helpers for memory evaluation artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping, Set
from typing import Any


def normalize_json(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("non-finite floats are not canonical JSON")
        return value
    if isinstance(value, Mapping):
        return {str(key): normalize_json(value[key]) for key in sorted(value)}
    if isinstance(value, Set) and not isinstance(value, (str, bytes, bytearray)):
        normalized = [normalize_json(item) for item in value]
        return sorted(normalized, key=canonical_json)
    if isinstance(value, (list, tuple)):
        return [normalize_json(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        normalize_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def stable_hash(value: Any) -> str:
    payload = canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def without_keys(value: Any, blocked_keys: set[str]) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): without_keys(child, blocked_keys)
            for key, child in value.items()
            if str(key) not in blocked_keys
        }
    if isinstance(value, list):
        return [without_keys(item, blocked_keys) for item in value]
    if isinstance(value, tuple):
        return [without_keys(item, blocked_keys) for item in value]
    return value
