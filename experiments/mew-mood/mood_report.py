from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_ITEMS = 8


@dataclass
class AxisScore:
    value: int
    reasons: list[str]


@dataclass
class MoodScores:
    energy: AxisScore
    worry: AxisScore
    joy: AxisScore
    label: str


@dataclass
class OutputPaths:
    mood: Path


def load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_date(state: dict[str, Any], explicit_date: str | None = None) -> str:
    if explicit_date:
        return explicit_date
    for key in ("date", "today", "current_date"):
        value = state.get(key)
        if isinstance(value, str) and value:
            return value
    return datetime.now().date().isoformat()


def build_paths(base_dir: Path, day: str) -> OutputPaths:
    return OutputPaths(mood=base_dir / ".mew" / "mood" / f"{day}.md")


def clamp(value: int, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, value))


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def task_ref(task: dict[str, Any]) -> str:
    title = normalize_text(task.get("title")) or "Untitled"
    status = normalize_text(task.get("status")) or "unknown"
    task_id = task.get("id")
    prefix = f"#{task_id} " if task_id is not None else ""
    return f"{prefix}{title} [{status}]"


def tasks_by_status(state: dict[str, Any], status: str) -> list[dict[str, Any]]:
    return [
        task
        for task in state.get("tasks", [])
        if isinstance(task, dict) and normalize_text(task.get("status")).casefold() == status
    ]


def open_tasks(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        task
        for task in state.get("tasks", [])
        if isinstance(task, dict) and normalize_text(task.get("status")).casefold() != "done"
    ]


def active_work_sessions(state: dict[str, Any]) -> list[dict[str, Any]]:
    sessions = []
    single_session = state.get("work_session")
    if isinstance(single_session, dict):
        sessions.append(single_session)
    raw_sessions = state.get("work_sessions")
    if isinstance(raw_sessions, list):
        sessions.extend(session for session in raw_sessions if isinstance(session, dict))
    return [session for session in sessions if session.get("status") == "active"]


def open_questions(state: dict[str, Any]) -> list[dict[str, Any]]:
    questions = []
    for message in state.get("outbox", []):
        if not isinstance(message, dict):
            continue
        if message.get("requires_reply") and not message.get("answered_at"):
            questions.append(message)
    return questions


def open_attention_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    attention = state.get("attention")
    if not isinstance(attention, dict):
        return []
    items = attention.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and item.get("status") == "open"]


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
    count = 0
    for run in verification_runs(state)[-MAX_ITEMS:]:
        if run.get("exit_code") == 0:
            count += 1
    return count


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
    open_count = len(open_tasks(state))
    question_count = len(open_questions(state))
    session_count = len(active_work_sessions(state))
    passed_verifications = count_recent_passed_verifications(state)

    value = 55
    value += min(done_count * 6, 24)
    value += min(passed_verifications * 2, 10)
    value -= min(open_count * 4, 24)
    value -= min(question_count * 8, 24)
    value -= min(session_count * 3, 9)

    reasons: list[str] = []
    add_reason(reasons, done_count > 0, f"{done_count} recent done task(s) add momentum")
    add_reason(reasons, passed_verifications > 0, f"{passed_verifications} recent passed verification(s) add confidence")
    add_reason(reasons, open_count > 0, f"{open_count} open task(s) consume attention")
    add_reason(reasons, question_count > 0, f"{question_count} unanswered question(s) reduce free energy")
    add_reason(reasons, session_count > 0, f"{session_count} active work session(s) need reentry care")
    if not reasons:
        reasons.append("No strong energy signals found")
    return AxisScore(clamp(value), reasons[:MAX_ITEMS])


def score_worry(state: dict[str, Any]) -> AxisScore:
    question_count = len(open_questions(state))
    open_attention_count = len(open_attention_items(state))
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
    add_reason(reasons, open_attention_count > 0, f"{open_attention_count} open attention item(s) need resolution")
    add_reason(reasons, blocked_count > 0, f"{blocked_count} blocked task(s) detected")
    add_reason(reasons, failed_verifications > 0, f"{failed_verifications} recent failed verification(s) detected")
    add_reason(reasons, failed_effects > 0, f"{failed_effects} recent runtime effect issue(s) detected")
    add_reason(reasons, passed_verifications > 0, f"{passed_verifications} recent passed verification(s) offset worry")
    if not reasons:
        reasons.append("No strong worry signals found")
    return AxisScore(clamp(value), reasons[:MAX_ITEMS])


def score_joy(state: dict[str, Any]) -> AxisScore:
    done_count = len(tasks_by_status(state, "done")[-MAX_ITEMS:])
    passed_verifications = count_recent_passed_verifications(state)
    question_count = len(open_questions(state))
    failed_verifications = count_recent_failed_verifications(state)

    value = 30
    value += min(done_count * 8, 40)
    value += min(passed_verifications * 3, 15)
    value -= min(question_count * 5, 20)
    value -= min(failed_verifications * 10, 30)

    reasons: list[str] = []
    add_reason(reasons, done_count > 0, f"{done_count} recent done task(s) create positive signal")
    add_reason(reasons, passed_verifications > 0, f"{passed_verifications} recent passed verification(s) create trust")
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
    for task in open_tasks(state)[:MAX_ITEMS]:
        lines.append(f"open task: {task_ref(task)}")
    for question in open_questions(state)[:MAX_ITEMS]:
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


def render_axis(name: str, score: AxisScore) -> list[str]:
    lines = [f"### {name}", f"- score: {score.value}"]
    for reason in score.reasons:
        lines.append(f"- {reason}")
    return lines


def render_mood(day: str, state: dict[str, Any]) -> str:
    scores = compute_mood(state)
    lines = [
        f"# Mew Mood {day}",
        "",
        f"Current mood: **{scores.label}**",
        "",
        "## Scores",
        "",
        *render_axis("Energy", scores.energy),
        "",
        *render_axis("Worry", scores.worry),
        "",
        *render_axis("Joy", scores.joy),
        "",
        "## Signals",
    ]
    signals = signal_lines(state)
    if signals:
        for signal in signals:
            lines.append(f"- {signal}")
    else:
        lines.append("- No active signals recorded")
    return "\n".join(lines) + "\n"


def write_outputs(paths: OutputPaths, mood_text: str) -> None:
    paths.mood.parent.mkdir(parents=True, exist_ok=True)
    paths.mood.write_text(mood_text, encoding="utf-8")


def generate(state_path: Path, output_dir: Path, explicit_date: str | None = None) -> OutputPaths:
    state = load_state(state_path)
    day = resolve_date(state, explicit_date)
    paths = build_paths(output_dir, day)
    write_outputs(paths, render_mood(day, state))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a mew mood report from state JSON")
    parser.add_argument("state_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--date")
    args = parser.parse_args(argv)

    paths = generate(args.state_path, args.output_dir, args.date)
    print(paths.mood)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
