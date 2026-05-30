"""Done-candidate sidecar records for the native implement_v2 loop."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Iterable

from .native_transcript import NativeTranscript, NativeTranscriptItem, native_transcript_hash

DONE_CANDIDATE_SCHEMA_VERSION = 1
DONE_CANDIDATE_DETECTOR_VERSION = "done_candidate_detector_v1"
DONE_CANDIDATES_FILE = "done_candidates.jsonl"


@dataclass(frozen=True)
class NativeDoneCandidate:
    """A model final-response candidate recorded before internal finish-gate work."""

    done_candidate_id: str
    lane_attempt_id: str
    turn_id: str
    assistant_message_item_ids: tuple[str, ...]
    final_response_text_ref: str
    transcript_hash_before_gate: str
    compact_sidecar_digest_hash: str
    detector_version: str = DONE_CANDIDATE_DETECTOR_VERSION
    assistant_text_preview: str = ""
    reason: str = "assistant_message_without_tool_call"
    schema_version: int = field(default=DONE_CANDIDATE_SCHEMA_VERSION, init=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "done_candidate_id": self.done_candidate_id,
            "lane_attempt_id": self.lane_attempt_id,
            "turn_id": self.turn_id,
            "assistant_message_item_ids": list(self.assistant_message_item_ids),
            "final_response_text_ref": self.final_response_text_ref,
            "transcript_hash_before_gate": self.transcript_hash_before_gate,
            "compact_sidecar_digest_hash": self.compact_sidecar_digest_hash,
            "detector_version": self.detector_version,
            "assistant_text_preview": self.assistant_text_preview,
            "reason": self.reason,
        }


def build_native_done_candidate(
    transcript: NativeTranscript,
    turn_items: Iterable[NativeTranscriptItem],
    *,
    compact_sidecar_digest_hash: str,
    reason: str = "assistant_message_without_tool_call",
) -> NativeDoneCandidate | None:
    """Build a done-candidate row from a no-tool assistant turn."""

    assistant_items = tuple(
        item for item in turn_items if item.kind == "assistant_message" and item.output_text_or_ref.strip()
    )
    if not assistant_items:
        return None
    first = assistant_items[0]
    turn_id = first.turn_id or f"sequence-{first.sequence}"
    item_ids = tuple(
        str(item.provider_item_id or f"sequence-{item.sequence}") for item in assistant_items
    )
    transcript_hash = native_transcript_hash(transcript)
    candidate_seed = {
        "lane_attempt_id": transcript.lane_attempt_id,
        "turn_id": turn_id,
        "assistant_message_item_ids": list(item_ids),
        "transcript_hash_before_gate": transcript_hash,
    }
    digest = hashlib.sha256(
        json.dumps(candidate_seed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return NativeDoneCandidate(
        done_candidate_id=f"done-candidate:{turn_id}:{digest}",
        lane_attempt_id=transcript.lane_attempt_id,
        turn_id=turn_id,
        assistant_message_item_ids=item_ids,
        final_response_text_ref=(
            f"native-transcript://{transcript.lane_attempt_id}/{turn_id}/assistant-final-response"
        ),
        transcript_hash_before_gate=transcript_hash,
        compact_sidecar_digest_hash=compact_sidecar_digest_hash,
        assistant_text_preview=_preview(" ".join(item.output_text_or_ref for item in assistant_items)),
        reason=reason,
    )


def write_native_done_candidate_artifacts(
    root: Path | str,
    done_candidates: Iterable[NativeDoneCandidate],
    *,
    proof_manifest_path: str | Path | None = None,
) -> dict[str, Path]:
    records = [candidate.as_dict() for candidate in done_candidates]
    if not records:
        return {}
    artifact_root = Path(root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    path = artifact_root / DONE_CANDIDATES_FILE
    payload = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )
    path.write_text(payload, encoding="utf-8")
    digest = _file_sha256(path)
    if proof_manifest_path is not None:
        _patch_proof_manifest(
            Path(proof_manifest_path),
            done_candidates_path=path,
            digest=digest,
            count=len(records),
        )
    return {"done_candidates": path}


def _patch_proof_manifest(
    manifest_path: Path,
    *,
    done_candidates_path: Path,
    digest: str,
    count: int,
) -> None:
    manifest: dict[str, object] = {}
    if manifest_path.exists():
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            manifest = loaded
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    metrics = dict(metrics or {})
    metrics["done_candidate_count"] = count
    metrics["done_candidates"] = count
    manifest["done_candidates_ref"] = done_candidates_path.name
    manifest["done_candidates_sha256"] = digest
    manifest["metrics"] = metrics
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _preview(value: str, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


__all__ = [
    "DONE_CANDIDATE_DETECTOR_VERSION",
    "DONE_CANDIDATE_SCHEMA_VERSION",
    "DONE_CANDIDATES_FILE",
    "NativeDoneCandidate",
    "build_native_done_candidate",
    "write_native_done_candidate_artifacts",
]
