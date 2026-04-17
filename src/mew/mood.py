from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .desk import (
    active_work_sessions_for_desk,
    open_attention_for_desk,
    open_questions_for_desk,
    open_tasks_for_desk,
)
from .report_io import write_generated_report


MAX_ITEMS = 8
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class AxisScore:
    value: int
    reasons: list[str]


@dataclass(frozen=True)
class MoodScores:
    energy: AxisScore
    worry: AxisScore
    joy: AxisScore
    label: str


def validate_date(value: str) -> str:
    if not DATE_PATTERN.fullmatch(value):
        raise ValueError("date must be in YYYY-MM-DD format")
    return value


def resolve_mood_date(explicit_date: str | None = None) -> str:
    if explicit_date:
        return validate_date(explicit_date)
    return validate_date(datetime.now().date().isoformat())


def mood_path(output_dir: Path, day: str) -> Path:
    return output_dir / ".mew" / "mood" / f"{day}.md"


def clamp(value: int, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, value))


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def tasks_by_status(state: dict[str, Any], status: str) -> list[dict[str, Any]]:
    return [
        task
        for task in state.get("tasks", [])
        if isinstance(task, dict) and normalize_text(task.get("status")).casefold() == status
    ]


def task_ref(task: dict[str, Any]) -> str:
    title = normalize_text(task.get("title")) or "Untitled"
    status = normalize_text(task.get("status")) or "unknown"
    task_id = task.get("id")
    prefix = f"#{task_id} " if task_id is not None else ""
    return f"{prefix}{title} [{status}]"


def verification_runs(state: dict[str, Any]) -> list[dict[str, Any]]:
    runs = state.get("verification_runs")
    if not isinstance(runs, list):
        return []
    return [run for run in runs if isinstance(run, dict)]


def recent_runtime_effects(state: dict[str, Any]) -> list[dict[str, Any]]:
    effects = state.get("runtime_effects")
    if not isinstance(effects, list):
        return []
    return [effect for effect in effects if isinstance(effect, dict)][-MAX_ITEMS:]


def failed_runtime_effects(state: dict[str, Any]) -> list[dict[str, Any]]:
    failed = []
    for effect in recent_runtime_effects(state):
        status = normalize_text(effect.get("status")).casefold()
        error = normalize_text(effect.get("error"))
        if status not in ("", "applied") or error:
            failed.append(effect)
    return failed


def count_recent_passed_verifications(state: dict[str, Any]) -> int:
    return sum(1 for run in verification_runs(state)[-MAX_ITEMS:] if run.get("exit_code") == 0)


def count_recent_failed_verifications(state: dict[str, Any]) -> int:
    count = 0
    for run in verification_runs(state)[-MAX_ITEMS:]:
        exit_code = run.get("exit_code")
        if exit_code not in (None, 0):
            count += 1
    return count


def add_reason(reasons: list[str], condition: bool, text: str) -> None:
    if condition:
        reasons.append(text)


def score_energy(state: dict[str, Any]) -> AxisScore:
    done_count = len(tasks_by_status(state, "done")[-MAX_ITEMS:])
    open_count = len(open_tasks_for_desk(state))
    question_count = len(open_questions_for_desk(state))
    session_count = len(active_work_sessions_for_desk(state))
    passed_verifications = count_recent_passed_verifications(state)

    value = 55
    value += min(done_count * 6, 24)
    value += min(passed_verifications * 2, 10)
    value -= min(open_count * 4, 24)
    value -= min(question_count * 8, 24)
    value -= min(session_count * 3, 9)

    reasons: list[str] = []
    add_reason(reasons, done_count > 0, f"{done_count} recent done task(s) add momentum")
    add_reason(
        reasons,
        passed_verifications > 0,
        f"{passed_verifications} recent passed verification(s) add confidence",
    )
    add_reason(reasons, open_count > 0, f"{open_count} open task(s) consume attention")
    add_reason(reasons, question_count > 0, f"{question_count} unanswered question(s) reduce free energy")
    add_reason(reasons, session_count > 0, f"{session_count} active work session(s) need reentry care")
    if not reasons:
        reasons.append("No strong energy signals found")
    return AxisScore(clamp(value), reasons[:MAX_ITEMS])


def score_worry(state: dict[str, Any]) -> AxisScore:
    question_count = len(open_questions_for_desk(state))
    open_attention_count = len(open_attention_for_desk(state))
    blocked_count = len(tasks_by_status(state, "blocked"))
    failed_verifications = count_recent_failed_verifications(state)
    failed_effects = len(failed_runtime_effects(state))
    passed_verifications = count_recent_passed_verifications(state)

    value = 20
    value += min(question_count * 15, 45)
    value += min(open_attention_count * 8, 32)
    value += min(blocked_count * 10, 30)
    value += min(failed_verifications * 20, 40)
    value += min(failed_effects * 12, 36)
    value -= min(passed_verifications * 3, 15)

    reasons: list[str] = []
    add_reason(reasons, question_count > 0, f"{question_count} unanswered question(s) are waiting")
    add_reason(
        reasons,
        open_attention_count > 0,
        f"{open_attention_count} open attention item(s) need resolution",
    )
    add_reason(reasons, blocked_count > 0, f"{blocked_count} blocked task(s) detected")
    add_reason(
        reasons,
        failed_verifications > 0,
        f"{failed_verifications} recent failed verification(s) detected",
    )
    add_reason(reasons, failed_effects > 0, f"{failed_effects} recent runtime effect issue(s) detected")
    add_reason(reasons, passed_verifications > 0, f"{passed_verifications} recent passed verification(s) offset worry")
    if not reasons:
        reasons.append("No strong worry signals found")
    return AxisScore(clamp(value), reasons[:MAX_ITEMS])


def score_joy(state: dict[str, Any]) -> AxisScore:
    done_count = len(tasks_by_status(state, "done")[-MAX_ITEMS:])
    passed_verifications = count_recent_passed_verifications(state)
    question_count = len(open_questions_for_desk(state))
    failed_verifications = count_recent_failed_verifications(state)

    value = 30
    value += min(done_count * 8, 40)
    value += min(passed_verifications * 3, 15)
    value -= min(question_count * 5, 20)
    value -= min(failed_verifications * 10, 30)

    reasons: list[str] = []
    add_reason(reasons, done_count > 0, f"{done_count} recent done task(s) create positive signal")
    add_reason(
        reasons,
        passed_verifications > 0,
        f"{passed_verifications} recent passed verification(s) create trust",
    )
    add_reason(reasons, question_count > 0, f"{question_count} unanswered question(s) hold joy back")
    add_reason(reasons, failed_verifications > 0, f"{failed_verifications} failed verification(s) hold joy back")
    if not reasons:
        reasons.append("No strong joy signals found")
    return AxisScore(clamp(value), reasons[:MAX_ITEMS])


def mood_label(energy: int, worry: int, joy: int) -> str:
    if worry >= 70 and energy < 40:
        return "overloaded"
    if joy >= 65 and worry >= 50:
        return "productive but watchful"
    if joy >= 65:
        return "pleased"
    if worry >= 60:
        return "concerned"
    if energy >= 65:
        return "ready"
    if energy < 35:
        return "tired"
    return "steady"


def compute_mood(state: dict[str, Any]) -> MoodScores:
    energy = score_energy(state)
    worry = score_worry(state)
    joy = score_joy(state)
    return MoodScores(
        energy=energy,
        worry=worry,
        joy=joy,
        label=mood_label(energy.value, worry.value, joy.value),
    )


def signal_lines(state: dict[str, Any]) -> list[str]:
    lines = []
    for task in open_tasks_for_desk(state)[:MAX_ITEMS]:
        lines.append(f"open task: {task_ref(task)}")
    for question in open_questions_for_desk(state)[:MAX_ITEMS]:
        question_id = question.get("question_id") or question.get("id")
        text = normalize_text(question.get("text")) or "Untitled question"
        lines.append(f"open question #{question_id}: {text}")
    for effect in reversed(recent_runtime_effects(state)):
        effect_id = effect.get("id", "?")
        reason = normalize_text(effect.get("reason")) or "unknown"
        status = normalize_text(effect.get("status")) or "unknown"
        lines.append(f"runtime effect #{effect_id}: {status}/{reason}")
        if len(lines) >= MAX_ITEMS:
            break
    return lines[:MAX_ITEMS]


def axis_to_dict(score: AxisScore) -> dict[str, Any]:
    return {"score": score.value, "reasons": list(score.reasons)}


def build_mood_view_model(state: dict[str, Any], explicit_date: str | None = None) -> dict[str, Any]:
    day = resolve_mood_date(explicit_date)
    scores = compute_mood(state)
    return {
        "date": day,
        "label": scores.label,
        "scores": {
            "energy": axis_to_dict(scores.energy),
            "worry": axis_to_dict(scores.worry),
            "joy": axis_to_dict(scores.joy),
        },
        "signals": signal_lines(state),
    }


def render_axis(name: str, score: dict[str, Any]) -> list[str]:
    lines = [f"### {name}", f"- score: {score['score']}"]
    for reason in score["reasons"]:
        lines.append(f"- {reason}")
    return lines


def render_mood_markdown(view_model: dict[str, Any]) -> str:
    scores = view_model["scores"]
    lines = [
        f"# Mew Mood {view_model['date']}",
        "",
        f"Current mood: **{view_model['label']}**",
        "",
        "## Scores",
        "",
        *render_axis("Energy", scores["energy"]),
        "",
        *render_axis("Worry", scores["worry"]),
        "",
        *render_axis("Joy", scores["joy"]),
        "",
        "## Signals",
    ]
    signals = view_model["signals"]
    if signals:
        for signal in signals:
            lines.append(f"- {signal}")
    else:
        lines.append("- No active signals recorded")
    return "\n".join(lines) + "\n"


def format_mood_view(view_model: dict[str, Any]) -> str:
    scores = view_model["scores"]
    return "\n".join(
        [
            f"Mew mood {view_model['date']}",
            f"label: {view_model['label']}",
            f"energy: {scores['energy']['score']}",
            f"worry: {scores['worry']['score']}",
            f"joy: {scores['joy']['score']}",
        ]
    )


def write_mood_report(view_model: dict[str, Any], output_dir: Path) -> Path:
    path = mood_path(output_dir, view_model["date"])
    write_generated_report(path, render_mood_markdown(view_model))
    return path
