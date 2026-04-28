from __future__ import annotations

import math
import re

from .read_tools import ensure_not_sensitive, resolve_allowed_path
from .tasks import clip_output


DEFAULT_ANALYZE_TABLE_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_ANALYZE_TABLE_MAX_ROWS = 20000
DEFAULT_ANALYZE_TABLE_MAX_EXTREMA = 8
_NUMBER_RE = re.compile(r"[-+]?(?:\d+[.,]\d+|\d+)(?:[eE][-+]?\d+)?")


def _parse_numeric_line(line: str, *, delimiter: str = "") -> list[float]:
    if delimiter == "tab" or "\t" in line:
        raw_parts = line.split("\t")
    elif delimiter == "semicolon" or ";" in line:
        raw_parts = line.split(";")
    elif delimiter == "comma":
        raw_parts = line.split(",")
    elif delimiter == "whitespace" or len(line.split()) > 1:
        raw_parts = line.split()
    elif line.count(",") > 1:
        raw_parts = line.split(",")
    else:
        raw_parts = [match.group(0) for match in _NUMBER_RE.finditer(line)]
    values: list[float] = []
    for raw in raw_parts:
        text = str(raw).strip().replace(",", ".")
        if not text:
            continue
        try:
            value = float(text)
        except ValueError:
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def _float_summary(values: list[float]) -> dict:
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "monotonic_increasing": False,
            "monotonic_decreasing": False,
            "monotonic_violations": None,
        }
    increasing_violations = sum(1 for prev, cur in zip(values, values[1:]) if cur < prev)
    decreasing_violations = sum(1 for prev, cur in zip(values, values[1:]) if cur > prev)
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "monotonic_increasing": increasing_violations == 0,
        "monotonic_decreasing": decreasing_violations == 0,
        "monotonic_violations": {
            "increasing": increasing_violations,
            "decreasing": decreasing_violations,
        },
    }


def _extremum(index: int, x: float, y: float) -> dict:
    return {"index": index, "x": x, "y": y}


def _pair_extrema(x_values: list[float], y_values: list[float], *, max_extrema: int) -> dict:
    maxima: list[dict] = []
    minima: list[dict] = []
    for index in range(1, min(len(x_values), len(y_values)) - 1):
        y_prev = y_values[index - 1]
        y = y_values[index]
        y_next = y_values[index + 1]
        if y >= y_prev and y >= y_next and (y > y_prev or y > y_next):
            maxima.append(_extremum(index, x_values[index], y))
        if y <= y_prev and y <= y_next and (y < y_prev or y < y_next):
            minima.append(_extremum(index, x_values[index], y))
    maxima.sort(key=lambda item: item["y"], reverse=True)
    minima.sort(key=lambda item: item["y"])
    if not y_values:
        return {
            "global_max": None,
            "global_min": None,
            "top_local_maxima": [],
            "top_local_minima": [],
        }
    max_index = max(range(len(y_values)), key=lambda idx: y_values[idx])
    min_index = min(range(len(y_values)), key=lambda idx: y_values[idx])
    return {
        "global_max": _extremum(max_index, x_values[max_index], y_values[max_index]),
        "global_min": _extremum(min_index, x_values[min_index], y_values[min_index]),
        "top_local_maxima": maxima[:max_extrema],
        "top_local_minima": minima[:max_extrema],
    }


def _guess_delimiter(sample_lines: list[str]) -> str:
    scores = {
        "tab": sum(line.count("\t") for line in sample_lines),
        "comma": sum(line.count(",") for line in sample_lines),
        "semicolon": sum(line.count(";") for line in sample_lines),
        "whitespace": sum(len(line.split()) - 1 for line in sample_lines if len(line.split()) > 1),
    }
    if scores["tab"] > 0:
        return "tab"
    if scores["semicolon"] > 0:
        return "semicolon"
    if scores["comma"] > 0 and any("." in line for line in sample_lines):
        return "comma"
    if scores["whitespace"] > 0:
        return "whitespace"
    if scores["comma"] > 0:
        return "comma"
    return "unknown"


def analyze_table(
    path,
    allowed_read_roots,
    *,
    max_bytes=DEFAULT_ANALYZE_TABLE_MAX_BYTES,
    max_rows=DEFAULT_ANALYZE_TABLE_MAX_ROWS,
    max_extrema=DEFAULT_ANALYZE_TABLE_MAX_EXTREMA,
):
    """Return deterministic numeric profile data for text tables.

    This is a read-only observation primitive. It deliberately avoids
    task-specific expectations; callers use the resulting ranges/extrema to
    choose better numeric validation and fitting strategies.
    """

    resolved = resolve_allowed_path(path, allowed_read_roots)
    ensure_not_sensitive(resolved, verb="analyze table")
    if not resolved.is_file():
        raise ValueError(f"path is not a file: {resolved}")
    max_bytes = max(1, int(max_bytes or DEFAULT_ANALYZE_TABLE_MAX_BYTES))
    size = resolved.stat().st_size
    if size > max_bytes:
        raise ValueError(f"table is too large: {size} bytes > {max_bytes} bytes")
    text = resolved.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    max_rows = max(1, int(max_rows or DEFAULT_ANALYZE_TABLE_MAX_ROWS))
    delimiter_guess = _guess_delimiter(lines[:20])
    parsed_rows: list[list[float]] = []
    skipped_lines = 0
    for line in lines:
        values = _parse_numeric_line(line, delimiter=delimiter_guess)
        if values:
            parsed_rows.append(values)
            if len(parsed_rows) >= max_rows:
                break
        elif line.strip():
            skipped_lines += 1
    column_count = max((len(row) for row in parsed_rows), default=0)
    columns = []
    for index in range(column_count):
        values = [row[index] for row in parsed_rows if len(row) > index]
        summary = _float_summary(values)
        summary["index"] = index
        columns.append(summary)
    pairs = []
    max_extrema = max(1, int(max_extrema or DEFAULT_ANALYZE_TABLE_MAX_EXTREMA))
    for y_index in range(1, min(column_count, 6)):
        x_values = [row[0] for row in parsed_rows if len(row) > y_index]
        y_values = [row[y_index] for row in parsed_rows if len(row) > y_index]
        if len(x_values) < 3 or len(y_values) < 3:
            continue
        pair = {
            "x_column": 0,
            "y_column": y_index,
            "count": len(y_values),
        }
        pair.update(_pair_extrema(x_values, y_values, max_extrema=max_extrema))
        pairs.append(pair)
    numeric_cells = sum(len(row) for row in parsed_rows)
    return {
        "path": str(resolved),
        "type": "table_analysis",
        "size": size,
        "delimiter_guess": delimiter_guess,
        "total_lines": len(lines),
        "parsed_rows": len(parsed_rows),
        "truncated_rows": len(parsed_rows) >= max_rows and len(lines) > len(parsed_rows),
        "skipped_nonempty_lines": skipped_lines,
        "column_count": column_count,
        "numeric_cells": numeric_cells,
        "columns": columns,
        "pairs": pairs,
        "sample": clip_output("\n".join(lines[:5]), 600),
    }
