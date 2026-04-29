from mew.acceptance import (
    acceptance_finish_blocker,
    coerce_acceptance_checks,
    exact_command_example_requirements,
    extract_acceptance_constraints,
    implementation_contract_source_requirements,
    is_numeric_artifact_task,
    is_query_only_hidden_model_task,
    is_runtime_visual_artifact_task,
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


def test_acceptance_finish_blocker_rejects_stateful_output_relabel_only():
    text = (
        "Connect the speech bubble copy to live current state. "
        "Ensure fixture output does not claim live state."
    )
    checks = [
        {
            "constraint": "speech bubble reflects live state",
            "status": "verified",
            "evidence": "tool #4 passed; asserted the live desk label appears in the speech bubble.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "stdout": "PASS: asserted live desk label appears in the speech bubble.",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "stateful output semantic contrast evidence missing" in blocker


def test_acceptance_finish_blocker_rejects_stateful_output_without_checks():
    text = "Connect the speech bubble copy to live current state."

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True})

    assert "stateful output semantic contrast evidence missing" in blocker


def test_acceptance_finish_blocker_accepts_stateful_output_contrast_evidence():
    text = (
        "Connect the speech bubble copy to live current state. "
        "Ensure fixture output does not claim live state."
    )
    checks = [
        {
            "constraint": "speech bubble reflects live state",
            "status": "verified",
            "evidence": "tool #4 passed positive injected-state and negative fixture assertions.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "stdout": (
                        "PASS positive injected state payload: adapter returned current state "
                        "status=busy and the speech message changed to Busy.\n"
                        "PASS negative fixture path: fixture output says local terminal and "
                        "does not claim live state."
                    ),
                },
            }
        ]
    }

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session) == ""


def test_acceptance_finish_blocker_rejects_stateful_output_contrast_claim_without_tool_output():
    text = (
        "Connect the speech bubble copy to live current state. "
        "Ensure fixture output does not claim live state."
    )
    checks = [
        {
            "constraint": "speech bubble reflects live state",
            "status": "verified",
            "evidence": "tool #4 passed positive injected-state and negative fixture assertions.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "stdout": "PASS: asserted the live desk label appears in the speech bubble.",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "stateful output semantic contrast evidence missing" in blocker


def test_acceptance_finish_blocker_rejects_stateful_output_contrast_from_edit_summary():
    text = (
        "Connect the speech bubble copy to live current state. "
        "Ensure fixture output does not claim live state."
    )
    checks = [
        {
            "constraint": "speech bubble reflects live state",
            "status": "verified",
            "evidence": "tool #4 passed positive injected-state and negative fixture assertions.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "edit_file",
                "status": "completed",
                "summary": "positive injected state and negative fixture assertions were added",
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "stateful output semantic contrast evidence missing" in blocker


def test_acceptance_finish_blocker_rejects_stateful_output_contrast_from_command_parameter_only():
    text = (
        "Connect the speech bubble copy to live current state. "
        "Ensure fixture output does not claim live state."
    )
    checks = [
        {
            "constraint": "speech bubble reflects live state",
            "status": "verified",
            "evidence": "tool #4 passed positive injected-state and negative fixture assertions.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "pytest -k 'positive injected state or negative fixture'"},
                "result": {"exit_code": 0, "stdout": "1 passed"},
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "stateful output semantic contrast evidence missing" in blocker


def test_acceptance_finish_blocker_does_not_escalate_plain_current_copy_replacement():
    text = "Replace the current copy from Start to Begin. Ensure the output text updates."
    checks = [
        {
            "constraint": "Replace the current copy from Start to Begin.",
            "status": "verified",
            "evidence": "tool #2 read the output text and found Begin.",
        },
        {
            "constraint": "Ensure the output text updates.",
            "status": "verified",
            "evidence": "tool #2 read the output text and found Begin.",
        }
    ]

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}) == ""


def test_acceptance_finish_blocker_does_not_escalate_literal_current_status_title_copy():
    text = 'Use "Current Status" as the title text in the UI. Ensure the output text updates.'
    checks = [
        {
            "constraint": 'Use "Current Status" as the title text in the UI.',
            "status": "verified",
            "evidence": "tool #2 read the title text and found Current Status.",
        },
        {
            "constraint": "Ensure the output text updates.",
            "status": "verified",
            "evidence": "tool #2 read the title text and found Current Status.",
        },
    ]

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}) == ""


def test_acceptance_finish_blocker_does_not_escalate_literal_state_title_copy():
    text = 'Use "State" as the title text in the UI. Ensure the output text updates.'
    checks = [
        {
            "constraint": 'Use "State" as the title text in the UI.',
            "status": "verified",
            "evidence": "tool #2 read the title text and found State.",
        },
        {
            "constraint": "Ensure the output text updates.",
            "status": "verified",
            "evidence": "tool #2 read the title text and found State.",
        },
    ]

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}) == ""


def test_acceptance_finish_blocker_rejects_stale_runtime_artifact_before_fresh_verifier():
    text = "Run `node vm.js`; it will write /tmp/frame.bmp during the fresh VM run."
    checks = [
        {
            "constraint": "frame written by node vm.js",
            "status": "verified",
            "evidence": "Tool #7 verified /tmp/frame.bmp with bmp_header_ok=True.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 7,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js && python3 check_frame.py"},
                "result": {
                    "command": "node vm.js && python3 check_frame.py",
                    "exit_code": 0,
                    "stdout": "path=/tmp/frame.bmp\nframe_bytes=1024054\nbmp_header_ok=True\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "runtime artifact freshness unchecked" in blocker
    assert "/tmp/frame.bmp" in blocker


def test_acceptance_finish_blocker_rejects_discovered_stale_runtime_artifact_before_fresh_verifier():
    text = (
        "Implement a MIPS interpreter called vm.js so I can run `node vm.js`. "
        "Running this file should result in saving the frames as they are rendered."
    )
    checks = [
        {
            "constraint": "first frame was saved",
            "status": "verified",
            "evidence": "Tool #30 ran `rm -f /tmp/frame.bmp && node vm.js` and validated /tmp/frame.bmp.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 30,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "rm -f /tmp/frame.bmp && node vm.js && python3 check_frame.py"},
                "result": {
                    "command": "rm -f /tmp/frame.bmp && node vm.js && python3 check_frame.py",
                    "exit_code": 0,
                    "stdout": "frame bmp validation ok\n",
                    "stderr": "saved frame 1 to /tmp/frame.bmp after 30670791 instructions\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "runtime artifact freshness unchecked" in blocker
    assert "/tmp/frame.bmp" in blocker


def test_acceptance_finish_blocker_allows_stale_runtime_artifact_after_cleanup():
    text = "Run `node vm.js`; it will write /tmp/frame.bmp during the fresh VM run."
    checks = [
        {
            "constraint": "frame written by node vm.js",
            "status": "verified",
            "evidence": "Tool #7 verified /tmp/frame.bmp and tool #8 removed the stale frame for the fresh verifier.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 7,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js && python3 check_frame.py"},
                "result": {
                    "command": "node vm.js && python3 check_frame.py",
                    "exit_code": 0,
                    "stdout": "path=/tmp/frame.bmp\nframe_bytes=1024054\nbmp_header_ok=True\n",
                },
            },
            {
                "id": 8,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "rm -f /tmp/frame.bmp"},
                "result": {"command": "rm -f /tmp/frame.bmp", "exit_code": 0, "stdout": "cleaned /tmp/frame.bmp\n"},
            },
        ]
    }

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session) == ""


def test_acceptance_finish_blocker_rejects_runtime_command_pass_without_artifact_proof():
    text = "Run `node vm.js`; it will write /tmp/frame.bmp during the fresh VM run."
    checks = [
        {
            "constraint": "node vm.js exits successfully",
            "status": "verified",
            "evidence": "Tool #3 ran node vm.js with exit_code=0.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 3,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js"},
                "result": {"command": "node vm.js", "exit_code": 0, "stdout": "Program exited cleanly\n"},
            }
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "runtime final verifier artifact evidence missing" in blocker
    assert "/tmp/frame.bmp" in blocker


def test_acceptance_finish_blocker_rejects_wrong_runtime_artifact_path():
    text = (
        "Implement a MIPS interpreter called vm.js so I can run `node vm.js`. "
        "Running this file should result in saving the frames as they are rendered."
    )
    checks = [
        {
            "constraint": "first rendered frame was saved",
            "status": "verified",
            "evidence": "Tool #22 saved frames/frame000001.bmp and tool #23 verified the root frame copy.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 22,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js"},
                "result": {
                    "command": "node vm.js",
                    "exit_code": 0,
                    "stdout": (
                        "DoomGeneric initialized. Frames will be saved to /tmp/frame.bmp\n"
                        "saved frames/frame000001.bmp\n"
                    ),
                },
            },
            {
                "id": 23,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "python3 inspect_frames.py"},
                "result": {
                    "command": "python3 inspect_frames.py",
                    "exit_code": 0,
                    "stdout": (
                        "path frames/frame000001.bmp exists True size 1024054\n"
                        "path frame000001.bmp exists True size 1024054\n"
                        "tmp_frame_before_cleanup False -1\n"
                    ),
                },
            },
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "runtime final verifier artifact evidence missing" in blocker
    assert "/tmp/frame.bmp" in blocker


def test_acceptance_finish_blocker_rejects_runtime_visual_artifact_format_only_evidence():
    text = (
        "Implement vm.js so I can run `node vm.js`. It should save rendered frames to /tmp/frame.bmp. "
        "I will check that you booted doom correctly from the first rendered frame."
    )
    checks = [
        {
            "constraint": "first rendered frame is correct",
            "status": "verified",
            "evidence": (
                "Tool #19 validated /tmp/frame.bmp as a valid/non-uniform BMP, "
                "and tool #20 removed the stale frame."
            ),
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 19,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js && python3 check_frame.py"},
                "result": {
                    "command": "node vm.js && python3 check_frame.py",
                    "exit_code": 0,
                    "stdout": (
                        "artifact validation passed: both outputs were identical "
                        "320x200x32 BMPs\npath=/tmp/frame.bmp\n"
                    ),
                    "stderr": "saved frame 1 to /tmp/frame.bmp\n",
                },
            },
            {
                "id": 20,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "rm -f /tmp/frame.bmp"},
                "result": {"command": "rm -f /tmp/frame.bmp", "exit_code": 0, "stdout": "removed /tmp/frame.bmp\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session)

    assert "runtime visual artifact quality evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_runtime_visual_artifact_quality_evidence():
    text = (
        "Implement vm.js so I can run `node vm.js`. It should save rendered frames to /tmp/frame.bmp. "
        "I will check that you booted doom correctly from the first rendered frame."
    )
    checks = [
        {
            "constraint": "first rendered frame is correct",
            "status": "verified",
            "evidence": (
                "Tool #19 confirmed exact stdout I_InitGraphics, expected dimensions 640x400, "
                "and reference similarity for /tmp/frame.bmp; tool #20 removed the stale frame."
            ),
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 19,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "node vm.js && python3 check_frame.py"},
                "result": {
                    "command": "node vm.js && python3 check_frame.py",
                    "exit_code": 0,
                    "stdout": (
                        "I_InitGraphics: DOOM screen size: w x h: 320 x 200\n"
                        "framebuffer expected dimensions 640x400\n"
                        "reference similarity passed l2=0.01\n"
                        "saved /tmp/frame.bmp\n"
                    ),
                },
            },
            {
                "id": 20,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "rm -f /tmp/frame.bmp"},
                "result": {"command": "rm -f /tmp/frame.bmp", "exit_code": 0, "stdout": "removed /tmp/frame.bmp\n"},
            },
        ]
    }

    assert acceptance_finish_blocker(text, {"type": "finish", "task_done": True, "acceptance_checks": checks}, session=session) == ""


def test_runtime_visual_artifact_task_classifier_requires_quality_language():
    assert is_runtime_visual_artifact_task(
        "Run node vm.js; it should save rendered frames and I will check the first frame is correct."
    )
    assert not is_runtime_visual_artifact_task(
        "Run node vm.js; it will write /tmp/frame.bmp during the fresh VM run."
    )


def test_implementation_contract_source_requirements_extract_provided_source_refs():
    text = (
        "I have provided /app/doomgeneric_mips, a MIPS elf file, along with doomgeneric/, "
        "the corresponding source code. Please implement vm.js so I can run `node vm.js`."
    )

    requirements = implementation_contract_source_requirements(text)

    assert [item["path"] for item in requirements] == ["/app/doomgeneric_mips", "doomgeneric/"]


def test_acceptance_finish_blocker_rejects_hard_task_without_provided_source_evidence():
    text = (
        "I have provided /app/doomgeneric_mips, a MIPS elf file, along with doomgeneric/, "
        "the corresponding source code. Please implement a MIPS interpreter called vm.js "
        "so that I can run `node vm.js`."
    )
    checks = [
        {
            "constraint": "node vm.js runs",
            "status": "verified",
            "evidence": "Tool #3 ran node vm.js and produced a frame.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 1,
                "tool": "write_file",
                "status": "completed",
                "parameters": {"path": "vm.js", "content": "console.log('DoomGeneric initialized')"},
            },
            {
                "id": 3,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {"command": "node vm.js"},
                "result": {"command": "node vm.js", "exit_code": 0, "stdout": "DoomGeneric initialized\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "implementation contract source evidence ungrounded" in blocker
    assert "/app/doomgeneric_mips" in blocker


def test_acceptance_finish_blocker_accepts_hard_task_with_provided_source_evidence():
    text = (
        "I have provided /app/doomgeneric_mips, a MIPS elf file, along with doomgeneric/, "
        "the corresponding source code. Please implement a MIPS interpreter called vm.js "
        "so that I can run `node vm.js`."
    )
    checks = [
        {
            "constraint": "provided binary inspected",
            "status": "verified",
            "evidence": "Tool #1 inspected /app/doomgeneric_mips.",
        },
        {
            "constraint": "provided source inspected",
            "status": "verified",
            "evidence": "Tool #2 listed doomgeneric/ source files.",
        },
        {
            "constraint": "node vm.js runs",
            "status": "verified",
            "evidence": "Tool #3 ran node vm.js.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 1,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": "file /app/doomgeneric_mips"},
                "result": {"command": "file /app/doomgeneric_mips", "exit_code": 0},
            },
            {
                "id": 2,
                "tool": "glob",
                "status": "completed",
                "parameters": {"pattern": "doomgeneric/**"},
                "result": {"text": "doomgeneric/doomgeneric_img.c\ndoomgeneric/i_system.c"},
            },
            {
                "id": 3,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {"command": "node vm.js"},
                "result": {"command": "node vm.js", "exit_code": 0},
            },
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


def test_query_only_hidden_model_classifier_covers_forward_extraction():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. Save the matrix "
        "to `/app/stolen_A1.npy`."
    )

    assert is_query_only_hidden_model_task(text)
    assert is_query_only_hidden_model_task(
        "Use query access via the forward function as a black-box oracle. "
        "The ReLU neural network has unknown hidden layer weights A1."
    )
    assert not is_query_only_hidden_model_task("Call forward(x) in this ordinary helper test.")


def test_acceptance_finish_blocker_rejects_query_only_visible_weight_access_from_write_file():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #3 checked source and output.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #3 exists True.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nimport forward as target\nnp.save('/app/stolen_A1.npy', target.A1)\n",
                },
            },
            {
                "id": 3,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "exists True\nmatches_A1 True\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model source violation" in blocker


def test_acceptance_finish_blocker_rejects_query_only_visible_weight_access_from_edit_hunks():
    text = (
        "Use query access via the forward function as a black-box oracle. "
        "The ReLU neural network has unknown hidden layer weights A1. "
        "Save the matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #3 checked source and output.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #3 exists True.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "edit_file_hunks",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "edits": [
                        {
                            "old": "return recover()",
                            "new": "import forward as target\nreturn target.A1",
                        }
                    ],
                },
            },
            {
                "id": 3,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "exists True\nmatches_A1 True\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model source violation" in blocker


def test_acceptance_finish_blocker_rejects_query_only_visible_weight_access_alias():
    text = (
        "Use query access via the forward function as a black-box oracle. "
        "The ReLU neural network has unknown hidden layer weights A1. "
        "Save the matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #3 synthetic randomized holdout pass true.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import forward as f\nanswer = f.A1\n",
                },
            },
            {
                "id": 3,
                "tool": "run_tests",
                "status": "completed",
                "result": {"stdout": "synthetic randomized holdout pass true\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model source violation" in blocker


def test_acceptance_finish_blocker_rejects_query_only_visible_weight_dynamic_reads():
    text = (
        "Use query access via the forward function as a black-box oracle. "
        "The ReLU neural network has unknown hidden layer weights A1. "
        "Save the matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #3 synthetic randomized holdout pass true.",
        }
    ]
    forbidden_sources = [
        "import forward\nanswer = forward.__dict__['A1']\n",
        "import forward\nanswer = vars(forward)['A1']\n",
        "import importlib\nm = importlib.import_module('forward')\nanswer = m.A1\n",
        "m = __import__('forward')\nanswer = m.__dict__['A1']\n",
        "import importlib\nanswer = importlib.import_module('forward').A1\n",
        "from pathlib import Path\nsrc = Path('forward.py').read_text()\n",
    ]
    for source in forbidden_sources:
        session = {
            "tool_calls": [
                {
                    "id": 2,
                    "tool": "write_file",
                    "status": "completed",
                    "parameters": {"path": "steal.py", "content": source},
                },
                {
                    "id": 3,
                    "tool": "run_tests",
                    "status": "completed",
                    "result": {"stdout": "synthetic randomized holdout pass true\n"},
                },
            ]
        }

        blocker = acceptance_finish_blocker(
            text,
            {"type": "finish", "task_done": True, "acceptance_checks": checks},
            session=session,
        )

        assert "query-only hidden-model source violation" in blocker


def test_acceptance_finish_blocker_allows_dynamic_import_for_forward_calls_only():
    text = (
        "Use query access via the forward function as a black-box oracle. "
        "The ReLU neural network has unknown hidden layer weights A1. "
        "Save the matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #3 synthetic randomized holdout pass true.",
        },
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #3 synthetic randomized holdout pass true.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #3 synthetic randomized holdout pass true.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": (
                        "import importlib\n"
                        "m = importlib.import_module('forward')\n"
                        "def f(x):\n"
                        "    return m.forward(x)\n"
                    ),
                },
            },
            {
                "id": 3,
                "tool": "run_tests",
                "status": "completed",
                "result": {"stdout": "synthetic randomized holdout pass true\n"},
            },
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


def test_acceptance_finish_blocker_rejects_query_only_visible_weight_access_star_import():
    text = (
        "Use query access via the forward function as a black-box oracle. "
        "The ReLU neural network has unknown hidden layer weights A1. "
        "Save the matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #3 synthetic randomized holdout pass true.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "from forward import *\nanswer = A1\n",
                },
            },
            {
                "id": 3,
                "tool": "run_tests",
                "status": "completed",
                "result": {"stdout": "synthetic randomized holdout pass true\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model source violation" in blocker


def test_acceptance_finish_blocker_rejects_query_only_visible_fixture_only_validation():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #4 query_only_source_check True.",
        },
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #4 visible fixture min_best_abs_cos_rows 0.999999 and pass True.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #4 exists True.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {
                    "stdout": (
                        "exists True\nstolen_shape (20, 10)\ntarget_shape (20, 10)\n"
                        "query_only_source_check True\npass True\n"
                    )
                },
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model generalization evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_query_only_failed_holdout_plus_visible_passed():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #4 synthetic holdout failed; visible fixture passed.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "synthetic holdout failed\nvisible fixture passed\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model generalization evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_query_only_skipped_holdout_plus_visible_passed():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #4 visible fixture passed. synthetic holdout skipped.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "visible fixture passed. synthetic holdout skipped.\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model generalization evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_query_only_hidden_ok_without_holdout():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #4 hidden ok.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "result": {"stdout": "hidden ok\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model generalization evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_query_only_holdout_validation():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #5 source check passed and synthetic randomized holdout pass true.",
        },
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #5 synthetic randomized holdout pass true; all matched on generated 30-row model.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #5 exists True and synthetic pass true.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 5,
                "tool": "run_tests",
                "status": "completed",
                "result": {
                    "stdout": (
                        "source check passed\nsynthetic randomized hidden holdout pass true\n"
                        "generated 30-row model all matched\n"
                    )
                },
            },
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


def test_acceptance_finish_blocker_accepts_query_only_all_matched_validation():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #5 randomized synthetic all_matched true.",
        },
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #5 randomized synthetic all_matched true.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #5 randomized synthetic all_matched true.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 5,
                "tool": "run_tests",
                "status": "completed",
                "result": {"stdout": "randomized synthetic validation all_matched true\n"},
            },
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


def test_acceptance_finish_blocker_rejects_query_only_all_matched_false():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #5 randomized synthetic all_matched=0.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": "import numpy as np\nfrom forward import forward\n# query-only recovery\n",
                },
            },
            {
                "id": 5,
                "tool": "run_tests",
                "status": "completed",
                "result": {"stdout": "randomized synthetic validation all_matched=0\n"},
            },
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "query-only hidden-model generalization evidence ungrounded" in blocker


def test_acceptance_finish_blocker_allows_synthetic_validator_object_fields():
    text = (
        "I have a ReLU neural network that you can query by importing `forward.py` "
        "and calling forward(x). You do not know the shape of A1. The script should "
        "save this matrix to `/app/stolen_A1.npy`."
    )
    checks = [
        {
            "constraint": "Use forward(x) query access for the extraction script.",
            "status": "verified",
            "evidence": "Tool #5 source check passed and synthetic randomized holdout pass true.",
        },
        {
            "constraint": "Output a matrix equal to A1 up to permuting neurons and scaling.",
            "status": "verified",
            "evidence": "Tool #5 synthetic randomized holdout pass true.",
        },
        {
            "constraint": "Save the matrix to /app/stolen_A1.npy.",
            "status": "verified",
            "evidence": "Tool #5 exists True and synthetic randomized holdout pass true.",
        },
    ]
    session = {
        "tool_calls": [
            {
                "id": 2,
                "tool": "write_file",
                "status": "completed",
                "parameters": {
                    "path": "steal.py",
                    "content": (
                        "from forward import forward\n"
                        "class Synthetic:\n"
                        "    def __init__(self):\n"
                        "        self.A1 = None\n"
                        "synthetic = Synthetic()\n"
                        "synthetic.A1 = 'holdout ground truth only'\n"
                    ),
                },
            },
            {
                "id": 5,
                "tool": "run_tests",
                "status": "completed",
                "result": {"stdout": "synthetic randomized holdout pass true\n"},
            },
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


def test_exact_command_example_requirements_extract_backticked_run_shapes():
    text = (
        "Write /app/polyglot/main.rs. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N` or "
        "`g++ -x c++ /app/polyglot/main.rs -o /app/polyglot/cmain && /app/polyglot/cmain N`."
    )

    commands = [item["command"] for item in exact_command_example_requirements(text)]

    assert commands == [
        "rustc /app/polyglot/main.rs && /app/polyglot/main N",
        "g++ -x c++ /app/polyglot/main.rs -o /app/polyglot/cmain && /app/polyglot/cmain N",
    ]


def test_acceptance_finish_blocker_rejects_cd_wrapped_exact_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "rustc /app/polyglot/main.rs && /app/polyglot/main N",
            "status": "verified",
            "evidence": "tool #4 ran the exact command shape.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'cd /app/polyglot; "
                        "rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                    )
                },
                "result": {
                    "command": "bash -lc 'cd /app/polyglot; rustc /app/polyglot/main.rs && /app/polyglot/main 20'",
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_exact_command_example_from_task_cwd():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "rustc /app/polyglot/main.rs && /app/polyglot/main N",
            "status": "verified",
            "evidence": "tool #4 ran rustc /app/polyglot/main.rs && /app/polyglot/main 20.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_command",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                },
                "result": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'",
                    "exit_code": 0,
                    "stdout": "10946\n",
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


def test_acceptance_finish_blocker_accepts_command_example_from_tool_not_check_text():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Both advertised command shapes should print Fibonacci values.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                },
                "result": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'",
                    "exit_code": 0,
                    "stdout": "10946\n",
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


def test_acceptance_finish_blocker_rejects_command_example_verifier_loop_as_surrogate():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Both advertised command shapes should print Fibonacci values.",
            "status": "verified",
            "evidence": "Tool call 4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs && "
                        "for n in 0 1 2 7; do /app/polyglot/main \"$n\"; done'"
                    )
                },
                "result": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs && "
                        "for n in 0 1 2 7; do /app/polyglot/main \"$n\"; done'"
                    ),
                    "exit_code": 0,
                    "stdout": "1\n1\n2\n21\n",
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_output_override_for_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs -o /app/polyglot/main "
                        "&& /app/polyglot/main 20'"
                    )
                },
                "result": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs -o /app/polyglot/main "
                        "&& /app/polyglot/main 20'"
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_python_output_override_for_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "python3 -c \"import subprocess; "
                        "subprocess.run(['rustc','/app/polyglot/main.rs','-o','/app/polyglot/main']); "
                        "subprocess.run(['/app/polyglot/main','20'])\""
                    )
                },
                "result": {
                    "command": (
                        "python3 -c \"import subprocess; "
                        "subprocess.run(['rustc','/app/polyglot/main.rs','-o','/app/polyglot/main']); "
                        "subprocess.run(['/app/polyglot/main','20'])\""
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_semicolon_for_and_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs; /app/polyglot/main 20'"
                },
                "result": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs; /app/polyglot/main 20'",
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_subshell_cd_for_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc '(cd /app/polyglot && rustc /app/polyglot/main.rs && /app/polyglot/main 20)'"
                },
                "result": {
                    "command": "bash -lc '(cd /app/polyglot && rustc /app/polyglot/main.rs && /app/polyglot/main 20)'",
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_setup_copy_between_command_example_terms():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs && "
                        "cp /app/main /app/polyglot/main && /app/polyglot/main 20'"
                    )
                },
                "result": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs && "
                        "cp /app/main /app/polyglot/main && /app/polyglot/main 20'"
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_setup_copy_before_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'cp /app/main /app/polyglot/main && "
                        "rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                    )
                },
                "result": {
                    "command": (
                        "bash -lc 'cp /app/main /app/polyglot/main && "
                        "rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_out_dir_override_for_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs --out-dir /app/polyglot "
                        "&& /app/polyglot/main 20'"
                    )
                },
                "result": {
                    "command": (
                        "bash -lc 'rustc /app/polyglot/main.rs --out-dir /app/polyglot "
                        "&& /app/polyglot/main 20'"
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_python_cwd_wrapper_for_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "python3 -c \"import subprocess; "
                        "subprocess.run(['rustc','/app/polyglot/main.rs'], cwd='/app/polyglot'); "
                        "subprocess.run(['/app/polyglot/main','20'])\""
                    )
                },
                "result": {
                    "command": (
                        "python3 -c \"import subprocess; "
                        "subprocess.run(['rustc','/app/polyglot/main.rs'], cwd='/app/polyglot'); "
                        "subprocess.run(['/app/polyglot/main','20'])\""
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_python_chdir_wrapper_for_command_example():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "python3 -c \"import os, subprocess; os.chdir('/app/polyglot'); "
                        "subprocess.run(['rustc','/app/polyglot/main.rs']); "
                        "subprocess.run(['/app/polyglot/main','20'])\""
                    )
                },
                "result": {
                    "command": (
                        "python3 -c \"import os, subprocess; os.chdir('/app/polyglot'); "
                        "subprocess.run(['rustc','/app/polyglot/main.rs']); "
                        "subprocess.run(['/app/polyglot/main','20'])\""
                    ),
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_rejects_failed_command_example_result():
    text = (
        "Write me a single file in /app/polyglot/main.rs which is a polyglot. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N`."
    )
    checks = [
        {
            "constraint": "Advertised command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=1 attempted advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                },
                "result": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'",
                    "exit_code": 1,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_requires_each_advertised_command_example():
    text = (
        "Write /app/polyglot/main.rs. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N` or "
        "`g++ -x c++ /app/polyglot/main.rs -o /app/polyglot/cmain && /app/polyglot/cmain N`."
    )
    checks = [
        {
            "constraint": "Advertised Rust command shape works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified the Rust advertised command shape.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                },
                "result": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'",
                    "exit_code": 0,
                },
            }
        ]
    }

    blocker = acceptance_finish_blocker(
        text,
        {"type": "finish", "task_done": True, "acceptance_checks": checks},
        session=session,
    )

    assert "exact command example evidence ungrounded" in blocker


def test_acceptance_finish_blocker_accepts_both_advertised_command_examples():
    text = (
        "Write /app/polyglot/main.rs. I can run "
        "`rustc /app/polyglot/main.rs && /app/polyglot/main N` or "
        "`g++ -x c++ /app/polyglot/main.rs -o /app/polyglot/cmain && /app/polyglot/cmain N`."
    )
    checks = [
        {
            "constraint": "Both advertised command shapes work.",
            "status": "verified",
            "evidence": "Tool #4 and Tool call 5 verified both advertised command shapes.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'"
                },
                "result": {
                    "command": "bash -lc 'rustc /app/polyglot/main.rs && /app/polyglot/main 20'",
                    "exit_code": 0,
                },
            },
            {
                "id": 5,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {
                    "command": (
                        "bash -lc 'g++ -x c++ /app/polyglot/main.rs -o /app/polyglot/cmain "
                        "&& /app/polyglot/cmain 20'"
                    )
                },
                "result": {
                    "command": (
                        "bash -lc 'g++ -x c++ /app/polyglot/main.rs -o /app/polyglot/cmain "
                        "&& /app/polyglot/cmain 20'"
                    ),
                    "exit_code": 0,
                },
            },
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


def test_acceptance_finish_blocker_accepts_python_command_example_itself():
    text = "You can run `python3 /app/check.py N` to validate the answer."
    checks = [
        {
            "constraint": "Advertised Python command works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified the advertised Python command.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {"command": "python3 /app/check.py 1"},
                "result": {"command": "python3 /app/check.py 1", "exit_code": 0},
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


def test_acceptance_finish_blocker_accepts_cat_command_example_itself():
    text = "You can run `cat /app/out.txt` to inspect the answer."
    checks = [
        {
            "constraint": "Advertised cat command works.",
            "status": "verified",
            "evidence": "Tool #4 run_tests exit_code=0 verified the advertised cat command.",
        }
    ]
    session = {
        "tool_calls": [
            {
                "id": 4,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {"command": "cat /app/out.txt"},
                "result": {"command": "cat /app/out.txt", "exit_code": 0},
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
