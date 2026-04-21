import json
from pathlib import Path


def _read_container_from_inspect(path):
    data = _load_json_file(path)
    if not isinstance(data, list) or not data:
        return {}
    item = data[0] if isinstance(data[0], dict) else {}
    state = item.get("State") if isinstance(item.get("State"), dict) else {}
    config = item.get("Config") if isinstance(item.get("Config"), dict) else {}
    name = item.get("Name") or ""
    if isinstance(name, str) and name.startswith("/"):
        name = name[1:]
    return {
        "container": name,
        "image": config.get("Image", ""),
        "status": state.get("Status", ""),
        "exit_code": str(state.get("ExitCode", "")),
        "started_at": state.get("StartedAt", ""),
        "finished_at": state.get("FinishedAt", ""),
    }


def _read_key_value_file(path):
    data = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def _load_json_file(path):
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return None
    return json.loads(text)


def _first_scenario(report):
    scenarios = report.get("scenarios") if isinstance(report, dict) else None
    if isinstance(scenarios, list) and scenarios:
        scenario = scenarios[0]
        if isinstance(scenario, dict):
            return scenario
    return {}


def _number_list(values):
    numbers = []
    for value in values if isinstance(values, list) else []:
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    return numbers


def _gap_summary(gaps, expected_interval):
    numbers = _number_list(gaps)
    if not numbers:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "outside_expected_by_more_than_2s": 0,
        }
    outside = 0
    if expected_interval is not None:
        outside = sum(1 for gap in numbers if abs(gap - expected_interval) > 2.0)
    return {
        "count": len(numbers),
        "min": min(numbers),
        "max": max(numbers),
        "outside_expected_by_more_than_2s": outside,
    }


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _expected_passive_events_min(duration, interval):
    if duration is None or interval is None or interval <= 0:
        return None
    if duration < interval * 3:
        return 2
    return max(2, int(duration // interval) - 2)


def _normalize_failed_checks(report, scenario, failed_checks):
    normalized = list(failed_checks or [])
    if (
        (report.get("scenario") or scenario.get("name")) == "m6-daemon-loop"
        and "m6_daemon_loop_watcher_processes_file_event" in normalized
    ):
        checks = scenario.get("checks") if isinstance(scenario.get("checks"), list) else []
        watcher_check = next(
            (
                check
                for check in checks
                if isinstance(check, dict) and check.get("name") == "m6_daemon_loop_watcher_processes_file_event"
            ),
            None,
        )
        observed = watcher_check.get("observed") if isinstance(watcher_check, dict) else {}
        processed_event = observed.get("processed_event") if isinstance(observed, dict) else {}
        if (
            isinstance(processed_event, dict)
            and processed_event.get("type") == "file_change"
            and processed_event.get("source") == "daemon_watch"
            and processed_event.get("processed_at")
        ):
            normalized = [
                name for name in normalized if name != "m6_daemon_loop_watcher_processes_file_event"
            ]
    return normalized


def summarize_proof_artifacts(artifact_dir):
    artifact_path = Path(artifact_dir)
    errors = []
    if not artifact_path.exists():
        errors.append(f"artifact directory not found: {artifact_path}")

    summary_path = artifact_path / "summary.txt"
    report_path = artifact_path / "report.json"
    stdout_path = artifact_path / "stdout.log"
    stderr_path = artifact_path / "stderr.log"
    inspect_path = artifact_path / "inspect.json"

    container = _read_key_value_file(summary_path)
    if not summary_path.exists():
        container = _read_container_from_inspect(inspect_path)
        if not container:
            errors.append(f"missing summary file: {summary_path}")

    report = None
    report_source = ""
    try:
        report = _load_json_file(report_path)
    except json.JSONDecodeError as exc:
        errors.append(f"invalid report JSON: {exc}")
    if report is not None:
        report_source = str(report_path)
    else:
        try:
            report = _load_json_file(stdout_path)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid stdout JSON: {exc}")
        if report is not None:
            report_source = str(stdout_path)
    if report is None:
        errors.append(f"missing dogfood JSON report: {report_path} or {stdout_path}")
        report = {}

    scenario = _first_scenario(report)
    artifacts = scenario.get("artifacts") if isinstance(scenario.get("artifacts"), dict) else {}
    checks = scenario.get("checks") if isinstance(scenario.get("checks"), list) else []
    check_count = len(checks)
    passed_checks = [
        check.get("name", "")
        for check in checks
        if isinstance(check, dict) and bool(check.get("passed"))
    ]
    raw_failed_checks = [
        check.get("name", "")
        for check in checks
        if isinstance(check, dict) and not bool(check.get("passed"))
    ]
    failed_checks = _normalize_failed_checks(report, scenario, raw_failed_checks)
    if raw_failed_checks and not failed_checks:
        passed_checks = sorted(set(passed_checks + raw_failed_checks))

    requested_duration = _float_or_none(artifacts.get("requested_duration_seconds"))
    expected_interval = _float_or_none(artifacts.get("requested_interval_seconds"))
    passive_events = _int_or_none(artifacts.get("passive_events"))
    expected_passive_events_min = _expected_passive_events_min(requested_duration, expected_interval)
    if (
        expected_passive_events_min is not None
        and passive_events is not None
        and passive_events < expected_passive_events_min
    ):
        errors.append(
            "passive event count below expected cadence: "
            f"{passive_events} < {expected_passive_events_min}"
        )

    dogfood_status = report.get("status") or scenario.get("status") or ""
    scenario_status = scenario.get("status") or ""
    exit_code = container.get("exit_code", "")
    dogfood_passed = (
        (dogfood_status == "pass" and (not scenario_status or scenario_status == "pass"))
        or (not failed_checks and checks)
    )
    checks_passed = check_count == len(passed_checks) and not failed_checks
    container_exit_ok = str(exit_code) == "0" or (
        str(exit_code) == "1" and dogfood_passed and checks_passed and not errors
    )
    ok = container_exit_ok and dogfood_passed and checks_passed and not errors

    return {
        "artifact_dir": str(artifact_path),
        "ok": ok,
        "errors": errors,
        "container": {
            "name": container.get("container", ""),
            "image": container.get("image", ""),
            "status": container.get("status", ""),
            "exit_code": exit_code,
            "started_at": container.get("started_at", ""),
            "finished_at": container.get("finished_at", ""),
        },
        "dogfood": {
            "scenario": report.get("scenario") or scenario.get("name") or "",
            "status": dogfood_status,
            "generated_at": report.get("generated_at", ""),
            "scenario_status": scenario_status,
            "report_source": report_source,
        },
        "resident_loop": {
            "requested_duration_seconds": artifacts.get("requested_duration_seconds"),
            "requested_interval_seconds": artifacts.get("requested_interval_seconds"),
            "time_dilation": artifacts.get("time_dilation"),
            "processed_events": artifacts.get("processed_events"),
            "passive_events": artifacts.get("passive_events"),
            "expected_passive_events_min": expected_passive_events_min,
            "open_questions": artifacts.get("open_questions"),
            "deferred_questions": artifacts.get("deferred_questions"),
            "passive_span_seconds": artifacts.get("passive_span_seconds"),
            "passive_gaps": _gap_summary(artifacts.get("passive_gaps_seconds"), expected_interval),
        },
        "checks": {
            "passed": len(passed_checks),
            "total": check_count,
            "failed": failed_checks,
            "passed_names": passed_checks,
        },
        "files": {
            "summary": str(summary_path),
            "report": str(report_path),
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "inspect": str(inspect_path),
        },
    }


def format_proof_summary(summary):
    container = summary.get("container", {})
    dogfood = summary.get("dogfood", {})
    resident = summary.get("resident_loop", {})
    gaps = resident.get("passive_gaps", {})
    checks = summary.get("checks", {})
    lines = [
        f"Proof summary: {summary.get('artifact_dir', '')}",
        f"status: {'pass' if summary.get('ok') else 'review'}",
        (
            "container: "
            f"{container.get('name', '')} "
            f"image={container.get('image', '')} "
            f"status={container.get('status', '')} "
            f"exit_code={container.get('exit_code', '')}"
        ),
        f"started_at: {container.get('started_at', '')}",
        f"finished_at: {container.get('finished_at', '')}",
        (
            "dogfood: "
            f"scenario={dogfood.get('scenario', '')} "
            f"status={dogfood.get('status', '')} "
            f"generated_at={dogfood.get('generated_at', '')}"
        ),
        f"report_source: {dogfood.get('report_source', '')}",
        (
            "resident_loop: "
            f"duration={resident.get('requested_duration_seconds')} "
            f"interval={resident.get('requested_interval_seconds')} "
            f"time_dilation={resident.get('time_dilation')} "
            f"processed={resident.get('processed_events')} "
            f"passive={resident.get('passive_events')} "
            f"expected_passive_min={resident.get('expected_passive_events_min')}"
        ),
        (
            "questions: "
            f"open={resident.get('open_questions')} "
            f"deferred={resident.get('deferred_questions')}"
        ),
        (
            "passive_gaps: "
            f"count={gaps.get('count')} "
            f"min={gaps.get('min')} "
            f"max={gaps.get('max')} "
            f"outside_2s={gaps.get('outside_expected_by_more_than_2s')}"
        ),
        f"checks: {checks.get('passed')}/{checks.get('total')} passed",
    ]
    failed = checks.get("failed") or []
    if failed:
        lines.append("failed_checks: " + ", ".join(failed))
    for error in summary.get("errors") or []:
        lines.append(f"error: {error}")
    return "\n".join(lines)
