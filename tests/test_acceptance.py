from mew.acceptance import (
    acceptance_finish_blocker,
    coerce_acceptance_checks,
    extract_acceptance_constraints,
    is_numeric_artifact_task,
)


def test_extract_acceptance_constraints_keeps_output_and_edit_scope_rules():
    text = (
        'Ensure that the LaTeX document main.tex compiles successfully with no "overfull hbox" warnings. '
        "In doing so, the only edits you may make are to replace words in input.tex with their specified "
        "synonyms in synonyms.txt. Do not edit main.tex or synonyms.txt."
    )

    constraints = extract_acceptance_constraints(text)

    assert any("no \"overfull hbox\" warnings" in item for item in constraints)
    assert any("only edits" in item and "synonyms.txt" in item for item in constraints)
    assert any("Do not edit main.tex or synonyms.txt" in item for item in constraints)


def test_acceptance_finish_blocker_requires_verified_checks_for_task_done():
    text = (
        "Ensure the output file exists. The only edits you may make are specified replacements. "
        "Do not edit config.json."
    )

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True})

    assert "acceptance constraints unchecked" in blocker


def test_acceptance_finish_blocker_accepts_complete_verified_checks():
    text = "Ensure the output file exists. Do not edit config.json."
    constraints = extract_acceptance_constraints(text)
    checks = [
        {"constraint": constraint, "status": "verified", "evidence": "tool #3 output confirmed it"}
        for constraint in constraints
    ]

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}) == ""
    assert coerce_acceptance_checks(checks) == checks


def test_acceptance_finish_blocker_rejects_edit_scope_write_history_after_write():
    text = (
        "Ensure the output file exists. The only edits you may make are specified replacements. "
        "Do not edit config.json."
    )
    checks = [
        {"constraint": "Ensure the output file exists.", "status": "verified", "evidence": "tool #3 passed"},
        {
            "constraint": "The only edits you may make are specified replacements.",
            "status": "verified",
            "evidence": "Applied edit_file tool #2 with replacements from earlier read history.",
        },
        {
            "constraint": "Do not edit config.json.",
            "status": "verified",
            "evidence": "Write history shows no write action for config.json.",
        },
    ]
    session = {
        "tool_calls": [
            {"id": 1, "tool": "read_file", "status": "completed"},
            {"id": 2, "tool": "edit_file", "status": "completed"},
            {"id": 3, "tool": "run_command", "status": "completed"},
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "edit-scope acceptance evidence ungrounded" in blocker


def test_acceptance_finish_blocker_requires_explicit_edit_scope_check_after_write():
    text = "Ensure output exists. The only edits you may make are specified replacements."
    checks = [
        {"constraint": "Ensure output exists.", "status": "verified", "evidence": "tool #3 passed"},
        {"constraint": "Task complete.", "status": "verified", "evidence": "tool #4 passed"},
    ]
    session = {
        "tool_calls": [
            {"id": 1, "tool": "read_file", "status": "completed"},
            {"id": 2, "tool": "edit_file", "status": "completed"},
            {"id": 3, "tool": "run_command", "status": "completed"},
            {"id": 4, "tool": "run_command", "status": "completed"},
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "edit-scope acceptance evidence missing" in blocker


def test_acceptance_finish_blocker_accepts_post_write_edit_scope_validator():
    text = (
        "Ensure the output file exists. The only edits you may make are specified replacements. "
        "Do not edit config.json."
    )
    checks = [
        {"constraint": "Ensure the output file exists.", "status": "verified", "evidence": "tool #3 passed"},
        {
            "constraint": "The only edits you may make are specified replacements.",
            "status": "verified",
            "evidence": "Tool #4 run_command compared the final file against the allowed replacements and printed OK.",
        },
        {
            "constraint": "Do not edit config.json.",
            "status": "verified",
            "evidence": "Tool #4 run_command confirmed config.json was unchanged.",
        },
    ]
    session = {
        "tool_calls": [
            {"id": 1, "tool": "read_file", "status": "completed"},
            {"id": 2, "tool": "edit_file", "status": "completed"},
            {"id": 3, "tool": "run_command", "status": "completed"},
            {"id": 4, "tool": "run_command", "status": "completed"},
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_rejects_numeric_single_fit_residual_only():
    text = (
        "Fit the G and 2D Peak of the spectrum and return the x0, gamma, "
        "amplitude and offset of the peaks."
    )
    checks = [
        {
            "constraint": "Verify numeric plausibility against the input data.",
            "status": "verified",
            "evidence": "Tool #4 residual checks and finite parameter assertions passed.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "rmse=0.05 rel_rmse=0.02 finite parameters"},
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "numeric artifact quality evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_numeric_independent_cross_check():
    text = (
        "Fit the G and 2D Peak of the spectrum and return the x0, gamma, "
        "amplitude and offset of the peaks."
    )
    checks = [
        {
            "constraint": "Verify numeric plausibility against the input data.",
            "status": "verified",
            "evidence": "Tool #4 independent cross-check recomputed fit stability with an alternative method.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {
                    "stdout": (
                        "independent cross-check: alternative grid fit compared against "
                        "nonlinear fit; residual rmse and parameter stability within bounds"
                    )
                },
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_ignores_blocked_numeric_checks():
    text = "Compute metrics from the dataset and write output.json."
    checks = [
        {
            "constraint": "Verify numeric metric quality against the input data.",
            "status": "blocked",
            "evidence": "Tool #4 independent cross-check recomputed metrics with an alternative method.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {
                    "stdout": (
                        "independent cross-check: alternative computation compared metrics; "
                        "residual error within bounds"
                    )
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "numeric artifact quality evidence missing" in blocker


def test_numeric_artifact_task_classifier_covers_rank_and_metrics_without_ui_false_positive():
    assert is_numeric_artifact_task("Rank rows by numeric score.")
    assert is_numeric_artifact_task("Compute metrics from the dataset.")
    assert not is_numeric_artifact_task("Fix offset pagination regression where the text does not fit.")
    assert not is_numeric_artifact_task("Update metrics reporting docs.")
    assert not is_numeric_artifact_task("Keep the prompt cache boundary empty without draft metrics.")


def test_acceptance_finish_blocker_does_not_treat_ui_fit_or_offset_as_numeric():
    text = "Fix offset pagination regression where the text does not fit in the card. Ensure output file exists."
    checks = [
        {"constraint": constraint, "status": "verified", "evidence": "tool #2 output confirmed it"}
        for constraint in extract_acceptance_constraints(text)
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "ui pagination regression verified"},
            }
        ]
    }

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )


def test_acceptance_finish_blocker_does_not_escalate_non_edit_scope_checks():
    text = "Ensure the output file exists."
    checks = [{"constraint": text, "status": "verified", "evidence": "tool #2 wrote the file"}]
    session = {"tool_calls": [{"id": 2, "tool": "write_file", "status": "completed"}]}

    assert (
        acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )
        == ""
    )
