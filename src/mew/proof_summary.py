import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from mew.patch_draft import PATCH_BLOCKER_RECOVERY_ACTIONS


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


def _safe_rate(numerator, denominator):
    try:
        numerator = float(numerator)
        denominator = float(denominator)
        if denominator <= 0:
            return 0.0
        return numerator / denominator
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _current_git_head():
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if head.returncode == 0:
            return (head.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return ""


def _cohort_label(git_head, current_head):
    git_head = str(git_head or "").strip()
    if not git_head:
        return "unknown"
    if not str(current_head or "").strip():
        return "unknown"
    if git_head == str(current_head or ""):
        return "current_head"
    return "legacy"


def _new_m6_11_cohort_summary():
    return {
        "total_bundles": 0,
        "non_counted_bundle_count": 0,
        "non_counted_bundle_reasons": defaultdict(int),
        "bundle_type_counts": defaultdict(int),
        "blocker_code_counts": defaultdict(int),
        "relevant_bundles": 0,
        "compiler_bundles": 0,
        "off_schema_count": 0,
        "refusal_count": 0,
        "refusal_by_type": defaultdict(int),
        "dominant_bundle_type": "",
        "dominant_bundle_share": 0.0,
        "malformed_bundle_count": 0,
        "malformed_relevant_bundle_count": 0,
        "malformed_bundle_counts": defaultdict(int),
        "thresholds": {
            "off_schema_rate_max": 0.05,
            "off_schema_rate_ok": True,
            "refusal_rate_max": 0.03,
            "refusal_rate_ok": True,
            "failure_mode_concentration_max": 0.4,
            "failure_mode_concentration_ok": True,
            "malformed_relevant_bundles_ok": True,
            "has_bundles": False,
            "has_relevant_bundles": False,
        },
    }


def _finalize_m6_11_cohort_summary(cohort):
    total_bundles = int(cohort.get("total_bundles", 0))
    relevant_bundles = int(cohort.get("relevant_bundles", 0))
    compiler_bundles = int(cohort.get("compiler_bundles", 0))
    off_schema_count = int(cohort.get("off_schema_count", 0))
    refusal_count = int(cohort.get("refusal_count", 0))
    malformed_bundle_count = int(cohort.get("malformed_bundle_count", 0))
    malformed_relevant_bundle_count = int(cohort.get("malformed_relevant_bundle_count", 0))

    bundle_type_counts = defaultdict(int, cohort.get("bundle_type_counts", {}))
    dominant_bundle_type = ""
    dominant_bundle_count = 0
    if bundle_type_counts:
        dominant_bundle_type, dominant_bundle_count = max(
            bundle_type_counts.items(),
            key=lambda item: item[1],
        )
    dominant_bundle_share = _safe_rate(dominant_bundle_count, total_bundles)
    off_schema_rate = _safe_rate(off_schema_count, compiler_bundles)
    refusal_rate = _safe_rate(refusal_count, total_bundles)
    dominant_share_ok = total_bundles == 0 or dominant_bundle_share <= 0.4
    malformed_relevant_ok = malformed_relevant_bundle_count == 0

    return {
        "total_bundles": total_bundles,
        "non_counted_bundle_count": int(cohort.get("non_counted_bundle_count", 0)),
        "non_counted_bundle_reasons": dict(
            defaultdict(int, cohort.get("non_counted_bundle_reasons", {}))
        ),
        "bundle_type_counts": dict(bundle_type_counts),
        "blocker_code_counts": dict(
            defaultdict(int, cohort.get("blocker_code_counts", {}))
        ),
        "relevant_bundles": relevant_bundles,
        "compiler_bundles": compiler_bundles,
        "off_schema_count": off_schema_count,
        "off_schema_rate": off_schema_rate,
        "off_schema_denominator": compiler_bundles,
        "refusal_count": refusal_count,
        "refusal_rate": refusal_rate,
        "refusal_by_type": dict(defaultdict(int, cohort.get("refusal_by_type", {}))),
        "dominant_bundle_type": dominant_bundle_type,
        "dominant_bundle_share": dominant_bundle_share,
        "malformed_bundle_count": malformed_bundle_count,
        "malformed_relevant_bundle_count": malformed_relevant_bundle_count,
        "malformed_bundle_counts": dict(
            defaultdict(int, cohort.get("malformed_bundle_counts", {}))
        ),
        "thresholds": {
            "off_schema_rate_max": 0.05,
            "off_schema_rate_ok": off_schema_rate <= 0.05,
            "refusal_rate_max": 0.03,
            "refusal_rate_ok": refusal_rate <= 0.03,
            "failure_mode_concentration_max": 0.4,
            "failure_mode_concentration_ok": dominant_share_ok,
            "malformed_relevant_bundles_ok": malformed_relevant_ok,
            "has_bundles": total_bundles > 0,
            "has_relevant_bundles": relevant_bundles > 0,
        },
    }

def _coerce_calibration_counted(value, default=True):
    return value if isinstance(value, bool) else default


def _read_validator_result(metadata_path, metadata):
    files = metadata.get("files") if isinstance(metadata.get("files"), dict) else {}
    validator_file = files.get("validator_result")
    validator_path = metadata_path.parent / (
        validator_file if isinstance(validator_file, str) else "validator_result.json"
    )
    try:
        validator = _load_json_file(validator_path)
    except json.JSONDecodeError:
        return None
    if not isinstance(validator, dict):
        return None
    return validator


def _calibration_compiler_type(code):
    code = str(code or "").strip()
    if not code:
        return "patch_draft_compiler.other"
    if code == "model_returned_non_schema":
        return "patch_draft_compiler.off_schema"
    if code == "model_returned_refusal":
        return "patch_draft_compiler.refusal"
    if code in PATCH_BLOCKER_RECOVERY_ACTIONS:
        return f"patch_draft_compiler.{code}"
    return "patch_draft_compiler.other"


def _calibration_model_failure_type(failure_code):
    code = str(failure_code or "").strip()
    if code == "model_refused":
        return "work-loop-model-failure.model_refused"
    if code:
        return f"work-loop-model-failure.{code}"
    return "work-loop-model-failure.other"


def _summarize_patch_draft_compiler_bundle(metadata_path):
    summary = {
        "bundle_type": "patch_draft_compiler",
        "calibration_bundle_type": "patch_draft_compiler.other",
        "calibration_counted": True,
        "calibration_exclusion_reason": "",
        "off_schema": False,
        "refusal": False,
        "git_head": "",
        "bucket_tag": "",
        "blocker_code": "",
        "errors": [],
    }
    try:
        metadata = _load_json_file(metadata_path)
    except json.JSONDecodeError as exc:
        summary["errors"].append(f"invalid compiler metadata JSON: {metadata_path}: {exc}")
        return summary

    if not isinstance(metadata, dict):
        summary["errors"].append(f"invalid compiler metadata payload: {metadata_path}")
        return summary

    summary["calibration_counted"] = _coerce_calibration_counted(
        metadata.get("calibration_counted"), default=True
    )
    summary["calibration_exclusion_reason"] = str(
        metadata.get("calibration_exclusion_reason") or ""
    )

    bundle_name = metadata.get("bundle")
    if isinstance(bundle_name, str) and bundle_name.strip():
        summary["bundle_type"] = bundle_name.strip()
    summary["git_head"] = str(metadata.get("git_head") or "")
    summary["bucket_tag"] = str(metadata.get("bucket_tag") or "")
    summary["blocker_code"] = str(metadata.get("blocker_code") or "")

    validator = _read_validator_result(metadata_path, metadata)
    if not isinstance(validator, dict):
        summary["errors"].append(f"missing or invalid validator_result JSON for {metadata_path}")
        return summary
    code = validator.get("code")
    if code is None:
        validator_kind = str(validator.get("kind") or "").strip()
        validator_status = str(validator.get("status") or "").strip()
        if not (validator_kind == "patch_draft" and validator_status == "validated"):
            summary["errors"].append(
                f"missing or invalid validator_result JSON for {metadata_path}"
            )
            return summary
        code = ""
    code = str(code or "").strip()
    summary["calibration_bundle_type"] = _calibration_compiler_type(code)
    summary["off_schema"] = code == "model_returned_non_schema"
    summary["refusal"] = code == "model_returned_refusal"
    return summary


def _summarize_model_failure_bundle(report_path):
    summary = {
        "bundle_type": "work-loop-model-failure",
        "calibration_bundle_type": "work-loop-model-failure.other",
        "calibration_counted": True,
        "calibration_exclusion_reason": "",
        "off_schema": False,
        "refusal": False,
        "git_head": "",
        "bucket_tag": "",
        "blocker_code": "",
        "errors": [],
    }
    try:
        report = _load_json_file(report_path)
    except json.JSONDecodeError as exc:
        summary["errors"].append(f"invalid model-failure report JSON: {report_path}: {exc}")
        return summary

    if not isinstance(report, dict):
        summary["errors"].append(f"invalid model-failure report payload: {report_path}")
        return summary

    bundle_name = report.get("bundle")
    if isinstance(bundle_name, str) and bundle_name.strip():
        summary["bundle_type"] = bundle_name.strip()
    summary["calibration_counted"] = _coerce_calibration_counted(
        report.get("calibration_counted"), default=True
    )
    summary["calibration_exclusion_reason"] = str(
        report.get("calibration_exclusion_reason") or ""
    )
    summary["git_head"] = str(report.get("git_head") or "")
    summary["bucket_tag"] = str(report.get("bucket_tag") or "")
    summary["blocker_code"] = str(report.get("blocker_code") or "")
    failure = report.get("failure") if isinstance(report.get("failure"), dict) else {}
    summary["calibration_bundle_type"] = _calibration_model_failure_type(failure.get("code"))
    summary["refusal"] = str(failure.get("code") or "") == "model_refused"
    return summary


def _m6_11_cohort_targets(cohort_summaries, bundle_summary, current_head, measurement_head):
    cohort_name = _cohort_label(bundle_summary.get("git_head"), current_head)
    targets = [cohort_summaries[cohort_name]]
    bundle_git_head = str(bundle_summary.get("git_head") or "").strip()
    if measurement_head and bundle_git_head == measurement_head:
        targets.append(cohort_summaries["measurement_head"])
    return targets


def _m6_12_default_ledger_path(_artifact_dir):
    return Path("proof-artifacts/m6_11_calibration_ledger.jsonl")


def _load_m6_12_closeout_index(closeout_index):
    if not closeout_index:
        return None
    path = Path(closeout_index)
    if not path.exists():
        raise FileNotFoundError(f"M6.12 closeout index not found: {path}")
    try:
        payload = _load_json_file(path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid M6.12 closeout index JSON: {path}: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError(f"invalid M6.12 closeout index: {path}: expected list")
    index = {}
    required = {"original_path", "export_path", "sha256", "size_bytes", "exported_at"}
    for entry_number, entry in enumerate(payload, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"invalid M6.12 closeout index entry #{entry_number}: expected object")
        missing = sorted(required - set(entry))
        if missing:
            raise ValueError(
                f"invalid M6.12 closeout index entry #{entry_number}: missing {', '.join(missing)}"
            )
        original_path = str(entry.get("original_path") or "").strip()
        if not original_path:
            raise ValueError(f"invalid M6.12 closeout index entry #{entry_number}: empty original_path")
        index[original_path] = entry
    return index


def _m6_12_row_ref(row):
    return f"ledger:#{row.line_number}"


def _m6_12_bundle_ref(row):
    value = row.field("replay_bundle_path")
    return str(value or "").strip()


def _m6_12_subsystem_tag(row):
    for field_name in ("subsystem_tag", "subsystem"):
        value = row.text_field(field_name).strip()
        if value:
            return value
    scope_files = row.field("scope_files")
    if isinstance(scope_files, list):
        for value in scope_files:
            path = str(value or "").strip()
            if path.startswith("src/mew/"):
                return Path(path).stem
    return "unknown"


def _resolve_m6_12_bundle_path(artifact_dir, replay_bundle_path, closeout_index=None):
    replay_bundle_path = str(replay_bundle_path or "").strip()
    if not replay_bundle_path:
        return "", True, ""
    artifact_path = Path(artifact_dir)
    if closeout_index is not None:
        entry = closeout_index.get(replay_bundle_path)
        if not isinstance(entry, dict):
            return "", False, "closeout_index_miss"
        candidate = artifact_path / str(entry.get("export_path") or "")
        if not candidate.is_file():
            return str(candidate), False, "closeout_export_missing"
        expected_sha = str(entry.get("sha256") or "").strip()
        if expected_sha:
            actual_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                return str(candidate), False, "closeout_export_sha_mismatch"
        return str(candidate), True, ""
    else:
        candidate_text = replay_bundle_path
        artifact_text = str(artifact_path)
        prefixes = []
        if artifact_text:
            prefixes.append(artifact_text.rstrip("/") + "/")
        prefixes.append(".mew/replays/work-loop/")
        for prefix in prefixes:
            if candidate_text.startswith(prefix):
                candidate_text = candidate_text[len(prefix):]
                break
        candidate = Path(replay_bundle_path) if Path(replay_bundle_path).is_absolute() else artifact_path / candidate_text
        if not candidate.is_file():
            return str(candidate), False, "precloseout_missing"
        return str(candidate), True, ""


def _summarize_m6_12_archetypes(classified_rows):
    rows_by_archetype = defaultdict(list)
    for classified in classified_rows:
        rows_by_archetype[classified.archetype].append(classified)

    from mew.calibration_report import ARCHETYPE_PRIORITY

    active = []
    for index, archetype in enumerate(ARCHETYPE_PRIORITY, start=1):
        items = rows_by_archetype.get(archetype, [])
        row_refs = [_m6_12_row_ref(item.row) for item in items]
        bundle_refs = sorted(
            {
                _m6_12_bundle_ref(item.row)
                for item in items
                if _m6_12_bundle_ref(item.row)
            }
        )
        active.append(
            {
                "label": archetype,
                "cohort": "all",
                "counted": len(items),
                "evidence_priority": index,
                "row_refs": row_refs,
                "bundle_refs": bundle_refs,
            }
        )
    return active


def _m6_12_calibration_rates_from_bundles(bundle_paths):
    total_bundles = 0
    compiler_bundles = 0
    off_schema_count = 0
    refusal_count = 0
    malformed_relevant_bundle_count = 0
    bundle_type_counts = defaultdict(int)

    for bundle_path in bundle_paths:
        path = Path(bundle_path)
        if path.name == "replay_metadata.json":
            summary = _summarize_patch_draft_compiler_bundle(path)
            expected_bundle_type = "patch_draft_compiler"
        elif path.name == "report.json":
            summary = _summarize_model_failure_bundle(path)
            expected_bundle_type = "work-loop-model-failure"
        else:
            malformed_relevant_bundle_count += 1
            continue

        if summary.get("bundle_type") != expected_bundle_type:
            malformed_relevant_bundle_count += 1
            continue
        if not _coerce_calibration_counted(summary.get("calibration_counted"), default=True):
            continue

        if summary.get("errors"):
            malformed_relevant_bundle_count += 1
            continue

        calibration_bundle_type = summary.get("calibration_bundle_type") or f"{expected_bundle_type}.other"
        total_bundles += 1
        bundle_type_counts[calibration_bundle_type] += 1
        if expected_bundle_type == "patch_draft_compiler":
            compiler_bundles += 1
        if summary.get("off_schema"):
            off_schema_count += 1
        if summary.get("refusal"):
            refusal_count += 1

    dominant_bundle_type = ""
    dominant_bundle_share = 0.0
    if bundle_type_counts:
        dominant_bundle_type, dominant_count = max(
            bundle_type_counts.items(),
            key=lambda item: item[1],
        )
        dominant_bundle_share = _safe_rate(dominant_count, total_bundles)

    return {
        "source": "resolved_ledger_replay_bundles",
        "total_bundles": total_bundles,
        "off_schema_rate": _safe_rate(off_schema_count, compiler_bundles),
        "off_schema_count": off_schema_count,
        "off_schema_denominator": compiler_bundles,
        "refusal_rate": _safe_rate(refusal_count, total_bundles),
        "refusal_count": refusal_count,
        "dominant_bundle_type": dominant_bundle_type,
        "dominant_bundle_share": dominant_bundle_share,
        "malformed_relevant_bundle_count": malformed_relevant_bundle_count,
    }


def summarize_m6_12_report(artifact_dir, ledger=None, closeout_index=None, measurement_head=None):
    from mew.calibration_ledger import load_calibration_ledger
    from mew.calibration_report import (
        ARCHETYPE_PRIORITY,
        CLASSIFIER_VERSION,
        classify_calibration_rows,
        summarize_calibration_rows,
    )

    artifact_path = Path(artifact_dir)
    measurement_head = str(measurement_head or "").strip()
    current_head = _current_git_head()
    ledger_path = Path(ledger) if ledger else _m6_12_default_ledger_path(artifact_path)
    closeout_payload = _load_m6_12_closeout_index(closeout_index) if closeout_index else None
    rows = load_calibration_ledger(ledger_path)
    mode = "post_closeout" if closeout_payload is not None else "pre_closeout"
    classifier_summary = summarize_calibration_rows(rows)
    classified_rows = classify_calibration_rows(rows)
    blocker_code_counts = defaultdict(int)
    countedness_counts = defaultdict(int)
    reviewer_decision_counts = defaultdict(int)
    non_counted_reason_counts = defaultdict(int)
    non_counted_reason_rows = defaultdict(list)
    non_counted_countedness_rows = defaultdict(list)
    cohort_summaries = defaultdict(
        lambda: {"ledger_rows": 0, "counted_rows": 0, "non_counted_rows": 0}
    )
    subsystem_summaries = defaultdict(
        lambda: {"counted": 0, "archetypes": defaultdict(int), "heads": set(), "row_refs": []}
    )
    missing_row_refs = []
    referenced = 0
    resolved = 0
    resolved_bundle_paths = []
    counted_rows = 0
    non_counted_rows = 0

    for row in rows:
        counted = _coerce_calibration_counted(row.field("counted"), default=True)
        if counted:
            counted_rows += 1
        else:
            non_counted_rows += 1
            reason = row.text_field("non_counted_reason").strip() or "unspecified"
            non_counted_reason_counts[reason] += 1
            non_counted_reason_rows[reason].append(_m6_12_row_ref(row))
        git_head = row.text_field("head").strip() or row.text_field("git_head").strip()
        cohort_names = [_cohort_label(git_head, current_head)]
        if measurement_head and git_head == measurement_head:
            cohort_names.append("measurement_head")
        for cohort_name in cohort_names:
            cohort = cohort_summaries[cohort_name]
            cohort["ledger_rows"] += 1
            if counted:
                cohort["counted_rows"] += 1
            else:
                cohort["non_counted_rows"] += 1
        blocker_code = row.text_field("blocker_code").strip()
        if blocker_code:
            blocker_code_counts[blocker_code] += 1
        countedness = row.text_field("countedness").strip()
        if countedness:
            countedness_counts[countedness] += 1
            if not counted:
                non_counted_countedness_rows[countedness].append(_m6_12_row_ref(row))
        reviewer_decision = row.text_field("reviewer_decision").strip()
        if reviewer_decision:
            reviewer_decision_counts[reviewer_decision] += 1
        replay_bundle_path = _m6_12_bundle_ref(row)
        if replay_bundle_path:
            referenced += 1
            candidate, bundle_resolved, missing_reason = _resolve_m6_12_bundle_path(
                artifact_path,
                replay_bundle_path,
                closeout_index=closeout_payload,
            )
            if bundle_resolved:
                resolved += 1
                resolved_bundle_paths.append(candidate)
            else:
                missing_row_refs.append(
                    {"row_ref": _m6_12_row_ref(row), "reason": missing_reason}
                )

    for classified in classified_rows:
        row = classified.row
        if not _coerce_calibration_counted(row.field("counted"), default=True):
            continue
        subsystem = subsystem_summaries[_m6_12_subsystem_tag(row)]
        subsystem["counted"] += 1
        subsystem["archetypes"][classified.archetype] += 1
        head = row.text_field("head").strip() or row.text_field("git_head").strip()
        if head:
            subsystem["heads"].add(head)
        subsystem["row_refs"].append(_m6_12_row_ref(row))

    missing = len(missing_row_refs)
    archetypes_active = _summarize_m6_12_archetypes(classified_rows)
    hardest_archetype = next(
        (item["label"] for item in archetypes_active if item.get("counted", 0)),
        "",
    )
    errors = []
    if missing:
        errors.append(f"M6.12 missing replay bundles: {missing}")
    warnings = [
        f"missing_bundle {item['row_ref']} reason={item['reason']}"
        for item in missing_row_refs
    ]
    warnings.extend(
        f"unclassified_v0 {_m6_12_row_ref(item.row)}"
        for item in classified_rows
        if item.archetype == "unclassified_v0"
    )

    bundle_provenance = {
        "mode": mode,
        "root": str(artifact_path),
        "closeout_index": str(closeout_index) if closeout_index else None,
        "referenced": referenced,
        "resolved": resolved,
        "missing": missing,
        "missing_row_refs": missing_row_refs,
    }
    canonical = {
        "mode": mode,
        "artifact_dir": str(artifact_path),
        "ledger_path": str(ledger_path),
        "ledger_rows": len(rows),
        "current_head": current_head,
        "measurement_head": measurement_head,
        "cohorts": {
            "all": {
                "ledger_rows": len(rows),
                "counted_rows": counted_rows,
                "non_counted_rows": non_counted_rows,
            },
            **{key: dict(value) for key, value in sorted(cohort_summaries.items())},
        },
        "bundles": {
            "referenced": referenced,
            "resolved": resolved,
            "missing": missing,
        },
        "counted_rows": counted_rows,
        "non_counted_rows": non_counted_rows,
        "bundle_provenance": bundle_provenance,
        "blocker_code_counts": dict(blocker_code_counts),
        "countedness_counts": dict(countedness_counts),
        "reviewer_decision_counts": dict(reviewer_decision_counts),
        "non_counted_reason_counts": dict(non_counted_reason_counts),
    }
    calibration_rates = None
    if not missing:
        calibration_rates = _m6_12_calibration_rates_from_bundles(resolved_bundle_paths)
    subsystem_rows = []
    for label, data in sorted(
        subsystem_summaries.items(),
        key=lambda item: (-item[1]["counted"], item[0]),
    ):
        top_archetypes = [
            {"label": archetype, "counted": count}
            for archetype, count in sorted(
                data["archetypes"].items(),
                key=lambda item: (-item[1], item[0]),
            )[:2]
        ]
        subsystem_rows.append(
            {
                "label": label,
                "counted": data["counted"],
                "heads_seen": len(data["heads"]),
                "top_archetypes": top_archetypes,
                "row_refs": data["row_refs"][:8],
            }
        )
    non_counted_concentration = {
        "reasons": [
            {"label": reason, "count": count, "row_refs": non_counted_reason_rows[reason][:8]}
            for reason, count in sorted(
                non_counted_reason_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:8]
        ],
        "countedness": [
            {"label": countedness, "count": len(row_refs), "row_refs": row_refs[:8]}
            for countedness, row_refs in sorted(
                non_counted_countedness_rows.items(),
                key=lambda item: (-len(item[1]), item[0]),
            )[:8]
        ],
    }
    derived = {
        "classifier_version": CLASSIFIER_VERSION,
        "classifier_priority": list(ARCHETYPE_PRIORITY),
        "archetypes_active": archetypes_active,
        "archetypes_reserved_seen": [],
        "archetype_counts": dict(classifier_summary.counts),
        "drift_axes": [
            {"label": "task_frontier_drift", "count": 0, "reserved": True},
            {"label": "context_session_drift", "count": 0, "reserved": True},
            {"label": "replay_tool_drift", "count": 0, "reserved": True},
            {"label": "approval_review_drift", "count": 0, "reserved": True},
            {"label": "ui_channel_drift", "count": 0, "reserved": True},
        ],
        "subsystems": subsystem_rows,
        "recurrence": [
            {
                "subsystem": item["label"],
                "heads_seen": item["heads_seen"],
                "top_archetypes": item["top_archetypes"],
            }
            for item in subsystem_rows
        ],
        "comparator": {},
        "calibration_rates": calibration_rates,
        "non_counted_concentration": non_counted_concentration,
        "hardest_archetype": hardest_archetype,
        "has_missing_bundles": missing > 0,
    }
    return {
        "ok": missing == 0,
        "kind": "m6_12_report",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "subcommand_mode": "m6_12_report",
        "classifier_version": CLASSIFIER_VERSION,
        "errors": errors,
        "canonical": canonical,
        "derived": derived,
        "warnings": warnings,
    }


def format_m6_12_report(summary):
    canonical = summary.get("canonical") if isinstance(summary, dict) else {}
    derived = summary.get("derived") if isinstance(summary, dict) else {}
    provenance = canonical.get("bundle_provenance") if isinstance(canonical, dict) else {}

    def _format_top_archetypes(item):
        return ", ".join(
            f"{top.get('label')}({top.get('counted', 0)})"
            for top in item.get("top_archetypes", [])
            if isinstance(top, dict)
        )

    active = [
        f"{item.get('label')}={item.get('counted', 0)}"
        for item in derived.get("archetypes_active") or []
        if isinstance(item, dict) and item.get("counted", 0)
    ]
    lines = [
        "M6.12 proof summary",
        f"subcommand_mode: {summary.get('subcommand_mode', '')}",
        f"classifier_version: {summary.get('classifier_version', '')}",
        f"mode: {canonical.get('mode', '')}",
        f"current_head: {canonical.get('current_head', '')}",
        f"measurement_head: {canonical.get('measurement_head', '')}",
        f"ledger: {canonical.get('ledger_path', '')}",
        f"ledger_rows: {canonical.get('ledger_rows', 0)}",
        f"counted_rows: {canonical.get('counted_rows', 0)}",
        f"non_counted_rows: {canonical.get('non_counted_rows', 0)}",
        f"bundle_provenance: mode={provenance.get('mode', '')} root={provenance.get('root', '')} referenced={provenance.get('referenced', 0)} resolved={provenance.get('resolved', 0)} missing={provenance.get('missing', 0)}",
        "summary:",
        *[
            f"  {cohort} counted={data.get('counted_rows', 0)} non_counted={data.get('non_counted_rows', 0)}"
            for cohort, data in sorted((canonical.get("cohorts") or {}).items())
            if isinstance(data, dict)
        ],
        "subsystem_heatmap:",
        *[
            (
                f"  {item.get('label')} counted={item.get('counted', 0)} "
                f"top={_format_top_archetypes(item)} "
                f"rows={', '.join(item.get('row_refs', [])[:3])}"
            )
            for item in derived.get("subsystems") or []
            if isinstance(item, dict)
        ][:8],
        "recurrence:",
        *[
            f"  {item.get('subsystem')} heads_seen={item.get('heads_seen', 0)} top_archetypes={', '.join(top.get('label', '') for top in item.get('top_archetypes', []))}"
            for item in derived.get("recurrence") or []
            if isinstance(item, dict)
        ][:8],
        "drift:",
        *[
            f"  {item.get('label')} count={item.get('count', 0)} (reserved)"
            for item in derived.get("drift_axes") or []
            if isinstance(item, dict)
        ],
        "calibration_rates (bundle-derived):",
        *(
            ["  suppressed: missing referenced bundles"]
            if derived.get("calibration_rates") is None
            else [
                f"  off_schema={derived.get('calibration_rates', {}).get('off_schema_rate')} ({derived.get('calibration_rates', {}).get('off_schema_count')}/{derived.get('calibration_rates', {}).get('off_schema_denominator')})",
                f"  refusal={derived.get('calibration_rates', {}).get('refusal_rate')} ({derived.get('calibration_rates', {}).get('refusal_count')}/{derived.get('calibration_rates', {}).get('total_bundles')})",
                f"  dominant_share={derived.get('calibration_rates', {}).get('dominant_bundle_share')} ({derived.get('calibration_rates', {}).get('dominant_bundle_type')})",
                f"  malformed_relevant={derived.get('calibration_rates', {}).get('malformed_relevant_bundle_count')}",
            ]
        ),
        "non_counted_concentration:",
        *[
            f"  reason {item.get('label')} x{item.get('count', 0)} rows={', '.join(item.get('row_refs', [])[:3])}"
            for item in (derived.get("non_counted_concentration") or {}).get("reasons", [])
        ],
        *[
            f"  countedness {item.get('label')} x{item.get('count', 0)} rows={', '.join(item.get('row_refs', [])[:3])}"
            for item in (derived.get("non_counted_concentration") or {}).get("countedness", [])
        ],
        f"classifier_priority: {', '.join(derived.get('classifier_priority') or [])}",
        f"hardest_archetype: {derived.get('hardest_archetype', '')}",
        f"archetypes_active: {', '.join(active)}",
        "warnings:",
        *([f"  {warning}" for warning in summary.get("warnings") or []] or ["  none"]),
    ]
    return "\n".join(lines)


def summarize_m6_11_replay_calibration(replay_root, measurement_head=None):
    replay_path = Path(replay_root)
    measurement_head = str(measurement_head or "").strip()
    errors = []
    if not replay_path.exists():
        errors.append(f"replay root not found: {replay_path}")

    bundle_type_counts = defaultdict(int)
    malformed_bundle_counts = defaultdict(int)
    malformed_bundle_count = 0
    malformed_relevant_bundle_count = 0
    total_bundles = 0
    off_schema_count = 0
    refusal_count = 0
    blocker_code_counts = defaultdict(int)
    dominant_bundle_type = ""
    refusal_by_type = defaultdict(int)
    compiler_bundles = 0
    relevant_bundles = 0
    non_counted_bundle_count = 0
    non_counted_bundle_reasons = defaultdict(int)

    cohort_summaries = {
        "current_head": _new_m6_11_cohort_summary(),
        "legacy": _new_m6_11_cohort_summary(),
        "unknown": _new_m6_11_cohort_summary(),
    }
    if measurement_head:
        cohort_summaries["measurement_head"] = _new_m6_11_cohort_summary()
    current_head = _current_git_head()

    for metadata_path in sorted(replay_path.rglob("replay_metadata.json")):
        if not metadata_path.is_file():
            continue
        bundle_summary = _summarize_patch_draft_compiler_bundle(metadata_path)
        bundle_type = bundle_summary.get("bundle_type") or "patch_draft_compiler"
        cohort_targets = _m6_11_cohort_targets(
            cohort_summaries,
            bundle_summary,
            current_head,
            measurement_head,
        )
        if bundle_type != "patch_draft_compiler":
            malformed_bundle_counts[f"ignored_{bundle_type}"] += 1
            malformed_bundle_count += 1
            for cohort_summary in cohort_targets:
                cohort_summary["malformed_bundle_count"] += 1
                cohort_summary["malformed_bundle_counts"][f"ignored_{bundle_type}"] += 1
            continue
        calibration_counted = _coerce_calibration_counted(
            bundle_summary.get("calibration_counted"),
            default=True,
        )
        if not calibration_counted:
            reason = str(bundle_summary.get("calibration_exclusion_reason") or "").strip()
            if not reason:
                reason = "unspecified"
            non_counted_bundle_count += 1
            non_counted_bundle_reasons[reason] += 1
            for cohort_summary in cohort_targets:
                cohort_summary["non_counted_bundle_count"] += 1
                cohort_summary["non_counted_bundle_reasons"][reason] += 1
            continue

        if bundle_summary.get("errors"):
            malformed_bundle_counts[bundle_type] += 1
            malformed_bundle_count += 1
            for cohort_summary in cohort_targets:
                cohort_summary["malformed_bundle_count"] += 1
                cohort_summary["malformed_bundle_counts"][bundle_type] += 1
            for error in bundle_summary.get("errors") or []:
                errors.append(error)

        relevant_bundles += 1
        for cohort_summary in cohort_targets:
            cohort_summary["relevant_bundles"] += 1
        if bundle_summary.get("errors"):
            malformed_relevant_bundle_count += 1
            for cohort_summary in cohort_targets:
                cohort_summary["malformed_relevant_bundle_count"] += 1
            continue

        calibration_bundle_type = bundle_summary.get("calibration_bundle_type") or "patch_draft_compiler.other"
        total_bundles += 1
        compiler_bundles += 1
        bundle_type_counts[calibration_bundle_type] += 1
        for cohort_summary in cohort_targets:
            cohort_summary["total_bundles"] += 1
            cohort_summary["compiler_bundles"] += 1
            cohort_summary["bundle_type_counts"][calibration_bundle_type] += 1
        if bundle_summary.get("off_schema"):
            off_schema_count += 1
            for cohort_summary in cohort_targets:
                cohort_summary["off_schema_count"] += 1
        if bundle_summary.get("refusal"):
            refusal_count += 1
            refusal_by_type[calibration_bundle_type] += 1
            for cohort_summary in cohort_targets:
                cohort_summary["refusal_count"] += 1
                cohort_summary["refusal_by_type"][calibration_bundle_type] += 1
        blocker_code = str(bundle_summary.get("blocker_code") or "").strip()
        if blocker_code:
            blocker_code_counts[blocker_code] += 1
            for cohort_summary in cohort_targets:
                cohort_summary["blocker_code_counts"][blocker_code] += 1

    for report_path in sorted(replay_path.rglob("report.json")):
        if not report_path.is_file():
            continue
        bundle_summary = _summarize_model_failure_bundle(report_path)
        bundle_type = bundle_summary.get("bundle_type") or "work-loop-model-failure"
        cohort_targets = _m6_11_cohort_targets(
            cohort_summaries,
            bundle_summary,
            current_head,
            measurement_head,
        )
        if bundle_type != "work-loop-model-failure":
            malformed_bundle_counts[f"ignored_{bundle_type}"] += 1
            malformed_bundle_count += 1
            for cohort_summary in cohort_targets:
                cohort_summary["malformed_bundle_count"] += 1
                cohort_summary["malformed_bundle_counts"][f"ignored_{bundle_type}"] += 1
            continue
        calibration_counted = _coerce_calibration_counted(
            bundle_summary.get("calibration_counted"),
            default=True,
        )
        if not calibration_counted:
            reason = str(bundle_summary.get("calibration_exclusion_reason") or "").strip()
            if not reason:
                reason = "unspecified"
            non_counted_bundle_count += 1
            non_counted_bundle_reasons[reason] += 1
            for cohort_summary in cohort_targets:
                cohort_summary["non_counted_bundle_count"] += 1
                cohort_summary["non_counted_bundle_reasons"][reason] += 1
            continue
        relevant_bundles += 1
        for cohort_summary in cohort_targets:
            cohort_summary["relevant_bundles"] += 1
        if bundle_summary.get("errors"):
            malformed_bundle_counts[bundle_type] += 1
            malformed_bundle_count += 1
            malformed_relevant_bundle_count += 1
            for cohort_summary in cohort_targets:
                cohort_summary["malformed_bundle_count"] += 1
                cohort_summary["malformed_relevant_bundle_count"] += 1
                cohort_summary["malformed_bundle_counts"][bundle_type] += 1
            for error in bundle_summary.get("errors") or []:
                errors.append(error)
            continue
        calibration_bundle_type = bundle_summary.get("calibration_bundle_type") or "work-loop-model-failure.other"
        total_bundles += 1
        bundle_type_counts[calibration_bundle_type] += 1
        for cohort_summary in cohort_targets:
            cohort_summary["total_bundles"] += 1
            cohort_summary["bundle_type_counts"][calibration_bundle_type] += 1
        if bundle_summary.get("refusal"):
            refusal_count += 1
            refusal_by_type[calibration_bundle_type] += 1
            for cohort_summary in cohort_targets:
                cohort_summary["refusal_count"] += 1
                cohort_summary["refusal_by_type"][calibration_bundle_type] += 1
        blocker_code = str(bundle_summary.get("blocker_code") or "").strip()
        if blocker_code:
            blocker_code_counts[blocker_code] += 1
            for cohort_summary in cohort_targets:
                cohort_summary["blocker_code_counts"][blocker_code] += 1
        for error in bundle_summary.get("errors") or []:
            errors.append(error)

    dominant_bundle_count = 0
    dominant_bundle_share = 0.0
    if bundle_type_counts:
        dominant_bundle_type, dominant_bundle_count = max(
            bundle_type_counts.items(),
            key=lambda item: item[1],
        )
        dominant_bundle_share = _safe_rate(dominant_bundle_count, total_bundles)
    off_schema_rate = _safe_rate(off_schema_count, compiler_bundles)
    refusal_rate = _safe_rate(refusal_count, total_bundles)

    dominant_share_ok = total_bundles == 0 or dominant_bundle_share <= 0.4
    malformed_bundle_ok = malformed_relevant_bundle_count == 0

    thresholds = {
        "off_schema_rate_max": 0.05,
        "off_schema_rate_ok": off_schema_rate <= 0.05,
        "refusal_rate_max": 0.03,
        "refusal_rate_ok": refusal_rate <= 0.03,
        "failure_mode_concentration_max": 0.4,
        "failure_mode_concentration_ok": dominant_share_ok,
        "malformed_relevant_bundles_ok": malformed_bundle_ok,
        "has_bundles": total_bundles > 0,
        "has_relevant_bundles": relevant_bundles > 0,
    }

    thresholds_pass = all(
        (
            thresholds["off_schema_rate_ok"],
            thresholds["refusal_rate_ok"],
            thresholds["failure_mode_concentration_ok"],
            thresholds["malformed_relevant_bundles_ok"],
            thresholds["has_bundles"],
        )
    )

    cohorts = {
        "current_head": _finalize_m6_11_cohort_summary(
            cohort_summaries["current_head"]
        ),
        "legacy": _finalize_m6_11_cohort_summary(cohort_summaries["legacy"]),
        "unknown": _finalize_m6_11_cohort_summary(cohort_summaries["unknown"]),
    }
    if measurement_head:
        cohorts["measurement_head"] = _finalize_m6_11_cohort_summary(
            cohort_summaries["measurement_head"]
        )

    summary = {
        "artifact_dir": str(replay_path),
        "mode": "m6_11_phase2_calibration",
        "ok": thresholds_pass,
        "errors": errors,
        "calibration": {
            "total_bundles": total_bundles,
            "non_counted_bundle_count": non_counted_bundle_count,
            "non_counted_bundle_reasons": dict(non_counted_bundle_reasons),
            "bundle_type_counts": dict(bundle_type_counts),
            "relevant_bundles": relevant_bundles,
            "compiler_bundles": compiler_bundles,
            "off_schema_count": off_schema_count,
            "off_schema_rate": off_schema_rate,
            "off_schema_denominator": compiler_bundles,
            "refusal_count": refusal_count,
            "refusal_rate": refusal_rate,
            "refusal_by_type": dict(refusal_by_type),
            "blocker_code_counts": dict(blocker_code_counts),
            "dominant_bundle_type": dominant_bundle_type,
            "dominant_bundle_share": dominant_bundle_share,
            "malformed_bundle_count": malformed_bundle_count,
            "malformed_relevant_bundle_count": malformed_relevant_bundle_count,
            "malformed_bundle_counts": dict(malformed_bundle_counts),
            "cohorts": cohorts,
            "thresholds": thresholds,
        },
    }
    if measurement_head:
        summary["measurement_head"] = measurement_head
    return summary


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
    calibration = summary.get("calibration")
    if calibration:
        refusal_by_type = calibration.get("refusal_by_type") or {}
        refusal_breakdown = ", ".join(
            f"{key}={value}" for key, value in sorted(refusal_by_type.items())
        )
        non_counted_reasons = calibration.get("non_counted_bundle_reasons") or {}
        non_counted_breakdown = ", ".join(
            f"{key}={value}" for key, value in sorted(non_counted_reasons.items())
        )
        blocker_code_by_type = calibration.get("blocker_code_counts") or {}
        blocker_code_breakdown = ", ".join(
            f"{key}={value}" for key, value in sorted(blocker_code_by_type.items())
        )
        rates = [
            (
                "off_schema="
                f"{calibration.get('off_schema_rate', 0.0):.4f}"
                f" ({calibration.get('off_schema_count', 0)}/{calibration.get('off_schema_denominator', 0)})"
            ),
            (
                "refusal="
                f"{calibration.get('refusal_rate', 0.0):.4f}"
                f" ({calibration.get('refusal_count', 0)}/{calibration.get('total_bundles', 0)})"
            ),
            f"blocker_code_breakdown={blocker_code_breakdown or 'none'}",
            f"dominant_share={calibration.get('dominant_bundle_share', 0.0):.4f}",
            f"refusal_breakdown={refusal_breakdown or 'none'}",
        ]
        bundle_counts = calibration.get("bundle_type_counts") or {}
        counts = ", ".join(
            f"{key}={value}"
            for key, value in sorted(bundle_counts.items())
        )
        lines = [
            f"Proof summary: {summary.get('artifact_dir', '')}",
            f"status: {'pass' if summary.get('ok') else 'review'}",
            "mode: m6.11 phase2/phase3 calibration",
            f"calibration_bundles: total={calibration.get('total_bundles', 0)}",
            f"calibration_non_counted_bundles: total={calibration.get('non_counted_bundle_count', 0)} reasons={non_counted_breakdown or 'none'}",
            f"calibration_bundle_types: {counts or 'none'}",
            f"calibration_rates: {', '.join(rates)}",
            (
            f"calibration_thresholds: "
            f"off_schema_ok={calibration.get('thresholds', {}).get('off_schema_rate_ok', False)} "
            f"refusal_ok={calibration.get('thresholds', {}).get('refusal_rate_ok', False)} "
            f"failure_mode_concentration_ok={calibration.get('thresholds', {}).get('failure_mode_concentration_ok', False)} "
            f"malformed_relevant_ok={calibration.get('thresholds', {}).get('malformed_relevant_bundles_ok', False)} "
            f"has_bundles={calibration.get('thresholds', {}).get('has_bundles', False)}"
        ),
            (
                "calibration_dominant_type: "
                f"{calibration.get('dominant_bundle_type', '')} "
                f"share={calibration.get('dominant_bundle_share', 0.0):.4f}"
            ),
            f"malformed_bundles: total={calibration.get('malformed_bundle_count', 0)}",
            (
                "malformed_bundle_types: "
                + ", ".join(
                    f"{key}={value}"
                    for key, value in sorted((calibration.get("malformed_bundle_counts") or {}).items())
                )
            ),
        ]
        cohorts = calibration.get("cohorts") or {}
        cohort_names = ["current_head", "legacy", "unknown"]
        if "measurement_head" in cohorts:
            cohort_names.append("measurement_head")
        for cohort_name in cohort_names:
            cohort = cohorts.get(cohort_name) or {}
            non_counted_by_type = cohort.get("non_counted_bundle_reasons") or {}
            non_counted_breakdown = ", ".join(
                f"{key}={value}" for key, value in sorted(non_counted_by_type.items())
            )
            refusal_by_type = cohort.get("refusal_by_type") or {}
            refusal_breakdown = ", ".join(
                f"{key}={value}" for key, value in sorted(refusal_by_type.items())
            )
            blocker_code_by_type = cohort.get("blocker_code_counts") or {}
            blocker_code_breakdown = ", ".join(
                f"{key}={value}" for key, value in sorted(blocker_code_by_type.items())
            )
            bundle_types = ", ".join(
                f"{key}={value}" for key, value in sorted((cohort.get("bundle_type_counts") or {}).items())
            )
            lines.append(
                f"cohort[{cohort_name}]: total={cohort.get('total_bundles', 0)} dominant={cohort.get('dominant_bundle_type', '')} share={cohort.get('dominant_bundle_share', 0.0):.4f} bundles={bundle_types or 'none'}"
            )
            lines.append(
                (
                    f"cohort[{cohort_name}]_non_counted: "
                    f"total={cohort.get('non_counted_bundle_count', 0)} "
                    f"reasons={non_counted_breakdown or 'none'}"
                )
            )
            lines.append(
                (
                    f"cohort[{cohort_name}]_rates: "
                    f"off_schema={cohort.get('off_schema_rate', 0.0):.4f} "
                    f"({cohort.get('off_schema_count', 0)}/{cohort.get('off_schema_denominator', 0)}) "
                    f"refusal={cohort.get('refusal_rate', 0.0):.4f} "
                    f"({cohort.get('refusal_count', 0)}/{cohort.get('total_bundles', 0)}) "
                    f"blocker_code_breakdown={blocker_code_breakdown or 'none'} "
                    f"refusal_breakdown={refusal_breakdown or 'none'}"
                )
            )
            lines.append(
                (
                    f"cohort[{cohort_name}]_thresholds: "
                    f"off_schema_ok={cohort.get('thresholds', {}).get('off_schema_rate_ok', False)} "
                    f"refusal_ok={cohort.get('thresholds', {}).get('refusal_rate_ok', False)} "
                    f"failure_mode_concentration_ok={cohort.get('thresholds', {}).get('failure_mode_concentration_ok', False)} "
                    f"malformed_relevant_ok={cohort.get('thresholds', {}).get('malformed_relevant_bundles_ok', False)} "
                    f"has_bundles={cohort.get('thresholds', {}).get('has_bundles', False)}"
                )
            )
        for error in summary.get("errors") or []:
            lines.append(f"error: {error}")
        return "\n".join(lines)

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
