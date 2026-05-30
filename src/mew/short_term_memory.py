from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Optional


SHORT_TERM_MEMORY_KINDS = (
    "fact",
    "decision",
    "blocker",
    "constraint",
    "next_step",
    "warning",
)

DEFAULT_SHORT_TERM_MEMORY_MODEL = "gpt-5.5"
DEFAULT_SHORT_TERM_MEMORY_BACKEND = "codex"

ModelJsonCaller = Callable[[str, Mapping[str, Any], str, str, str, int], Any]


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _require_text(value: object, name: str) -> str:
    text = _clean_text(value)
    if not text:
        raise ValueError(f"{name} must not be empty")
    return text


def _stable_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _tokenize(value: str) -> tuple[str, ...]:
    cleaned = []
    for char in value.casefold():
        cleaned.append(char if char.isalnum() or char in {"_", "-", "/"} else " ")
    return tuple(token for token in "".join(cleaned).split() if token)


def _truncate(value: object, max_chars: int) -> str:
    text = _clean_text(value)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "..."


@dataclass(frozen=True)
class ShortTermMemoryCard:
    kind: str
    summary: str
    why_it_matters: str
    source_refs: tuple[str, ...]
    expires: str = "turns:5"
    confidence: float = 0.7
    created_turn: int = 0
    card_id: str = ""

    def __post_init__(self) -> None:
        kind = _clean_text(self.kind).casefold().replace("-", "_")
        if kind not in SHORT_TERM_MEMORY_KINDS:
            raise ValueError(f"kind must be one of: {', '.join(SHORT_TERM_MEMORY_KINDS)}")
        source_refs = tuple(_clean_text(ref) for ref in self.source_refs if _clean_text(ref))
        if not source_refs:
            raise ValueError("source_refs must not be empty")
        confidence = max(0.0, min(1.0, float(self.confidence)))
        created_turn = max(0, int(self.created_turn or 0))
        expires = _clean_text(self.expires) or "turns:5"
        card_id = _clean_text(self.card_id)
        if not card_id:
            card_id = "stm-" + _stable_hash(
                {
                    "kind": kind,
                    "summary": _clean_text(self.summary),
                    "source_refs": list(source_refs),
                    "created_turn": created_turn,
                    "expires": expires,
                }
            )[:16]
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "summary", _truncate(_require_text(self.summary, "summary"), 500))
        object.__setattr__(self, "why_it_matters", _truncate(_clean_text(self.why_it_matters), 300))
        object.__setattr__(self, "source_refs", source_refs)
        object.__setattr__(self, "expires", expires)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "created_turn", created_turn)
        object.__setattr__(self, "card_id", card_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "kind": self.kind,
            "summary": self.summary,
            "why_it_matters": self.why_it_matters,
            "source_refs": list(self.source_refs),
            "expires": self.expires,
            "confidence": self.confidence,
            "created_turn": self.created_turn,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ShortTermMemoryCard":
        return cls(
            card_id=str(data.get("card_id") or ""),
            kind=str(data.get("kind") or ""),
            summary=str(data.get("summary") or ""),
            why_it_matters=str(data.get("why_it_matters") or ""),
            source_refs=tuple(str(item) for item in data.get("source_refs") or ()),
            expires=str(data.get("expires") or "turns:5"),
            confidence=float(data.get("confidence", 0.7)),
            created_turn=int(data.get("created_turn", 0)),
        )

    def is_expired(self, *, current_turn: int) -> bool:
        expires = self.expires.casefold()
        if expires == "manual":
            return False
        if expires == "task_end":
            return False
        if expires.startswith("turns:"):
            try:
                ttl = int(expires.split(":", 1)[1])
            except ValueError:
                return False
            return current_turn > self.created_turn + max(0, ttl)
        return False

    def search_text(self) -> str:
        return " ".join((self.kind, self.summary, self.why_it_matters, " ".join(self.source_refs)))


@dataclass(frozen=True)
class ShortTermMemoryCompressionRequest:
    raw_text: str
    source_refs: tuple[str, ...]
    current_turn: int = 0
    max_cards: int = 5
    max_summary_chars: int = 220
    default_expires: str = "turns:5"

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_text", _require_text(self.raw_text, "raw_text"))
        source_refs = tuple(_clean_text(ref) for ref in self.source_refs if _clean_text(ref))
        if not source_refs:
            raise ValueError("source_refs must not be empty")
        object.__setattr__(self, "source_refs", source_refs)
        object.__setattr__(self, "current_turn", max(0, int(self.current_turn or 0)))
        object.__setattr__(self, "max_cards", max(1, int(self.max_cards or 1)))
        object.__setattr__(self, "max_summary_chars", max(80, int(self.max_summary_chars or 0)))
        object.__setattr__(self, "default_expires", _clean_text(self.default_expires) or "turns:5")


@dataclass(frozen=True)
class ShortTermMemoryCompressionResult:
    cards: tuple[ShortTermMemoryCard, ...]
    dropped: tuple[dict[str, str], ...]
    prompt_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cards": [card.to_dict() for card in self.cards],
            "dropped": list(self.dropped),
            "prompt_hash": self.prompt_hash,
        }


@dataclass(frozen=True)
class ShortTermMemoryRecallResult:
    cards: tuple[ShortTermMemoryCard, ...]
    dropped: dict[str, int]
    query_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "cards": [card.to_dict() for card in self.cards],
            "dropped": dict(self.dropped),
            "query_hash": self.query_hash,
        }


class ShortTermMemoryBuffer:
    def __init__(self, cards: Sequence[ShortTermMemoryCard] = ()) -> None:
        self._cards = list(cards)

    @property
    def cards(self) -> tuple[ShortTermMemoryCard, ...]:
        return tuple(self._cards)

    def add_cards(self, cards: Iterable[ShortTermMemoryCard]) -> None:
        existing = {card.card_id for card in self._cards}
        for card in cards:
            if card.card_id in existing:
                continue
            self._cards.append(card)
            existing.add(card.card_id)

    def recall(self, query: str, *, current_turn: int = 0, limit: int = 5) -> ShortTermMemoryRecallResult:
        query_terms = set(_tokenize(query))
        scored: list[tuple[float, ShortTermMemoryCard]] = []
        dropped: dict[str, int] = {}
        for card in self._cards:
            if card.is_expired(current_turn=current_turn):
                dropped["expired"] = dropped.get("expired", 0) + 1
                continue
            score = _short_term_card_score(card, query_terms, current_turn=current_turn)
            if query_terms and score <= 0:
                dropped["query_mismatch"] = dropped.get("query_mismatch", 0) + 1
                continue
            scored.append((score, card))
        scored.sort(key=lambda item: (item[0], item[1].confidence, item[1].created_turn), reverse=True)
        limit = max(0, int(limit or 0))
        return ShortTermMemoryRecallResult(
            cards=tuple(card for _, card in scored[:limit]),
            dropped=dropped,
            query_hash=_stable_hash({"query": query}),
        )


def compress_short_term_memory_with_model(
    request: ShortTermMemoryCompressionRequest,
    *,
    model_auth: Mapping[str, Any],
    model_backend: str = DEFAULT_SHORT_TERM_MEMORY_BACKEND,
    model: str = DEFAULT_SHORT_TERM_MEMORY_MODEL,
    base_url: str = "",
    timeout: int = 120,
    call_json: Optional[ModelJsonCaller] = None,
) -> ShortTermMemoryCompressionResult:
    if model_auth is None:
        raise ValueError("short-term memory compression requires model_auth")
    caller = call_json
    if caller is None:
        from .model_backends import call_model_json

        caller = call_model_json
    prompt = short_term_memory_compression_prompt(request)
    payload = caller(model_backend, model_auth, prompt, model, base_url, timeout)
    if not isinstance(payload, Mapping):
        raise ValueError("short-term memory compressor must return a JSON object")
    result = normalize_short_term_memory_payload(payload, request)
    return ShortTermMemoryCompressionResult(
        cards=result.cards,
        dropped=result.dropped,
        prompt_hash=_stable_hash({"prompt": prompt}),
    )


def short_term_memory_compression_prompt(request: ShortTermMemoryCompressionRequest) -> str:
    payload = {
        "task": "Compress recent agent/session evidence into short-term memory cards for the next few turns.",
        "schema": {
            "cards": [
                {
                    "kind": "fact | decision | blocker | constraint | next_step | warning",
                    "summary": "short memory text, no raw transcript",
                    "why_it_matters": "why this matters for the next few turns",
                    "source_refs": ["turn:12", "tool:abc", "file:path"],
                    "expires": "turns:5 | task_end | manual",
                    "confidence": 0.0,
                }
            ],
            "dropped": [
                {
                    "reason": "too_old | low_value | duplicated | raw_detail",
                    "summary": "brief note about omitted information",
                }
            ],
        },
        "rules": [
            "Return exactly one JSON object matching the schema.",
            "Create at most max_cards cards.",
            "Do not copy raw transcript; compress it.",
            "Do not include next actions as commands. A next_step card may record an already-decided next step only.",
            "Every card must cite at least one provided source_ref.",
            "Prefer facts, decisions, blockers, constraints, warnings, and immediately useful next-step state.",
        ],
        "limits": {
            "max_cards": request.max_cards,
            "max_summary_chars": request.max_summary_chars,
            "default_expires": request.default_expires,
        },
        "source_refs": list(request.source_refs),
        "raw_text": request.raw_text,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def normalize_short_term_memory_payload(
    payload: Mapping[str, Any],
    request: ShortTermMemoryCompressionRequest,
) -> ShortTermMemoryCompressionResult:
    raw_cards = payload.get("cards")
    if not isinstance(raw_cards, Sequence) or isinstance(raw_cards, (str, bytes)):
        raw_cards = ()
    cards: list[ShortTermMemoryCard] = []
    dropped: list[dict[str, str]] = []
    allowed_refs = set(request.source_refs)
    for raw in raw_cards:
        if not isinstance(raw, Mapping):
            dropped.append({"reason": "invalid_card", "summary": "card was not an object"})
            continue
        source_refs = tuple(str(ref) for ref in raw.get("source_refs") or ())
        source_refs = tuple(ref for ref in source_refs if ref in allowed_refs)
        if not source_refs:
            source_refs = (request.source_refs[0],)
        try:
            card = ShortTermMemoryCard(
                kind=str(raw.get("kind") or "fact"),
                summary=_truncate(raw.get("summary") or "", request.max_summary_chars),
                why_it_matters=_truncate(raw.get("why_it_matters") or "", 300),
                source_refs=source_refs,
                expires=str(raw.get("expires") or request.default_expires),
                confidence=float(raw.get("confidence", 0.7)),
                created_turn=request.current_turn,
            )
        except (TypeError, ValueError) as exc:
            dropped.append({"reason": "invalid_card", "summary": str(exc)})
            continue
        cards.append(card)
        if len(cards) >= request.max_cards:
            break
    raw_dropped = payload.get("dropped")
    if isinstance(raw_dropped, Sequence) and not isinstance(raw_dropped, (str, bytes)):
        for item in raw_dropped:
            if isinstance(item, Mapping):
                dropped.append(
                    {
                        "reason": _clean_text(item.get("reason") or "model_dropped"),
                        "summary": _truncate(item.get("summary") or "", 160),
                    }
                )
    return ShortTermMemoryCompressionResult(cards=tuple(cards), dropped=tuple(dropped))


def _short_term_card_score(card: ShortTermMemoryCard, query_terms: set[str], *, current_turn: int) -> float:
    if not query_terms:
        overlap = 1.0
    else:
        terms = set(_tokenize(card.search_text()))
        overlap = len(query_terms & terms) / max(1, len(query_terms))
    recency = 1.0 / (1.0 + max(0, current_turn - card.created_turn) * 0.05)
    return round(overlap * card.confidence * recency, 6)

