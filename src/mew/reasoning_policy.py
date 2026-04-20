import os
from contextlib import contextmanager


CODEX_REASONING_ENV = "MEW_CODEX_REASONING_EFFORT"
VALID_REASONING_EFFORTS = {"low", "medium", "high", "xhigh"}
HIGH_RISK_TERMS = (
    "approval",
    "auth",
    "daemon",
    "governance",
    "m5",
    "m6",
    "permission",
    "policy",
    "recovery",
    "roadmap",
    "rollback",
    "safety",
    "security",
)
TASK_HISTORY_MARKERS = (
    "\n\nRecently completed git commits",
    "\n\nCurrent coding focus:",
    "\n\nRecent friction",
    "\n\nConstraints:",
)


def normalize_reasoning_effort(value):
    text = str(value or "").strip().casefold()
    return text if text in VALID_REASONING_EFFORTS else ""


def _joined_text(*values):
    return " ".join(str(value or "") for value in values if value)


def _matching_high_risk_terms(text):
    lowered = str(text or "").casefold()
    return [term for term in HIGH_RISK_TERMS if term in lowered]


def task_policy_description(task):
    description = str((task or {}).get("description") or "")
    for marker in TASK_HISTORY_MARKERS:
        if marker in description:
            description = description.split(marker, 1)[0]
    return description


def select_work_reasoning_policy(task=None, *, guidance="", capabilities=None, env=None):
    env = os.environ if env is None else env
    override = normalize_reasoning_effort(env.get(CODEX_REASONING_ENV))
    if override:
        return {
            "effort": override,
            "source": "env_override",
            "work_type": "explicit",
            "reason": f"{CODEX_REASONING_ENV}={override}",
        }

    task = task or {}
    capabilities = capabilities or {}
    text = _joined_text(
        task.get("title"),
        task_policy_description(task),
        task.get("notes"),
        guidance,
    )
    high_risk_terms = _matching_high_risk_terms(text)
    if high_risk_terms:
        return {
            "effort": "high",
            "source": "auto",
            "work_type": "high_risk",
            "reason": f"matched high-risk terms: {', '.join(high_risk_terms[:5])}",
            "matched_terms": high_risk_terms,
        }

    write_roots = capabilities.get("allowed_write_roots") or capabilities.get("allow_write_roots")
    if write_roots or capabilities.get("allow_verify"):
        return {
            "effort": "medium",
            "source": "auto",
            "work_type": "small_implementation",
            "reason": "write or verification capability is enabled for a non-high-risk work turn",
        }

    return {
        "effort": "low",
        "source": "auto",
        "work_type": "exploration",
        "reason": "read-only non-high-risk work turn",
    }


@contextmanager
def codex_reasoning_effort_scope(effort):
    normalized = normalize_reasoning_effort(effort)
    if not normalized:
        yield
        return

    previous = os.environ.get(CODEX_REASONING_ENV)
    os.environ[CODEX_REASONING_ENV] = normalized
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(CODEX_REASONING_ENV, None)
        else:
            os.environ[CODEX_REASONING_ENV] = previous
