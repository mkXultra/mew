import os
import re
from contextlib import contextmanager


CODEX_REASONING_ENV = "MEW_CODEX_REASONING_EFFORT"
VALID_REASONING_EFFORTS = {"low", "medium", "high", "xhigh"}
HIGH_RISK_TERMS = (
    "approval",
    "auth",
    "daemon",
    "governance",
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
NOTE_HISTORY_MARKERS = (
    "Dogfood note:",
    "Long session checkpoint:",
    "Context save ",
)
HIGH_RISK_NEGATION_MARKERS = (
    "out of scope",
    "out-of-scope",
    "outside scope",
    "not in scope",
    "reviewer-owned",
    "do not edit",
    "do not touch",
)
HIGH_RISK_KEEP_DIRTY_MARKERS = (
    "proof-artifacts",
    "proof artifacts",
    "proof artifact",
    "roadmap_status.md",
    "proofs",
)
COMPLEX_IMPLEMENTATION_TERMS = (
    "compiler",
    "concurrent",
    "cross-compile",
    "cross compile",
    "distributed",
    "emulator",
    "elf",
    "interpreter",
    "linker",
    "loader",
    "mips",
    "multi-file",
    "multi file",
    "parser",
    "provided source",
    "runtime",
    "scheduler",
    "source code",
    "state machine",
    "terminal-bench",
    "toolchain",
    "virtual machine",
    "vm.js",
)
COMPLEX_IMPLEMENTATION_TEXT_CHARS = 1200


def normalize_reasoning_effort(value):
    text = str(value or "").strip().casefold()
    return text if text in VALID_REASONING_EFFORTS else ""


def _joined_text(*values):
    return "\n".join(str(value or "") for value in values if value)


def _line_suppresses_high_risk(line):
    lowered = str(line or "").casefold()
    if not lowered:
        return False
    if "dirty" in lowered and any(
        marker in lowered for marker in HIGH_RISK_KEEP_DIRTY_MARKERS
    ):
        return True
    return any(marker in lowered for marker in HIGH_RISK_NEGATION_MARKERS)


def _matching_high_risk_terms(text):
    matches = []
    for line in str(text or "").splitlines() or [str(text or "")]:
        lowered = str(line or "").casefold()
        lowered = (
            lowered.replace("reasoning-policy", "reasoning")
            .replace("reasoning_policy", "reasoning")
            .replace("reasoning policy", "reasoning")
        )
        if _line_suppresses_high_risk(lowered):
            continue
        for term in HIGH_RISK_TERMS:
            if term in lowered and term not in matches:
                matches.append(term)
    return matches


def _matching_complex_implementation_terms(text):
    lowered = str(text or "").casefold()
    matches = []
    for term in COMPLEX_IMPLEMENTATION_TERMS:
        if _complex_term_matches(lowered, term) and term not in matches:
            matches.append(term)
    return matches


def _complex_term_matches(lowered_text, term):
    normalized = str(term or "").casefold()
    if normalized in {"elf", "mips"}:
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", lowered_text) is not None
    return normalized in lowered_text


def task_policy_description(task):
    description = str((task or {}).get("description") or "")
    for marker in TASK_HISTORY_MARKERS:
        if marker in description:
            description = description.split(marker, 1)[0]
    return description


def task_policy_notes(task):
    notes = str((task or {}).get("notes") or "")
    kept_lines = []
    for line in notes.splitlines():
        if any(marker.casefold() in line.casefold() for marker in NOTE_HISTORY_MARKERS):
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines)


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
        task_policy_notes(task),
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
    implementation_capable = bool(write_roots or capabilities.get("allow_verify"))
    if implementation_capable:
        complex_terms = _matching_complex_implementation_terms(text)
        if complex_terms or len(text) >= COMPLEX_IMPLEMENTATION_TEXT_CHARS:
            reason = (
                f"matched complex implementation terms: {', '.join(complex_terms[:5])}"
                if complex_terms
                else f"task text is long enough for complex implementation: {len(text)} chars"
            )
            result = {
                "effort": "high",
                "source": "auto",
                "work_type": "complex_implementation",
                "reason": reason,
            }
            if complex_terms:
                result["matched_terms"] = complex_terms
            return result

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
