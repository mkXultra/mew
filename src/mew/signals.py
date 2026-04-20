from copy import deepcopy
from urllib.request import urlopen
from xml.etree import ElementTree

from .state import add_event, next_id
from .timeutil import now_iso


DEFAULT_SIGNAL_BUDGET_LIMIT = 5
MAX_SIGNAL_JOURNAL = 200


def ensure_signal_state(state):
    signals = state.setdefault("signals", {})
    signals.setdefault("sources", [])
    signals.setdefault("journal", [])
    return signals


def find_signal_source(state, name):
    target = (name or "").strip()
    if not target:
        return None
    for source in ensure_signal_state(state).get("sources", []):
        if source.get("name") == target:
            return source
    return None


def _today(current_time):
    return (current_time or now_iso()).split("T", 1)[0]


def _budget(limit, current_time):
    return {
        "window": "day",
        "window_key": _today(current_time),
        "limit": max(0, int(limit)),
        "used": 0,
    }


def _refresh_budget_window(source, current_time):
    budget = source.setdefault("budget", _budget(DEFAULT_SIGNAL_BUDGET_LIMIT, current_time))
    window_key = _today(current_time)
    if budget.get("window") != "day":
        budget["window"] = "day"
    if budget.get("window_key") != window_key:
        budget["window_key"] = window_key
        budget["used"] = 0
    budget["limit"] = max(0, int(budget.get("limit") or 0))
    budget["used"] = max(0, int(budget.get("used") or 0))
    return budget


def enable_signal_source(state, name, *, kind, reason, budget_limit=None, config=None, current_time=None):
    current_time = current_time or now_iso()
    name = (name or "").strip()
    kind = (kind or "").strip()
    if not name:
        raise ValueError("signal source name is required")
    if not kind:
        raise ValueError("signal source kind is required")
    source = find_signal_source(state, name)
    if source is None:
        source = {
            "id": next_id(state, "signal_source"),
            "name": name,
            "kind": kind,
            "enabled": True,
            "reason": reason or "",
            "config": deepcopy(config or {}),
            "budget": _budget(
                DEFAULT_SIGNAL_BUDGET_LIMIT if budget_limit is None else budget_limit,
                current_time,
            ),
            "created_at": current_time,
            "updated_at": current_time,
            "disabled_at": None,
        }
        ensure_signal_state(state)["sources"].append(source)
        return source
    source["kind"] = kind
    source["enabled"] = True
    source["reason"] = reason or source.get("reason") or ""
    source["config"] = deepcopy(config or source.get("config") or {})
    if budget_limit is not None:
        source["budget"] = _budget(budget_limit, current_time)
    else:
        _refresh_budget_window(source, current_time)
    source["updated_at"] = current_time
    source["disabled_at"] = None
    return source


def disable_signal_source(state, name, *, current_time=None):
    current_time = current_time or now_iso()
    source = find_signal_source(state, name)
    if source is None:
        return None
    source["enabled"] = False
    source["updated_at"] = current_time
    source["disabled_at"] = current_time
    return source


def list_signal_sources(state):
    return list(ensure_signal_state(state).get("sources", []))


def list_signal_journal(state, limit=20):
    journal = ensure_signal_state(state).get("journal", [])
    return list(journal[-max(0, int(limit)) :])


def record_signal_observation(
    state,
    source_name,
    *,
    kind,
    summary,
    reason_for_use,
    payload=None,
    budget_cost=1,
    queue_event=True,
    current_time=None,
):
    current_time = current_time or now_iso()
    source = find_signal_source(state, source_name)
    if source is None:
        return {"status": "blocked", "reason": "unknown_source", "source": None}
    if not source.get("enabled"):
        return {"status": "blocked", "reason": "source_disabled", "source": source}
    budget = _refresh_budget_window(source, current_time)
    cost = max(0, int(budget_cost or 0))
    if budget["used"] + cost > budget["limit"]:
        return {
            "status": "blocked",
            "reason": "budget_exhausted",
            "source": source,
            "budget": deepcopy(budget),
        }

    budget["used"] += cost
    journal = ensure_signal_state(state)["journal"]
    item = {
        "id": next_id(state, "signal"),
        "source": source.get("name"),
        "source_kind": source.get("kind"),
        "kind": (kind or "observation").strip() or "observation",
        "summary": summary or "",
        "payload": deepcopy(payload or {}),
        "reason_for_use": reason_for_use or "",
        "budget_cost": cost,
        "budget": {
            "window": budget.get("window"),
            "window_key": budget.get("window_key"),
            "limit": budget.get("limit"),
            "used_after": budget.get("used"),
        },
        "event_id": None,
        "created_at": current_time,
    }
    if queue_event:
        event = add_event(
            state,
            "signal_observed",
            f"signal:{source.get('name')}",
            {
                "signal_id": item["id"],
                "source": source.get("name"),
                "source_kind": source.get("kind"),
                "kind": item["kind"],
                "summary": item["summary"],
                "reason_for_use": item["reason_for_use"],
            },
        )
        item["event_id"] = event.get("id")
    journal.append(item)
    del journal[:-MAX_SIGNAL_JOURNAL]
    source["updated_at"] = current_time
    return {"status": "recorded", "source": source, "signal": item}


def _feed_local_name(tag):
    return (tag or "").rsplit("}", 1)[-1]


def _feed_child(element, name):
    if element is None:
        return None
    for child in element:
        if _feed_local_name(child.tag) == name:
            return child
    return None


def _feed_text(element, name):
    child = _feed_child(element, name)
    if child is None:
        return ""
    return (child.text or "").strip()


def _feed_link(element):
    link = _feed_child(element, "link")
    if link is None:
        return ""
    return (link.attrib.get("href") or link.text or "").strip()


def parse_signal_feed(xml_text):
    root = ElementTree.fromstring(xml_text or "")
    root_name = _feed_local_name(root.tag)
    if root_name == "rss":
        channel = _feed_child(root, "channel")
        item = _feed_child(channel, "item")
        link = _feed_text(item, "link") if item is not None else ""
    elif root_name == "feed":
        item = _feed_child(root, "entry")
        link = _feed_link(item) if item is not None else ""
    else:
        raise ValueError(f"unsupported feed root: {root_name}")
    if item is None:
        return None
    title = _feed_text(item, "title")
    summary = title or link
    if not summary:
        return None
    return {
        "kind": "rss_item",
        "summary": summary,
        "payload": {
            "title": title,
            "url": link,
        },
    }


def fetch_signal_source(state, source_name, *, opener=None, current_time=None):
    source = find_signal_source(state, source_name)
    if source is None:
        return {"status": "blocked", "reason": "unknown_source", "source": None}
    if not source.get("enabled"):
        return {"status": "blocked", "reason": "source_disabled", "source": source}
    if (source.get("kind") or "").strip() != "rss":
        return {"status": "blocked", "reason": "unsupported_source_kind", "source": source}
    url = ((source.get("config") or {}).get("url") or "").strip()
    if not url:
        return {"status": "blocked", "reason": "missing_url", "source": source}

    opener = opener or urlopen
    with opener(url, timeout=10) as response:
        feed_text = response.read().decode("utf-8", errors="replace")
    try:
        item = parse_signal_feed(feed_text)
    except (ElementTree.ParseError, ValueError):
        return {"status": "blocked", "reason": "invalid_feed", "source": source}
    if item is None:
        return {"status": "blocked", "reason": "no_items", "source": source}

    payload = deepcopy(item.get("payload") or {})
    payload.setdefault("feed_url", url)
    return record_signal_observation(
        state,
        source_name,
        kind=item.get("kind") or "rss_item",
        summary=item.get("summary") or "",
        reason_for_use=source.get("reason") or f"fetched from {url}",
        payload=payload,
        current_time=current_time,
    )


def format_signal_sources(sources):
    if not sources:
        return "No signal sources configured."
    lines = ["Signal sources:"]
    for source in sources:
        budget = source.get("budget") or {}
        enabled = "enabled" if source.get("enabled") else "disabled"
        lines.append(
            f"- {source.get('name')} [{source.get('kind')}] {enabled} "
            f"budget={budget.get('used', 0)}/{budget.get('limit', 0)} "
            f"reason={source.get('reason', '')}"
        )
    return "\n".join(lines)


def format_signal_journal(items):
    if not items:
        return "No signal observations recorded."
    lines = ["Signal journal:"]
    for item in items:
        event_text = f" event=#{item.get('event_id')}" if item.get("event_id") else ""
        lines.append(
            f"- #{item.get('id')} {item.get('source')}:{item.get('kind')}"
            f"{event_text} {item.get('summary', '')}"
        )
    return "\n".join(lines)
