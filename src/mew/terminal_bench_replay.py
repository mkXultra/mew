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


def _raw_action_from_model_turn(turn):
    if not isinstance(turn, dict):
        return {}
    for key in ("action_plan", "decision_plan"):
        plan = turn.get(key)
        if isinstance(plan, dict) and isinstance(plan.get("action"), dict):
            return dict(plan["action"])
    action = turn.get("action")
    if isinstance(action, dict) and isinstance(action.get("blocked_action"), dict):
        return dict(action["blocked_action"])
    return dict(action) if isinstance(action, dict) else {}


def _llm_action_fixture_from_step(step):
    if not isinstance(step, dict):
        return {}
    turn = step.get("model_turn")
    if not isinstance(turn, dict):
        return {}
    raw_action = _raw_action_from_model_turn(turn)
    if not raw_action:
        return {}
    post_policy_action = turn.get("action") if isinstance(turn.get("action"), dict) else {}
    return {
        "step_index": step.get("index"),
        "step_status": step.get("status") or "",
        "model_turn_id": turn.get("id"),
        "model_turn_status": turn.get("status") or "",
        "raw_action": raw_action,
        "post_policy_action": dict(post_policy_action),
        "source": "model_turn.action_plan.action",
    }


def _llm_action_fixtures_from_work_report(report):
    steps = ((report.get("work_report") or {}).get("steps") or []) if isinstance(report, dict) else []
    fixtures = []
    for step in steps:
        fixture = _llm_action_fixture_from_step(step)
        if fixture:
            fixtures.append(fixture)
    return fixtures


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
    session = {
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
    frontier = resume.get("active_compatibility_frontier")
    if isinstance(frontier, dict) and frontier:
        session["active_compatibility_frontier"] = dict(frontier)
    return session


def _summarize_active_compatibility_frontier(frontier):
    frontier = frontier if isinstance(frontier, dict) else {}
    if not frontier:
        return {}
    signature = frontier.get("failure_signature") if isinstance(frontier.get("failure_signature"), dict) else {}
    closure = frontier.get("closure_state") if isinstance(frontier.get("closure_state"), dict) else {}
    compact = frontier.get("compact_summary") if isinstance(frontier.get("compact_summary"), dict) else {}
    candidates = frontier.get("open_candidates") or frontier.get("sibling_candidates") or compact.get("open_candidates") or []
    open_candidate_ids = []
    for candidate in candidates:
        if isinstance(candidate, dict):
            status = str(candidate.get("status") or "unexplored")
            if status in {"verified", "rejected", "deferred"}:
                continue
            if candidate.get("id"):
                open_candidate_ids.append(candidate.get("id"))
        elif candidate:
            open_candidate_ids.append(str(candidate))
    next_action = closure.get("next_action") or compact.get("next_action") or ""
    return {
        "id": frontier.get("id") or "",
        "status": frontier.get("status") or "",
        "signature": signature.get("fingerprint") or compact.get("failure_signature") or "",
        "kind": signature.get("kind") or "",
        "family_key": signature.get("family_key") or "",
        "runtime_component_kind": signature.get("runtime_component_kind") or "",
        "next_action": next_action,
        "guard_mode": closure.get("guard_mode") or compact.get("guard_mode") or "",
        "blocked_action_kinds": list(closure.get("blocked_action_kinds") or compact.get("blocked_action_kinds") or []),
        "open_candidate_count": len(open_candidate_ids),
        "open_candidate_ids": open_candidate_ids[:8],
        "evidence_ref_count": len(frontier.get("evidence_refs") or compact.get("evidence_refs") or []),
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
            stored_frontier = stored_resume.get("active_compatibility_frontier")
            if isinstance(stored_frontier, dict) and stored_frontier:
                recomputed_resume["active_compatibility_frontier"] = dict(stored_frontier)
        except Exception as exc:  # pragma: no cover - defensive replay should report, not crash.
            replay_error = str(exc)
    else:
        replay_error = "work_report steps did not contain replayable tool calls"
    reward = _reward_from_trial(trial_dir, trial_result)
    verifier_stdout = _read_text(trial_dir / "verifier" / "test-stdout.txt")
    stored_long = _summarize_long_build_state(stored_resume.get("long_build_state") or {})
    current_long = _summarize_long_build_state(recomputed_resume.get("long_build_state") or {})
    stored_frontier = _summarize_active_compatibility_frontier(stored_resume.get("active_compatibility_frontier"))
    current_frontier = _summarize_active_compatibility_frontier(
        recomputed_resume.get("active_compatibility_frontier")
    )
    llm_action_fixtures = _llm_action_fixtures_from_work_report(report)
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
        "llm_action_fixture_count": len(llm_action_fixtures),
        "latest_llm_action_fixture": llm_action_fixtures[-1] if llm_action_fixtures else {},
        "stored": {
            "phase": stored_resume.get("phase") or "",
            "next_action": stored_resume.get("next_action") or "",
            "long_build_state": stored_long,
            "active_compatibility_frontier": stored_frontier,
        },
        "current": {
            "recomputed": bool(recomputed_resume),
            "replay_error": replay_error,
            "phase": recomputed_resume.get("phase") or "",
            "next_action": recomputed_resume.get("next_action") or "",
            "long_build_state": current_long,
            "active_compatibility_frontier": current_frontier,
        },
        "verifier_stdout_excerpt": "\n".join((verifier_stdout or "").splitlines()[-12:]),
    }


def terminal_bench_llm_action_fixture_contexts(job_dir, *, task=None, trial=None):
    """Return replay contexts for model-chosen actions saved in Harbor artifacts.

    The provider's exact raw text is not persisted in all historical artifacts.
    This exposes the raw action JSON that mew parsed from each model turn, plus
    the reconstructed session/task needed to re-run policy checks around that
    action without rerunning Harbor.
    """
    contexts = []
    for report_path in _trial_report_paths(job_dir):
        report_path = Path(report_path)
        report = _read_json(report_path)
        trial_dir = _find_parent_with_result(report_path)
        trial_result = _read_json(trial_dir / "result.json")
        trial_name = _trial_name_from_result(trial_result, trial_dir)
        if task and task not in trial_name and task not in str(trial_dir):
            continue
        if trial and trial != trial_name and trial not in str(trial_dir):
            continue
        stored_resume = _primary_resume(report)
        session = _session_from_report(report)
        task_data = _task_from_report(report, stored_resume)
        for fixture in _llm_action_fixtures_from_work_report(report):
            contexts.append(
                {
                    "trial_name": trial_name,
                    "trial_dir": str(trial_dir),
                    "report_path": str(report_path),
                    "fixture": fixture,
                    "session": session,
                    "task": task_data,
                }
            )
    return contexts


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
    current_frontier = ((entry.get("current") or {}).get("active_compatibility_frontier") or {})
    expected = assertions.get("frontier_signature")
    if expected:
        observed = current_frontier.get("signature") or ""
        add("frontier_signature", observed == expected, observed, expected)
    if assertions.get("frontier_signature_required"):
        observed = current_frontier.get("signature") or ""
        add("frontier_signature_required", bool(observed), observed, "non-empty frontier signature")
    stored_frontier = ((entry.get("stored") or {}).get("active_compatibility_frontier") or {})
    if assertions.get("frontier_signature_matches_stored"):
        observed = current_frontier.get("signature") or ""
        expected_stored = stored_frontier.get("signature") or ""
        add("frontier_signature_matches_stored", bool(expected_stored) and observed == expected_stored, observed, expected_stored)
    expected = assertions.get("frontier_family_key")
    if expected:
        observed = current_frontier.get("family_key") or ""
        add("frontier_family_key", observed == expected, observed, expected)
    if assertions.get("frontier_family_key_matches_stored"):
        observed = current_frontier.get("family_key") or ""
        expected_stored = stored_frontier.get("family_key") or ""
        add("frontier_family_key_matches_stored", bool(expected_stored) and observed == expected_stored, observed, expected_stored)
    expected = assertions.get("frontier_next_action_contains")
    if expected:
        observed = current_frontier.get("next_action") or ""
        add("frontier_next_action_contains", expected in observed, observed, expected)
    if assertions.get("frontier_next_action_required"):
        observed = current_frontier.get("next_action") or ""
        add("frontier_next_action_required", bool(observed), observed, "non-empty frontier next_action")
    if assertions.get("frontier_next_action_matches_stored"):
        observed = current_frontier.get("next_action") or ""
        expected_stored = stored_frontier.get("next_action") or ""
        add("frontier_next_action_matches_stored", bool(expected_stored) and observed == expected_stored, observed, expected_stored)
    expected = assertions.get("frontier_open_candidate_count_min")
    if expected is not None:
        observed = current_frontier.get("open_candidate_count") or 0
        add("frontier_open_candidate_count_min", observed >= int(expected), observed, f">={expected}")
    if assertions.get("frontier_open_candidate_ids_match_stored"):
        observed = current_frontier.get("open_candidate_ids") or []
        expected_stored = stored_frontier.get("open_candidate_ids") or []
        add(
            "frontier_open_candidate_ids_match_stored",
            bool(expected_stored) and observed == expected_stored,
            observed,
            expected_stored,
        )
    expected = assertions.get("frontier_evidence_ref_count_min")
    if expected is not None:
        observed = current_frontier.get("evidence_ref_count") or 0
        add("frontier_evidence_ref_count_min", observed >= int(expected), observed, f">={expected}")
    if assertions.get("frontier_evidence_ref_count_matches_stored"):
        observed = current_frontier.get("evidence_ref_count") or 0
        expected_stored = stored_frontier.get("evidence_ref_count") or 0
        add(
            "frontier_evidence_ref_count_matches_stored",
            expected_stored > 0 and observed == expected_stored,
            observed,
            expected_stored,
        )
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
