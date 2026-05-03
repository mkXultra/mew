import json
from pathlib import Path

from .timeutil import now_iso
from .work_session import build_work_session_resume


def _read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {} if default is None else default


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _find_parent_with_result(path):
    current = Path(path).resolve(strict=False)
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        result_path = candidate / "result.json"
        if result_path.is_file():
            return candidate
    return current


def _trial_name_from_result(result, trial_dir):
    return (
        str(result.get("trial_name") or "")
        or str((result.get("task_id") or {}).get("name") or "")
        or Path(trial_dir).name
    )


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _reward_from_trial(trial_dir, trial_result):
    verifier_result = trial_result.get("verifier_result") if isinstance(trial_result, dict) else {}
    reward = None
    if isinstance(verifier_result, dict):
        reward = verifier_result.get("reward")
        if reward is None:
            reward = verifier_result.get("score")
    if reward is None and isinstance(trial_result, dict):
        reward = trial_result.get("reward")
    if reward is None:
        reward_text = _read_text(Path(trial_dir) / "verifier" / "reward.txt").strip()
        if reward_text:
            reward = reward_text
    return _safe_float(reward)


def _root_stats(job_dir):
    root_result = _read_json(Path(job_dir) / "result.json")
    stats = root_result.get("stats") if isinstance(root_result, dict) else {}
    return stats if isinstance(stats, dict) else {}


def _resume_candidates(report):
    candidates = []
    if not isinstance(report, dict):
        return candidates
    for key in ("resume", "work_session_resume"):
        value = report.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    for key in ("work_report", "work_session"):
        value = report.get(key)
        if isinstance(value, dict) and isinstance(value.get("resume"), dict):
            candidates.append(value["resume"])
    return candidates


def _primary_resume(report):
    candidates = _resume_candidates(report)
    return candidates[0] if candidates else {}


def _tool_calls_from_work_report(report):
    steps = ((report.get("work_report") or {}).get("steps") or []) if isinstance(report, dict) else []
    calls = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        call = step.get("tool_call")
        if isinstance(call, dict):
            calls.append(dict(call))
    return calls


def _model_turns_from_work_report(report):
    steps = ((report.get("work_report") or {}).get("steps") or []) if isinstance(report, dict) else []
    turns = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        turn = step.get("model_turn")
        if isinstance(turn, dict):
            turns.append(dict(turn))
    return turns


def _task_from_report(report, resume):
    task_id = report.get("task_id") or resume.get("task_id") or 1
    return {
        "id": task_id,
        "title": resume.get("title") or "terminal-bench replay task",
        "description": resume.get("goal") or "",
        "status": "ready",
        "kind": "coding",
    }


def _session_from_report(report):
    resume = _primary_resume(report)
    work_report = report.get("work_report") if isinstance(report.get("work_report"), dict) else {}
    session_id = work_report.get("session_id") or report.get("session_id") or resume.get("session_id") or 1
    task_id = work_report.get("task_id") or report.get("task_id") or resume.get("task_id") or 1
    long_build_state = resume.get("long_build_state") if isinstance(resume.get("long_build_state"), dict) else {}
    return {
        "id": session_id,
        "task_id": task_id,
        "status": "active",
        "title": resume.get("title") or "terminal-bench replay task",
        "goal": resume.get("goal") or "",
        "updated_at": resume.get("updated_at") or now_iso(),
        "tool_calls": _tool_calls_from_work_report(report),
        "model_turns": _model_turns_from_work_report(report),
        "long_command_runs": list(long_build_state.get("long_command_runs") or []),
        "default_options": {"verify_disabled": True},
        "_allow_synthesized_command_evidence": True,
    }


def _summarize_long_build_state(state):
    if not isinstance(state, dict) or not state:
        return {}
    current_failure = state.get("current_failure") if isinstance(state.get("current_failure"), dict) else {}
    recovery_decision = state.get("recovery_decision") if isinstance(state.get("recovery_decision"), dict) else {}
    allowed_next_action = (
        recovery_decision.get("allowed_next_action")
        if isinstance(recovery_decision.get("allowed_next_action"), dict)
        else {}
    )
    return {
        "status": state.get("status") or "",
        "incomplete_reason": state.get("incomplete_reason") or "",
        "latest_build_status": state.get("latest_build_status") or "",
        "latest_long_command_run_id": state.get("latest_long_command_run_id") or "",
        "latest_long_command_status": state.get("latest_long_command_status") or "",
        "current_failure_class": current_failure.get("failure_class") or "",
        "current_failure_status": current_failure.get("status") or "",
        "recovery_decision": recovery_decision.get("decision") or "",
        "recovery_action_kind": allowed_next_action.get("kind") or "",
        "strategy_blockers": [
            item.get("code") for item in state.get("strategy_blockers") or [] if isinstance(item, dict)
        ],
        "missing_artifacts": [
            item.get("path") for item in state.get("missing_artifacts") or [] if isinstance(item, dict)
        ],
    }


def _trial_report_paths(root):
    root = Path(root).expanduser()
    if root.is_file() and root.name == "mew-report.json":
        return [root.resolve(strict=False)]
    if not root.exists():
        return []
    reports = sorted(root.rglob("mew-report.json"))
    return [path.resolve(strict=False) for path in reports]


def _trial_entry_from_report(report_path):
    report_path = Path(report_path)
    report = _read_json(report_path)
    trial_dir = _find_parent_with_result(report_path)
    trial_result = _read_json(trial_dir / "result.json")
    transcript = _read_json(report_path.parent / "command-transcript.json")
    stored_resume = _primary_resume(report)
    session = _session_from_report(report)
    task = _task_from_report(report, stored_resume)
    recomputed_resume = {}
    replay_error = ""
    if session.get("tool_calls"):
        try:
            recomputed_resume = build_work_session_resume(session, task=task) or {}
        except Exception as exc:  # pragma: no cover - defensive replay should report, not crash.
            replay_error = str(exc)
    else:
        replay_error = "work_report steps did not contain replayable tool calls"
    reward = _reward_from_trial(trial_dir, trial_result)
    verifier_stdout = _read_text(trial_dir / "verifier" / "test-stdout.txt")
    stored_long = _summarize_long_build_state(stored_resume.get("long_build_state") or {})
    current_long = _summarize_long_build_state(recomputed_resume.get("long_build_state") or {})
    return {
        "trial_name": _trial_name_from_result(trial_result, trial_dir),
        "trial_dir": str(trial_dir),
        "report_path": str(report_path),
        "command_transcript_path": str(report_path.parent / "command-transcript.json"),
        "result_path": str(trial_dir / "result.json"),
        "verifier_stdout_path": str(trial_dir / "verifier" / "test-stdout.txt"),
        "external_reward": reward,
        "mew_exit_code": report.get("work_exit_code"),
        "stop_reason": (report.get("work_report") or {}).get("stop_reason") or "",
        "wall_timeout": bool((report.get("work_report") or {}).get("wall_timeout")),
        "command_exit_code": transcript.get("exit_code") if isinstance(transcript, dict) else None,
        "command_timed_out": bool(transcript.get("timed_out")) if isinstance(transcript, dict) else False,
        "stored": {
            "phase": stored_resume.get("phase") or "",
            "next_action": stored_resume.get("next_action") or "",
            "long_build_state": stored_long,
        },
        "current": {
            "recomputed": bool(recomputed_resume),
            "replay_error": replay_error,
            "phase": recomputed_resume.get("phase") or "",
            "next_action": recomputed_resume.get("next_action") or "",
            "long_build_state": current_long,
        },
        "verifier_stdout_excerpt": "\n".join((verifier_stdout or "").splitlines()[-12:]),
    }


def _check_assertions(entry, assertions):
    checks = []
    current_long = ((entry.get("current") or {}).get("long_build_state") or {})

    def add(name, passed, observed, expected):
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})

    expected = assertions.get("long_build_status")
    if expected:
        observed = current_long.get("status") or ""
        add("long_build_status", observed == expected, observed, expected)
    expected = assertions.get("current_failure")
    if expected:
        observed = current_long.get("current_failure_class") or ""
        add("current_failure", observed == expected, observed, expected)
    expected = assertions.get("recovery_action")
    if expected:
        observed = current_long.get("recovery_action_kind") or ""
        add("recovery_action", observed == expected, observed, expected)
    for blocker in assertions.get("blockers") or []:
        observed = current_long.get("strategy_blockers") or []
        add(f"blocker:{blocker}", blocker in observed, observed, blocker)
    expected = assertions.get("mew_exit_code")
    if expected is not None:
        observed = entry.get("mew_exit_code")
        add("mew_exit_code", observed == expected, observed, expected)
    expected = assertions.get("external_reward")
    if expected is not None:
        observed = entry.get("external_reward")
        add("external_reward", observed == expected, observed, expected)
    expected = assertions.get("next_action_contains")
    if expected:
        observed = (entry.get("current") or {}).get("next_action") or ""
        add("next_action_contains", expected in observed, observed, expected)
    return checks


def replay_terminal_bench_job(
    job_dir,
    *,
    task=None,
    trial=None,
    assertions=None,
):
    job_dir = Path(job_dir).expanduser().resolve(strict=False)
    assertions = dict(assertions or {})
    report_paths = _trial_report_paths(job_dir)
    entries = []
    for report_path in report_paths:
        entry = _trial_entry_from_report(report_path)
        if task and task not in entry.get("trial_name", "") and task not in entry.get("trial_dir", ""):
            continue
        if trial and trial != entry.get("trial_name") and trial not in entry.get("trial_dir", ""):
            continue
        entry["checks"] = _check_assertions(entry, assertions)
        entries.append(entry)
    stats = _root_stats(job_dir if job_dir.is_dir() else job_dir.parent)
    checks = []
    if not entries:
        checks.append(
            {
                "name": "replay_artifacts_found",
                "passed": False,
                "observed": str(job_dir),
                "expected": "at least one mew-report.json under job_dir",
            }
        )
    for entry in entries:
        checks.extend(entry.get("checks") or [])
        checks.append(
            {
                "name": f"{entry.get('trial_name')}:recomputed_resume",
                "passed": bool((entry.get("current") or {}).get("recomputed")),
                "observed": (entry.get("current") or {}).get("replay_error") or "ok",
                "expected": "current resume rebuilt from work_report steps",
            }
        )
    return {
        "kind": "terminal_bench_replay",
        "schema_version": 1,
        "generated_at": now_iso(),
        "job_dir": str(job_dir),
        "task_filter": task or "",
        "trial_filter": trial or "",
        "root_stats": stats,
        "trial_count": len(entries),
        "status": "pass" if all(check.get("passed") for check in checks) else "fail",
        "checks": checks,
        "trials": entries,
    }


def format_terminal_bench_replay(report):
    lines = [
        f"terminal-bench replay: {report.get('status')} trials={report.get('trial_count')}",
        f"job_dir: {report.get('job_dir')}",
    ]
    for entry in report.get("trials") or []:
        current_long = ((entry.get("current") or {}).get("long_build_state") or {})
        lines.append("")
        lines.append(
            f"- {entry.get('trial_name')} reward={entry.get('external_reward')} "
            f"mew_exit={entry.get('mew_exit_code')} stop={entry.get('stop_reason') or '-'}"
        )
        lines.append(
            "  current_long_build: "
            f"status={current_long.get('status') or '-'} "
            f"failure={current_long.get('current_failure_class') or '-'} "
            f"recovery={current_long.get('recovery_action_kind') or '-'}"
        )
        blockers = current_long.get("strategy_blockers") or []
        if blockers:
            lines.append(f"  blockers: {', '.join(str(item) for item in blockers)}")
    failed = [check for check in report.get("checks") or [] if not check.get("passed")]
    if failed:
        lines.append("")
        lines.append("failed checks:")
        for check in failed:
            lines.append(f"- {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return "\n".join(lines)
