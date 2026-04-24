"""Read-only parser for the M6.11 calibration ledger JSONL artifact."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

DEFAULT_LEDGER_PATH = Path("proof-artifacts/m6_11_calibration_ledger.jsonl")


@dataclass(frozen=True)
class CalibrationLedgerRow:
    """One parsed calibration-ledger JSONL row.

    The closeout ledger is treated as evidence: this module only reads and
    normalizes row access. It deliberately does not mutate proof artifacts.
    """

    line_number: int
    data: Mapping[str, Any]

    @property
    def row_ref(self) -> str:
        for key in ("row_ref", "row", "id", "case_id"):
            value = self.data.get(key)
            if value not in (None, ""):
                return str(value)
        return str(self.line_number)

    def field(self, name: str, default: Any = None) -> Any:
        """Return a field from top-level data or common nested payloads."""

        if name in self.data:
            return self.data[name]
        for container_name in ("derived", "classification", "review", "failure", "metadata"):
            container = self.data.get(container_name)
            if isinstance(container, Mapping) and name in container:
                return container[name]
        return default

    def text_field(self, name: str) -> str:
        value = self.field(name, "")
        if value is None:
            return ""
        return str(value)


def iter_calibration_ledger(path: str | Path = DEFAULT_LEDGER_PATH) -> Iterator[CalibrationLedgerRow]:
    """Yield parsed non-empty JSONL rows from *path*.

    Raises ValueError with line context when a row is not a JSON object.
    """

    ledger_path = Path(path)
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:  # pragma: no cover - exact msg from json
                raise ValueError(f"invalid JSON on {ledger_path}:{line_number}: {exc.msg}") from exc
            if not isinstance(payload, Mapping):
                raise ValueError(f"expected object on {ledger_path}:{line_number}")
            yield CalibrationLedgerRow(line_number=line_number, data=payload)


def load_calibration_ledger(path: str | Path = DEFAULT_LEDGER_PATH) -> list[CalibrationLedgerRow]:
    """Return all parsed calibration-ledger rows from *path*."""

    return list(iter_calibration_ledger(path))


def coerce_calibration_rows(rows: Iterable[CalibrationLedgerRow | Mapping[str, Any]]) -> list[CalibrationLedgerRow]:
    """Coerce fixture dictionaries into row objects for classifier tests."""

    coerced: list[CalibrationLedgerRow] = []
    for index, row in enumerate(rows, start=1):
        if isinstance(row, CalibrationLedgerRow):
            coerced.append(row)
        elif isinstance(row, Mapping):
            coerced.append(CalibrationLedgerRow(line_number=index, data=row))
        else:
            raise TypeError(f"unsupported calibration row type: {type(row)!r}")
    return coerced
