import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mew.cli import build_parser
from mew.config import LOG_FILE, MODEL_TRACE_FILE, STATE_DIR, STATE_FILE
from mew.dogfood import (
    DOGFOOD_SCENARIOS,
    _evaluate_managed_action_projection,
    _repository_test_tail_summary,
    _write_repository_test_tail_emulator_fixture,
    _write_terminal_bench_replay_fixture,
    active_agent_run_ids,
    agent_reflex_sweep_timeout,
    build_dogfood_report,
    build_m2_comparative_protocol,
    build_runtime_command,
    copy_source_workspace,
    dogfood_subprocess_env,
    dogfood_time_dilation_env,
    dogfood_stop_timeout,
    dogfood_runtime_env,
    effective_time_dilation,
    format_dogfood_loop_report,
    format_dogfood_report,
    format_dogfood_scenario_report,
    format_m2_fresh_cli_restart_prompt,
    injected_message_status,
    prepopulate_project_snapshot,
    prepare_dogfood_workspace,
    queued_message_event_id,
    run_dogfood,
    run_dogfood_loop,
    run_dogfood_scenario,
    run_post_wait_agent_reflex,
    seed_ready_coding_task,
    summarize_dogfood_scenario_json,
    suppress_processed_injected_dropped_threads,
    tail_lines,
    validate_m6_13_internalization_review_artifact,
    wait_for_active_agent_runs,
)
from mew.state import add_event, add_outbox_message, default_state


class DogfoodTests(unittest.TestCase):
    def test_dogfood_subprocess_env_preserves_explicit_mew_executable(self):
        with patch.dict(os.environ, {"MEW_EXECUTABLE": "/tmp/custom-mew"}):
            env = dogfood_subprocess_env()

        self.assertEqual(env["MEW_EXECUTABLE"], "/tmp/custom-mew")

    def test_dogfood_runtime_env_adds_overrides_to_subprocess_env(self):
        with patch("mew.dogfood.dogfood_subprocess_env", return_value={"PYTHONPATH": "src", "KEEP": "base"}):
            env = dogfood_runtime_env({"KEEP": "override", "EXTRA": "1"})

        self.assertEqual(env["PYTHONPATH"], "src")
        self.assertEqual(env["KEEP"], "override")
        self.assertEqual(env["EXTRA"], "1")

    def test_dogfood_time_dilation_env_sets_multiplier(self):
        env = dogfood_time_dilation_env({"KEEP": "base"}, 168)

        self.assertEqual(env["KEEP"], "base")
        self.assertEqual(env["MEW_TIME_DILATION"], "168.0")
        self.assertEqual(effective_time_dilation(env), 168.0)

    def test_cli_dogfood_scenario_choices_follow_registered_scenarios(self):
        parser = build_parser()

        for scenario in DOGFOOD_SCENARIOS:
            args = parser.parse_args(["dogfood", "--scenario", scenario, "--json"])
            self.assertEqual(args.scenario, scenario)

    def test_cli_dogfood_all_shortcut_parses_exactly(self):
        parser = build_parser()

        args = parser.parse_args(["dogfood", "--all", "--json"])

        self.assertTrue(args.all_scenarios)
        self.assertIsNone(args.scenario)

    def test_cli_dogfood_scenario_timing_defaults_are_unspecified(self):
        parser = build_parser()

        args = parser.parse_args(["dogfood", "--scenario", "resident-loop", "--json"])

        self.assertFalse(hasattr(args, "duration"))
        self.assertFalse(hasattr(args, "interval"))
        self.assertFalse(hasattr(args, "poll_interval"))
        self.assertFalse(hasattr(args, "time_dilation"))

    def test_cli_dogfood_time_dilation_parses(self):
        parser = build_parser()

        args = parser.parse_args(["dogfood", "--scenario", "resident-loop", "--time-dilation", "168", "--json"])

        self.assertEqual(args.time_dilation, 168.0)

    def test_cli_dogfood_terminal_bench_replay_assertions_parse(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "dogfood",
                "--scenario",
                "m6_24-terminal-bench-replay",
                "--terminal-bench-job-dir",
                "/tmp/job",
                "--terminal-bench-task",
                "build-cython-ext",
                "--terminal-bench-assert-long-build-status",
                "blocked",
                "--terminal-bench-assert-current-failure",
                "long_command_failed",
                "--terminal-bench-assert-recovery-action",
                "repair_failed_long_command",
                "--terminal-bench-assert-blocker",
                "runtime_link_failed",
                "--terminal-bench-assert-mew-exit-code",
                "1",
                "--terminal-bench-assert-external-reward",
                "0",
                "--terminal-bench-assert-next-action-contains",
                "compiled/native source frontier",
                "--json",
            ]
        )

        self.assertEqual(args.terminal_bench_job_dir, "/tmp/job")
        self.assertEqual(args.terminal_bench_task, "build-cython-ext")
        self.assertEqual(args.terminal_bench_assert_long_build_status, "blocked")
        self.assertEqual(args.terminal_bench_assert_current_failure, "long_command_failed")
        self.assertEqual(args.terminal_bench_assert_recovery_action, "repair_failed_long_command")
        self.assertEqual(args.terminal_bench_assert_blocker, ["runtime_link_failed"])
        self.assertEqual(args.terminal_bench_assert_mew_exit_code, 1)
        self.assertEqual(args.terminal_bench_assert_external_reward, 0.0)
        self.assertEqual(args.terminal_bench_assert_next_action_contains, "compiled/native source frontier")

    def test_cli_dogfood_m2_task_shape_choices(self):
        parser = build_parser()

        for shape in ("test_discovery", "approval_pairing", "process_stop"):
            with self.subTest(shape=shape):
                args = parser.parse_args(
                    [
                        "dogfood",
                        "--scenario",
                        "m2-comparative",
                        "--m2-task-shape",
                        shape,
                        "--json",
                    ]
                )

            self.assertEqual(args.m2_task_shape, shape)

    def test_cli_dogfood_m3_comparison_report_parses(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "dogfood",
                "--scenario",
                "m3-reentry-gate",
                "--m3-comparison-report",
                "fresh-report.json",
                "--json",
            ]
        )

        self.assertEqual(args.m3_comparison_report, "fresh-report.json")

    def test_dogfood_stop_timeout_covers_ai_model_timeout(self):
        args = SimpleNamespace(ai=True, stop_timeout=10.0, model_timeout=60.0)

        self.assertEqual(dogfood_stop_timeout(args), 75.0)

    def test_dogfood_stop_timeout_keeps_explicit_longer_timeout(self):
        args = SimpleNamespace(ai=True, stop_timeout=120.0, model_timeout=60.0)

        self.assertEqual(dogfood_stop_timeout(args), 120.0)

    def test_prepare_workspace_creates_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace, created = prepare_dogfood_workspace(Path(tmp) / "dog")

            self.assertFalse(created)
            self.assertTrue((workspace / "README.md").exists())

    def test_build_runtime_command_keeps_ai_optional(self):
        args = SimpleNamespace(
            interval=3,
            poll_interval=0.2,
            autonomy_level="act",
            model_timeout=45,
            ai=False,
            auth=None,
            model_backend="codex",
            model="",
            base_url="",
            allow_write=False,
            allow_verify=False,
            execute_tasks=False,
            allow_agent_run=False,
            allow_native_work=False,
            agent_stale_minutes=None,
            agent_result_timeout=None,
            agent_start_timeout=None,
            review_model=None,
            verify_command="",
            verify_interval_minutes=0.05,
        )

        command = build_runtime_command(args, Path("/tmp/work"))

        self.assertIn("--autonomous", command)
        self.assertNotIn("--ai", command)

    def test_build_runtime_command_resolves_relative_auth_before_workspace_cwd(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                args = SimpleNamespace(
                    interval=3,
                    poll_interval=0.2,
                    autonomy_level="act",
                    model_timeout=45,
                    ai=True,
                    auth="auth.json",
                    model_backend="codex",
                    model="",
                    base_url="",
                    allow_write=False,
                    allow_verify=False,
                    execute_tasks=False,
                    allow_agent_run=False,
                    allow_native_work=False,
                    agent_stale_minutes=None,
                    agent_result_timeout=None,
                    agent_start_timeout=None,
                    review_model=None,
                    verify_command="",
                    verify_interval_minutes=0.05,
                )

                command = build_runtime_command(args, Path("/tmp/work"))

                self.assertEqual(command[command.index("--auth") + 1], str((Path(tmp) / "auth.json").resolve()))
            finally:
                os.chdir(old_cwd)

    def test_build_runtime_command_can_enable_programmer_gates(self):
        args = SimpleNamespace(
            interval=3,
            poll_interval=0.2,
            autonomy_level="act",
            model_timeout=45,
            ai=False,
            auth=None,
            model_backend="codex",
            model="",
            base_url="",
            allow_write=False,
            allow_verify=False,
            execute_tasks=True,
            allow_agent_run=True,
            allow_native_work=True,
            allow_native_advance=True,
            agent_stale_minutes=3.0,
            agent_result_timeout=4.0,
            agent_start_timeout=5.0,
            review_model="codex-ultra",
            verify_command="",
            verify_interval_minutes=0.05,
            trace_model=True,
            max_reflex_rounds=2,
        )

        command = build_runtime_command(args, Path("/tmp/work"))

        self.assertIn("--execute-tasks", command)
        self.assertIn("--allow-agent-run", command)
        self.assertIn("--allow-native-work", command)
        self.assertIn("--allow-native-advance", command)
        self.assertEqual(command[command.index("--agent-stale-minutes") + 1], "3.0")
        self.assertEqual(command[command.index("--agent-result-timeout") + 1], "4.0")
        self.assertEqual(command[command.index("--agent-start-timeout") + 1], "5.0")
        self.assertEqual(command[command.index("--review-model") + 1], "codex-ultra")
        self.assertIn("--trace-model", command)
        self.assertEqual(command[command.index("--max-reflex-rounds") + 1], "2")

    def test_run_dogfood_trace_smoke_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="trace-smoke",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "trace-smoke")
            self.assertIn("trace-smoke: pass", text)

    def test_run_dogfood_scenario_cleanup_keeps_explicit_workspace_with_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "dog"
            args = SimpleNamespace(
                workspace=str(workspace),
                scenario="trace-smoke",
                cleanup=True,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            summary = summarize_dogfood_scenario_json(report)

            self.assertTrue(workspace.exists())
            self.assertTrue(report["kept"])
            self.assertEqual(report["cleanup_skipped_reason"], "explicit_workspace")
            self.assertIn("cleanup_skipped: explicit_workspace", text)
            self.assertEqual(summary["cleanup_skipped_reason"], "explicit_workspace")

    def test_run_dogfood_memory_search_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="memory-search",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "memory-search")
            self.assertIn("context_checkpoint_surfaces_in_focus", text)
            self.assertIn("context_checkpoint_surfaces_in_brief", text)
            self.assertIn("context_checkpoint_surfaces_in_desk_json", text)

    def test_run_dogfood_interrupted_focus_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="interrupted-focus",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertIn("ready_coding_question_points_to_code_cockpit", text)

    def test_run_dogfood_runtime_focus_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="runtime-focus",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "runtime-focus")
            self.assertIn("runtime-focus: pass", text)

    def test_run_dogfood_resident_loop_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="resident-loop",
                cleanup=False,
                duration=7.0,
                interval=2.0,
                poll_interval=0.1,
                time_dilation=24.0,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "resident-loop")
            checks = scenario["checks"]
            self.assertIn("resident_loop_processes_multiple_events", text)
            cadence_check = next(
                check
                for check in checks
                if check["name"] == "resident_loop_processes_multiple_events"
            )
            self.assertGreaterEqual(cadence_check["observed"]["passive_events"], 2)
            self.assertEqual(scenario["artifacts"]["requested_duration_seconds"], 7.0)
            self.assertEqual(scenario["artifacts"]["requested_interval_seconds"], 2.0)
            self.assertEqual(scenario["artifacts"]["time_dilation"], 24.0)
            self.assertGreaterEqual(scenario["artifacts"]["passive_events"], 2)
            self.assertGreaterEqual(scenario["artifacts"]["open_questions"], 1)
            self.assertGreaterEqual(scenario["artifacts"]["passive_span_seconds"], 40.0)
            self.assertIn("resident_loop_reentry_focus_surfaces_next_action", text)
            self.assertIn("resident_loop_reentry_brief_surfaces_current_state", text)
            self.assertIn("resident_loop_reentry_context_saves_checkpoint", text)

    def test_run_dogfood_native_work_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="native-work",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "native-work")
            self.assertIn("native_work_session_created_for_ready_coding_task", text)

    def test_run_dogfood_self_improve_controls_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="self-improve-controls",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "self-improve-controls")
            self.assertIn("self_improve_start_session_json_surfaces_controls", text)
            self.assertIn("self_improve_start_session_seeds_reentry_note", text)
            self.assertIn("self_improve_status_refresh_command_is_executable", text)
            self.assertIn("self_improve_reused_session_refreshes_reentry_note", text)

    def test_run_dogfood_m5_safety_hooks_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m5-safety-hooks",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "m5-safety-hooks")
            self.assertIn("m5_safety_hooks_governance_auto_approval_escalates", text)
            self.assertIn("m5_safety_hooks_external_side_effect_blocks_before_execution", text)

    def test_run_dogfood_m6_daemon_watch_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6-daemon-watch",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "m6-daemon-watch")
            self.assertIn("m6_daemon_status_reports_active_watcher", text)
            self.assertIn("m6_daemon_watcher_queues_processed_file_event", text)
            self.assertIn("m6_daemon_log_records_external_event", text)

    def test_run_dogfood_m6_daemon_restart_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6-daemon-restart",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "m6-daemon-restart")
            self.assertIn("m6_daemon_restart_reattaches_watcher_snapshot", text)
            self.assertIn("m6_daemon_restart_uses_external_event_path", text)
            self.assertIn("m6_daemon_restart_final_stop_is_clean", text)

    def test_run_dogfood_m6_daemon_loop_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6-daemon-loop",
                duration=3.2,
                interval=1.0,
                poll_interval=0.05,
                time_dilation=None,
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "m6-daemon-loop")
            self.assertIn("m6_daemon_loop_watcher_processes_file_event", text)
            self.assertIn("m6_daemon_loop_controls_pause_inspect_resume", text)
            self.assertIn("m6_daemon_loop_processes_multiple_passive_ticks", text)
            self.assertIn("m6_daemon_loop_reentry_focus_surfaces_task", text)
            self.assertGreaterEqual(report["scenarios"][0]["artifacts"]["passive_events"], 2)
            self.assertIsNotNone(report["scenarios"][0]["artifacts"]["watcher_event_id"])

    def test_run_dogfood_m6_9_memory_taxonomy_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_9-memory-taxonomy",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            check_names = {item["name"] for item in scenario["checks"]}

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_9-memory-taxonomy")
            self.assertEqual(scenario["status"], "pass")
            self.assertIn("m6_9-memory-taxonomy: pass", text)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(
                set(scenario["artifacts"]["populated_kinds"]),
                {"reviewer-steering", "task-template", "failure-shield", "file-pair"},
            )
            self.assertIn("reviewer-steering-missing-why", scenario["artifacts"]["rejected_cases"])
            self.assertIn("reasoning-trace-missing-evidence", scenario["artifacts"]["rejected_cases"])
            self.assertIn("m6_9_memory_taxonomy_reviewer-steering_write_accepts_required_evidence", check_names)
            self.assertIn("m6_9_memory_taxonomy_missing_reviewer_why_rejected", check_names)
            self.assertIn("m6_9_memory_taxonomy_incomplete_reasoning_trace_rejected", check_names)
            self.assertIn("m6_9_memory_taxonomy_resolves_source_to_test_pair", check_names)
            self.assertIn("m6_9_memory_taxonomy_resolves_test_to_source_pair", check_names)

    def test_run_dogfood_m6_9_active_memory_recall_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_9-active-memory-recall",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            check_names = {item["name"] for item in scenario["checks"]}

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_9-active-memory-recall")
            self.assertEqual(scenario["status"], "pass")
            self.assertIn("m6_9-active-memory-recall: pass", text)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertIn("M6.9 active recall dogfood pair", scenario["artifacts"]["active_memory_names"])
            self.assertIn("precondition_miss", scenario["artifacts"]["drop_reasons"])
            self.assertGreaterEqual(scenario["artifacts"]["kept_file_pair_count"], 1)
            self.assertGreaterEqual(scenario["artifacts"]["stale_drop_count"], 1)
            self.assertIn("m6_9_active_memory_recall_keeps_relevant_file_pair", check_names)
            self.assertIn("m6_9_active_memory_recall_drops_stale_file_pair_with_precondition_miss", check_names)

    def test_run_dogfood_m6_9_reviewer_steering_reuse_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_9-reviewer-steering-reuse",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            check_names = {item["name"] for item in scenario["checks"]}

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_9-reviewer-steering-reuse")
            self.assertEqual(scenario["status"], "pass")
            self.assertIn("m6_9-reviewer-steering-reuse: pass", text)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertTrue(scenario["artifacts"]["durable_rule_fired"])
            self.assertTrue(scenario["artifacts"]["blocked_pre_implementation"])
            self.assertTrue(scenario["artifacts"]["simulated_rescue_edit_prevented"])
            self.assertEqual(scenario["artifacts"]["reviewer_steering_rule_count"], 3)
            self.assertEqual(scenario["artifacts"]["durable_rule_fired_count"], 3)
            self.assertGreaterEqual(scenario["artifacts"]["simulated_rescue_edit_prevented_count"], 1)
            self.assertEqual(scenario["artifacts"]["blocked_patch_kind"], "existing_scenario_artifact_tweak")
            self.assertEqual(
                set(scenario["artifacts"]["blocked_patch_kinds"]),
                {"existing_scenario_artifact_tweak", "missing_focused_verifier", "unpaired_source_edit"},
            )
            self.assertIn("M6.9 reviewer steering reuse rule", scenario["artifacts"]["recalled_rule_names"])
            self.assertIn("M6.9 paired source test steering rule", scenario["artifacts"]["recalled_rule_names"])
            self.assertIn("M6.9 focused proof steering rule", scenario["artifacts"]["recalled_rule_names"])
            self.assertTrue(scenario["artifacts"]["trace"]["durable_rule_fired"])
            self.assertEqual(scenario["artifacts"]["trace"]["durable_rule_fired_count"], 3)
            self.assertTrue(scenario["artifacts"]["trace"]["simulated_rescue_edit_prevented"])
            self.assertIn("m6_9_reviewer_steering_reuse_active_recall_finds_rule", check_names)
            self.assertIn("m6_9_reviewer_steering_reuse_blocks_off_scope_patch", check_names)
            self.assertIn("m6_9_reviewer_steering_reuse_prevents_simulated_rescue_edit", check_names)
            self.assertIn("m6_9_reviewer_steering_reuse_writes_deterministic_trace", check_names)

    def test_run_dogfood_m6_9_failure_shield_reuse_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_9-failure-shield-reuse",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            check_names = {item["name"] for item in scenario["checks"]}

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_9-failure-shield-reuse")
            self.assertEqual(scenario["status"], "pass")
            self.assertIn("m6_9-failure-shield-reuse: pass", text)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["shield_blocked_count"], 2)
            self.assertTrue(scenario["artifacts"]["pre_implementation_blocked"])
            self.assertEqual(
                set(scenario["artifacts"]["blocked_patch_kinds"]),
                {"generic_cleanup_default_flag", "repeat_cached_window_retry"},
            )
            self.assertIn("M6.9 stale cached-window shield", scenario["artifacts"]["recalled_shield_names"])
            self.assertIn("M6.9 generic cleanup shield", scenario["artifacts"]["recalled_shield_names"])
            self.assertEqual(scenario["artifacts"]["trace"]["shield_blocked_count"], 2)
            self.assertTrue(scenario["artifacts"]["trace"]["pre_implementation_blocked"])
            self.assertIn("m6_9_failure_shield_reuse_active_recall_finds_two_shields", check_names)
            self.assertIn("m6_9_failure_shield_reuse_blocks_two_reverted_approaches", check_names)
            self.assertIn("m6_9_failure_shield_reuse_writes_deterministic_trace", check_names)

    def test_run_dogfood_m6_9_reasoning_trace_recall_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_9-reasoning-trace-recall",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            check_names = {item["name"] for item in scenario["checks"]}

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_9-reasoning-trace-recall")
            self.assertEqual(scenario["status"], "pass")
            self.assertIn("m6_9-reasoning-trace-recall: pass", text)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["recalled_count"], 2)
            self.assertEqual(scenario["artifacts"]["shortened_deliberation_count"], 2)
            self.assertGreaterEqual(scenario["artifacts"]["abstract_recall_count"], 1)
            self.assertIn("M6.9 focused verifier trace", scenario["artifacts"]["recalled_trace_names"])
            self.assertIn("M6.9 anti-polish drift trace", scenario["artifacts"]["recalled_trace_names"])
            self.assertEqual(scenario["artifacts"]["trace"]["recalled_count"], 2)
            self.assertGreaterEqual(scenario["artifacts"]["trace"]["abstract_recall_count"], 1)
            self.assertIn("m6_9_reasoning_trace_recall_writes_two_approved_traces", check_names)
            self.assertIn("m6_9_reasoning_trace_recall_two_iterations_recall_traces", check_names)
            self.assertIn("m6_9_reasoning_trace_recall_reviewer_confirms_shortened_deliberation", check_names)
            self.assertIn("m6_9_reasoning_trace_recall_writes_deterministic_trace", check_names)

    def test_validate_m6_13_internalization_review_artifact_rejects_mismatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            ref = Path(STATE_DIR) / "durable" / "review" / "review.json"
            path = workspace / ref
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "decision": "rejected",
                        "reasoning_trace_candidate": True,
                        "source_lane": "deliberation",
                        "source_lane_attempt_id": "lane-1",
                        "source_blocker_code": "review_rejected",
                        "source_bundle_ref": ".mew/durable/replay/deliberation/hard.json",
                        "same_shape_key": "shape-a",
                        "raw_transcript_stored": False,
                    }
                ),
                encoding="utf-8",
            )

            result = validate_m6_13_internalization_review_artifact(
                workspace,
                str(ref),
                lane_attempt_id="lane-1",
                source_bundle_ref=".mew/durable/replay/deliberation/hard.json",
                same_shape_key="shape-a",
            )

        self.assertFalse(result["ok"])
        self.assertIn("decision_mismatch", result["errors"])

    def test_run_dogfood_m6_13_deliberation_internalization_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_13-deliberation-internalization",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            artifacts = scenario["artifacts"]
            trace = artifacts["trace"]
            check_names = {item["name"] for item in scenario["checks"]}
            workspace = Path(args.workspace)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_13-deliberation-internalization")
            self.assertEqual(scenario["status"], "pass")
            self.assertIn("m6_13-deliberation-internalization: pass", text)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertTrue(artifacts["recalled"])
            self.assertEqual(artifacts["hard_task_id"], 61301)
            self.assertEqual(artifacts["later_same_shape_task_id"], 61302)
            self.assertEqual(artifacts["tiny_provider_mode"], "deterministic_fake")
            self.assertEqual(trace["evidence_class"], "contract_fixture")
            self.assertTrue(trace["close_evidence"])
            self.assertTrue(trace["contract_cycle_proven"])
            self.assertEqual(trace["tiny_provider_mode"], "deterministic_fake")
            self.assertEqual(trace["original_blocker_code"], "review_rejected")
            self.assertFalse(trace["known_limitations"])
            self.assertEqual(trace["ranked_recall_event"]["ranker"]["name"], "m6_9-ranked-recall")
            self.assertTrue(trace["ranked_recall_event"]["returned"])
            self.assertGreaterEqual(trace["ranked_recall_event"]["rank"], 1)
            self.assertIn("task_shape_similarity", trace["ranked_recall_event"]["score_components"])
            self.assertGreater(trace["ranked_recall_event"]["score_components"]["task_shape_similarity"], 0)
            self.assertEqual(trace["adapted_memory_event"]["source_lane"], "deliberation")
            self.assertEqual(trace["reviewer_decision"]["decision"], "approved")
            self.assertTrue(trace["reviewer_decision"]["validation"]["ok"])
            self.assertEqual(trace["reasoning_trace_ledger_ref"], ".mew/durable/memory/reasoning_trace.jsonl")
            self.assertTrue(trace["reviewer_confirmed_trace_shortened_deliberation"])
            self.assertFalse(trace["later_task_deliberation_invoked"])
            self.assertFalse(trace["close_blockers"])
            tiny_bundle = json.loads(
                (workspace / artifacts["trace"]["tiny_lane_replay_bundle_ref"]).read_text(encoding="utf-8")
            )
            normal_execution = tiny_bundle["normal_work_execution"]
            self.assertEqual(tiny_bundle["execution_path"], "run_work_batch_action->_apply_work_approval_batch")
            self.assertEqual(tiny_bundle["approval_count"], 2)
            self.assertEqual(tiny_bundle["deferred_verification_count"], 1)
            self.assertEqual(tiny_bundle["applied_paths"], ["tests/test_patch_draft.py", "src/mew/patch_draft.py"])
            self.assertEqual(normal_execution["final_source_verification_exit_code"], 0)
            self.assertGreaterEqual(normal_execution["verification_test_count"], 1)
            self.assertTrue(normal_execution["files_reflect_patch"])
            self.assertIn(
                "m6_13_deliberation_internalization_writes_reviewed_trace_with_provenance",
                check_names,
            )
            self.assertIn("m6_13_deliberation_internalization_consumes_reviewer_decision_artifact", check_names)
            self.assertIn("m6_13_deliberation_internalization_appends_reasoning_trace_ledger", check_names)
            self.assertIn("m6_13_deliberation_internalization_later_task_recalls_trace", check_names)
            self.assertIn("m6_13_deliberation_internalization_records_ranked_recall_event", check_names)
            self.assertIn("m6_13_deliberation_internalization_records_tiny_reuse_contract", check_names)
            self.assertIn("m6_13_deliberation_internalization_writes_deterministic_contract_trace", check_names)

    def test_run_dogfood_m6_13_live_provider_uses_backend_auth_defaults(self):
        observed_auth = []

        def fake_load_model_auth(model_backend, auth_path=None):
            observed_auth.append((model_backend, auth_path))
            return {"access_token": "token"}

        def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
            self.assertEqual(model_auth, {"access_token": "token"})
            if "read-only deliberation lane" in prompt:
                return {
                    "kind": "deliberation_result",
                    "schema_version": 1,
                    "todo_id": "todo-61301",
                    "lane": "deliberation",
                    "blocker_code": "review_rejected",
                    "decision": "propose_patch_strategy",
                    "situation": "review rejection needs a narrow causal repair in the work loop",
                    "reasoning_summary": "classify the blocker family before drafting",
                    "recommended_next": "retry_tiny",
                    "expected_trace_candidate": True,
                    "confidence": "high",
                }
            self.assertIn("Write-ready tiny draft lane is active.", prompt)
            return {
                "kind": "patch_proposal",
                "summary": "increment the paired meaning value",
                "files": [
                    {
                        "path": "src/mew/patch_draft.py",
                        "edits": [{"old": "return 41", "new": "return 42"}],
                    },
                    {
                        "path": "tests/test_patch_draft.py",
                        "edits": [{"old": "meaning(), 41", "new": "meaning(), 42"}],
                    },
                ],
            }

        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_13-deliberation-internalization",
                cleanup=False,
                ai=True,
                auth=None,
                model_backend="",
                model="",
                base_url="",
                model_timeout=60,
            )

            with patch("mew.dogfood.load_model_auth", side_effect=fake_load_model_auth):
                with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                    report = run_dogfood_scenario(args)

            scenario = report["scenarios"][0]
            artifacts = scenario["artifacts"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(observed_auth, [("codex", None)])
            self.assertEqual(artifacts["tiny_provider_mode"], "live_provider")
            self.assertEqual(artifacts["trace"]["evidence_class"], "live_provider_internalization_contract")
            self.assertTrue(artifacts["trace"]["close_evidence"])
            self.assertTrue(artifacts["trace"]["contract_cycle_proven"])

    def test_run_dogfood_m6_13_live_provider_requires_deliberation_result(self):
        def fake_load_model_auth(model_backend, auth_path=None):
            return {"access_token": "token"}

        def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
            return {
                "kind": "patch_proposal",
                "summary": "increment the paired meaning value",
                "files": [
                    {
                        "path": "src/mew/patch_draft.py",
                        "edits": [{"old": "return 41", "new": "return 42"}],
                    },
                    {
                        "path": "tests/test_patch_draft.py",
                        "edits": [{"old": "meaning(), 41", "new": "meaning(), 42"}],
                    },
                ],
            }

        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_13-deliberation-internalization",
                cleanup=False,
                ai=True,
                auth=None,
                model_backend="",
                model="",
                base_url="",
                model_timeout=60,
            )

            with patch("mew.dogfood.load_model_auth", side_effect=fake_load_model_auth):
                with patch("mew.work_loop._attempt_work_deliberation_lane", return_value={}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        report = run_dogfood_scenario(args)

            scenario = report["scenarios"][0]
            failed = {item["name"]: item for item in scenario["checks"] if not item["passed"]}

            self.assertEqual(report["status"], "fail")
            self.assertIn("m6_13_deliberation_internalization_records_deliberation_result", failed)
            self.assertEqual(
                failed["m6_13_deliberation_internalization_records_deliberation_result"]["observed"]["status"],
                "missing_live_result",
            )

    def test_run_dogfood_m6_9_repeated_task_recall_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_9-repeated-task-recall",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            artifacts = scenario["artifacts"]
            trace = artifacts["trace"]
            check_names = {item["name"] for item in scenario["checks"]}

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_9-repeated-task-recall")
            self.assertEqual(scenario["status"], "pass")
            self.assertIn("m6_9-repeated-task-recall: pass", text)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertTrue(artifacts["recall_shortened_deliberation"])
            self.assertEqual(artifacts["reviewer_rescue_edits"], 0)
            self.assertEqual(artifacts["shape_count"], 10)
            self.assertEqual(
                set(artifacts["task_shapes"]),
                {
                    "bounded_source_test_pair",
                    "bounded_symbol_index_pair",
                    "bounded_commands_pair",
                    "bounded_memory_explore_pair",
                    "bounded_context_checkpoint_pair",
                    "bounded_work_loop_pair",
                    "bounded_memory_pair",
                    "bounded_tasks_pair",
                    "bounded_runtime_pair",
                    "bounded_snapshot_pair",
                },
            )
            self.assertGreater(
                artifacts["repetition_1_deliberation_search_step_count"],
                artifacts["repetition_2_deliberation_search_step_count"],
            )
            self.assertEqual(len(artifacts["first_five_wall_seconds"]), 5)
            self.assertEqual(len(artifacts["first_five_deliberation_step_counts"]), 5)
            self.assertGreater(
                artifacts["first_five_wall_seconds"][0],
                sorted(artifacts["first_five_wall_seconds"][1:])[2],
            )
            self.assertGreater(
                artifacts["first_five_deliberation_step_counts"][0],
                sorted(artifacts["first_five_deliberation_step_counts"][1:])[2],
            )
            self.assertEqual(artifacts["resolved_source_path"], "src/mew/dogfood.py")
            self.assertEqual(artifacts["resolved_test_path"], "tests/test_dogfood.py")
            self.assertEqual(
                set(artifacts["per_shape_recalled_file_pair_counts"]),
                {
                    "bounded_source_test_pair",
                    "bounded_symbol_index_pair",
                    "bounded_commands_pair",
                    "bounded_memory_explore_pair",
                    "bounded_context_checkpoint_pair",
                    "bounded_work_loop_pair",
                    "bounded_memory_pair",
                    "bounded_tasks_pair",
                    "bounded_runtime_pair",
                    "bounded_snapshot_pair",
                },
            )
            self.assertEqual(
                set(artifacts["per_shape_first_five_wall_seconds"]),
                set(artifacts["per_shape_recalled_file_pair_counts"]),
            )
            self.assertEqual(
                set(artifacts["per_shape_first_five_deliberation_step_counts"]),
                set(artifacts["per_shape_recalled_file_pair_counts"]),
            )
            self.assertEqual(
                set(artifacts["per_shape_median_improvement"]),
                set(artifacts["per_shape_recalled_file_pair_counts"]),
            )
            self.assertTrue(all(count > 0 for count in artifacts["per_shape_recalled_file_pair_counts"].values()))
            self.assertTrue(
                all(len(values) == 5 for values in artifacts["per_shape_first_five_wall_seconds"].values())
            )
            self.assertTrue(
                all(
                    len(values) == 5
                    for values in artifacts["per_shape_first_five_deliberation_step_counts"].values()
                )
            )
            self.assertTrue(
                all(
                    improvement["wall_seconds"] and improvement["deliberation_step_count"]
                    for improvement in artifacts["per_shape_median_improvement"].values()
                )
            )
            self.assertEqual(trace["scenario"], "m6_9-repeated-task-recall")
            self.assertEqual(trace["shape_count"], 10)
            self.assertEqual(
                set(trace["task_shapes"]),
                {
                    "bounded_source_test_pair",
                    "bounded_symbol_index_pair",
                    "bounded_commands_pair",
                    "bounded_memory_explore_pair",
                    "bounded_context_checkpoint_pair",
                    "bounded_work_loop_pair",
                    "bounded_memory_pair",
                    "bounded_tasks_pair",
                    "bounded_runtime_pair",
                    "bounded_snapshot_pair",
                },
            )
            self.assertEqual(len(trace["repetitions"]), 5)
            self.assertEqual(len(trace["first_five_wall_seconds"]), 5)
            self.assertEqual(len(trace["first_five_deliberation_step_counts"]), 5)
            self.assertFalse(trace["repetitions"][0]["durable_recall_used"])
            self.assertTrue(trace["repetitions"][1]["durable_recall_used"])
            self.assertEqual(trace["repetitions"][1]["reviewer_rescue_edits"], 0)
            self.assertTrue(trace["recall_shortened_deliberation"])
            for shape_trace in trace["shapes"]:
                self.assertEqual(len(shape_trace["repetitions"]), 5)
                self.assertEqual(len(shape_trace["first_five_wall_seconds"]), 5)
                self.assertEqual(len(shape_trace["first_five_deliberation_step_counts"]), 5)
                self.assertFalse(shape_trace["repetitions"][0]["durable_recall_used"])
                self.assertTrue(shape_trace["repetitions"][1]["durable_recall_used"])
                self.assertGreater(
                    shape_trace["repetitions"][0]["deliberation_search_step_count"],
                    shape_trace["repetitions"][1]["deliberation_search_step_count"],
                )
                self.assertGreater(
                    shape_trace["first_five_wall_seconds"][0],
                    sorted(shape_trace["first_five_wall_seconds"][1:])[2],
                )
                self.assertGreater(
                    shape_trace["first_five_deliberation_step_counts"][0],
                    sorted(shape_trace["first_five_deliberation_step_counts"][1:])[2],
                )
                self.assertTrue(shape_trace["median_wall_seconds_improved"])
                self.assertTrue(shape_trace["median_deliberation_step_count_improved"])
                self.assertEqual(shape_trace["reviewer_rescue_edits"], 0)
                self.assertTrue(shape_trace["recall_shortened_deliberation"])
            self.assertEqual(trace["durable_index_evidence"]["kind"], "file-pair")
            self.assertEqual(trace["durable_index_evidence"]["source_path"], "src/mew/dogfood.py")
            self.assertEqual(trace["durable_index_evidence"]["test_path"], "tests/test_dogfood.py")
            self.assertIn("m6_9_repeated_task_recall_first_repetition_starts_without_durable_memory", check_names)
            self.assertIn("m6_9_repeated_task_recall_first_repetition_writes_typed_memory_index_evidence", check_names)
            self.assertIn("m6_9_repeated_task_recall_second_repetition_uses_durable_recall_index", check_names)
            self.assertIn("m6_9_repeated_task_recall_second_repetition_shortens_deliberation_without_rescue", check_names)
            self.assertIn("m6_9_repeated_task_recall_covers_multiple_task_shapes", check_names)
            self.assertIn("m6_9_repeated_task_recall_writes_deterministic_trace_artifact", check_names)

    def test_run_dogfood_m6_9_symbol_index_hit_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_9-symbol-index-hit",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            check_names = {item["name"] for item in scenario["checks"]}

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_9-symbol-index-hit")
            self.assertEqual(scenario["status"], "pass")
            self.assertIn("m6_9-symbol-index-hit: pass", text)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["symbol"], "M6_9_SYMBOL_INDEX_HIT_ANCHOR")
            self.assertTrue(scenario["artifacts"]["index_hit"])
            self.assertFalse(scenario["artifacts"]["fresh_search_performed"])
            self.assertEqual(scenario["artifacts"]["resolved_source_path"], "src/mew/dogfood.py")
            self.assertEqual(scenario["artifacts"]["resolved_test_path"], "tests/test_dogfood.py")
            self.assertEqual(scenario["artifacts"]["trace"]["index_hit"], True)
            self.assertEqual(scenario["artifacts"]["trace"]["fresh_search_performed"], False)
            self.assertEqual(scenario["artifacts"]["trace"]["resolved_source_path"], "src/mew/dogfood.py")
            self.assertEqual(scenario["artifacts"]["trace"]["resolved_test_path"], "tests/test_dogfood.py")
            self.assertIn("m6_9_symbol_index_hit_builds_durable_index", check_names)
            self.assertIn("m6_9_symbol_index_hit_first_read_source_lookup_uses_index", check_names)
            self.assertIn("m6_9_symbol_index_hit_resolves_expected_source_test_pair", check_names)
            self.assertIn("m6_9_symbol_index_hit_writes_deterministic_trace", check_names)

    def test_run_dogfood_m6_9_drift_canary_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_9-drift-canary",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            artifacts = scenario["artifacts"]
            novel_task = artifacts["novel_task_injection"]
            trace = artifacts["trace"]
            trace_json = json.loads(Path(artifacts["trace_path"]).read_text(encoding="utf-8"))
            check_names = {item["name"] for item in scenario["checks"]}

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_9-drift-canary")
            self.assertEqual(scenario["status"], "pass")
            self.assertIn("m6_9-drift-canary: pass", text)
            self.assertIn("m6_9_drift_canary_runs_five_green_iterations", text)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(artifacts["iterations_total"], 5)
            self.assertEqual(artifacts["drift_canary_green_count"], 5)
            self.assertTrue(artifacts["memory_accumulated"])
            self.assertTrue(novel_task["forced_exploration"])
            self.assertTrue(novel_task["unknown_memory_match"])
            self.assertTrue(novel_task["forced_source_read"])
            self.assertTrue(novel_task["forced_test_read"])
            self.assertFalse(novel_task["silent_memory_reliance"])
            self.assertTrue(novel_task["no_silent_memory_reliance"])
            self.assertEqual(novel_task["known_memory_matches"], [])
            self.assertIn("novel-task", novel_task["reviewer_visible_exploration_reason"])
            self.assertIn("reviewer-visible", novel_task["reviewer_visible_exploration_reason"])
            self.assertEqual(
                [item["decision"] for item in novel_task["exploration_decision_matrix"]],
                [
                    "unknown-memory match",
                    "forced source read",
                    "forced test read",
                    "no silent memory reliance",
                ],
            )
            self.assertEqual(trace["iterations_total"], 5)
            self.assertEqual(trace["drift_canary_green_count"], 5)
            self.assertTrue(trace["memory_accumulated"])
            self.assertEqual(trace_json["iterations_total"], 5)
            self.assertEqual(trace_json["drift_canary_green_count"], 5)
            self.assertTrue(trace_json["memory_accumulated"])
            self.assertTrue(trace_json["novel_task_injection"]["forced_exploration"])
            self.assertTrue(trace_json["novel_task_injection"]["forced_source_read"])
            self.assertTrue(trace_json["novel_task_injection"]["forced_test_read"])
            self.assertFalse(trace_json["novel_task_injection"]["silent_memory_reliance"])
            self.assertTrue(trace_json["novel_task_injection"]["no_silent_memory_reliance"])
            self.assertIn(
                "reviewer-visible",
                trace_json["novel_task_injection"]["reviewer_visible_exploration_reason"],
            )
            self.assertEqual(
                [item["memory_item_count"] for item in trace_json["iterations"]],
                [1, 2, 3, 4, 5],
            )
            self.assertIn("m6_9_drift_canary_runs_five_green_iterations", check_names)
            self.assertIn("m6_9_drift_canary_accumulates_memory", check_names)
            self.assertIn("m6_9_drift_canary_novel_task_forces_exploration", check_names)
            self.assertIn("m6_9_drift_canary_writes_deterministic_trace", check_names)

    def test_run_dogfood_m6_9_alignment_decay_rehearsal_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_9-alignment-decay-rehearsal",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            report_json = json.loads(json.dumps(report, sort_keys=True))
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            scenario_json = report_json["scenarios"][0]
            artifacts = scenario["artifacts"]
            trace = artifacts["trace"]
            trace_json = json.loads(Path(artifacts["trace_path"]).read_text(encoding="utf-8"))
            check_names = {item["name"] for item in scenario["checks"]}

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report_json["status"], "pass")
            self.assertEqual(scenario["name"], "m6_9-alignment-decay-rehearsal")
            self.assertEqual(scenario_json["name"], "m6_9-alignment-decay-rehearsal")
            self.assertEqual(scenario["status"], "pass")
            self.assertIn("m6_9-alignment-decay-rehearsal: pass", text)
            self.assertIn("m6_9_alignment_decay_rehearsal_recovers_prior_conventions_without_steering", text)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertTrue(artifacts["simulated_gap_or_decay"])
            self.assertTrue(artifacts["rehearsal_pass_ran"])
            self.assertEqual(artifacts["recovered_within_iterations"], 1)
            self.assertFalse(artifacts["reviewer_steering_required"])
            self.assertTrue(artifacts["prior_convention_reused"])
            self.assertTrue(scenario_json["artifacts"]["simulated_gap_or_decay"])
            self.assertTrue(scenario_json["artifacts"]["rehearsal_pass_ran"])
            self.assertEqual(scenario_json["artifacts"]["recovered_within_iterations"], 1)
            self.assertFalse(scenario_json["artifacts"]["reviewer_steering_required"])
            self.assertTrue(scenario_json["artifacts"]["prior_convention_reused"])
            for payload in (trace, trace_json, scenario_json["artifacts"]["trace"]):
                self.assertEqual(payload["scenario"], "m6_9-alignment-decay-rehearsal")
                self.assertTrue(payload["simulated_gap_or_decay"])
                self.assertTrue(payload["rehearsal_pass_ran"])
                self.assertEqual(payload["recovered_within_iterations"], 1)
                self.assertFalse(payload["reviewer_steering_required"])
                self.assertTrue(payload["prior_convention_reused"])
                self.assertEqual(payload["gap_or_decay"]["available_conventions_after_decay"], [])
                self.assertEqual([item["iteration"] for item in payload["iterations"]], [1])
            self.assertIn("m6_9_alignment_decay_rehearsal_simulates_gap_or_decay", check_names)
            self.assertIn("m6_9_alignment_decay_rehearsal_runs_rehearsal_pass", check_names)
            self.assertIn("m6_9_alignment_decay_rehearsal_recovers_prior_conventions_without_steering", check_names)
            self.assertIn("m6_9_alignment_decay_rehearsal_writes_deterministic_trace", check_names)

    def test_run_dogfood_m6_11_compiler_replay_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_11-compiler-replay",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_11-compiler-replay")
            self.assertEqual(scenario["status"], "pass")
            self.assertEqual(scenario["command_count"], 0)
            self.assertIn("m6_11-compiler-replay: pass", text)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["fixture_count"], 3)
            self.assertIn("paired_src_test_happy", scenario["artifacts"]["fixtures"])
            self.assertIn(
                "m6_11_compiler_replay_paired_src_test_happy_kind",
                {item["name"] for item in scenario["checks"]},
            )
            self.assertIn(
                "m6_11_compiler_replay_paired_src_test_happy_validator_version",
                {item["name"] for item in scenario["checks"]},
            )
            self.assertIn(
                "m6_11_compiler_replay_paired_src_test_happy_artifact_id",
                {item["name"] for item in scenario["checks"]},
            )
            self.assertIn(
                "m6_11_compiler_replay_paired_src_test_happy_file_paths",
                {item["name"] for item in scenario["checks"]},
            )
            self.assertIn(
                "m6_11_compiler_replay_paired_src_test_happy_file_0_window_sha256s",
                {item["name"] for item in scenario["checks"]},
            )
            self.assertIn(
                "m6_11_compiler_replay_paired_src_test_happy_file_0_pre_file_sha256",
                {item["name"] for item in scenario["checks"]},
            )
            self.assertIn(
                "m6_11_compiler_replay_paired_src_test_happy_file_0_post_file_sha256",
                {item["name"] for item in scenario["checks"]},
            )
            self.assertIn(
                "m6_11_compiler_replay_stale_cached_window_text_recovery_action",
                {item["name"] for item in scenario["checks"]},
            )

    def test_run_dogfood_m6_24_terminal_bench_replay_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_24-terminal-bench-replay",
                cleanup=False,
                terminal_bench_job_dir=None,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_24-terminal-bench-replay")
            self.assertEqual(scenario["status"], "pass")
            self.assertEqual(scenario["command_count"], 0)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["replay_status"], "pass")
            self.assertEqual(scenario["artifacts"]["trial_count"], 1)
            self.assertIn("compatibility_override_probe_missing", scenario["artifacts"]["current_long_build"]["strategy_blockers"])
            self.assertIn("m6_24-terminal-bench-replay: pass", text)

    def test_run_dogfood_m6_24_terminal_bench_replay_scenario_accepts_external_assertions(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _write_terminal_bench_replay_fixture(Path(tmp) / "fixture")
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_24-terminal-bench-replay",
                cleanup=False,
                terminal_bench_job_dir=str(fixture),
                terminal_bench_assert_long_build_status="blocked",
                terminal_bench_assert_current_failure="dependency_strategy_unresolved",
                terminal_bench_assert_blocker=["compatibility_override_probe_missing"],
                terminal_bench_assert_mew_exit_code=1,
                terminal_bench_assert_external_reward=0.0,
            )

            report = run_dogfood_scenario(args)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["status"], "pass")
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["replay_status"], "pass")
            self.assertEqual(
                scenario["artifacts"]["current_long_build"]["current_failure_class"],
                "dependency_strategy_unresolved",
            )

    def test_run_dogfood_m6_24_terminal_bench_replay_scenario_accepts_non_compile_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _write_terminal_bench_replay_fixture(Path(tmp) / "fixture", task="build-cython-ext")
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_24-terminal-bench-replay",
                cleanup=False,
                terminal_bench_job_dir=str(fixture),
                terminal_bench_task="build-cython-ext",
                terminal_bench_assert_mew_exit_code=1,
                terminal_bench_assert_external_reward=0.0,
            )

            report = run_dogfood_scenario(args)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["status"], "pass")
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["task"], "build-cython-ext")
            self.assertEqual(scenario["artifacts"]["first_trial"], "build-cython-ext__fixture")

    def test_run_dogfood_m6_24_terminal_bench_replay_scenario_accepts_next_action_assertion(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _write_repository_test_tail_emulator_fixture(Path(tmp) / "fixture", task="build-cython-ext")
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_24-terminal-bench-replay",
                cleanup=False,
                terminal_bench_job_dir=str(fixture),
                terminal_bench_task="build-cython-ext",
                terminal_bench_assert_mew_exit_code=1,
                terminal_bench_assert_external_reward=0.0,
                terminal_bench_assert_next_action_contains="numpy.int",
            )

            report = run_dogfood_scenario(args)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["status"], "pass")
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))

    def test_run_dogfood_m6_24_compile_compcert_emulator_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_24-compile-compcert-emulator",
                cleanup=False,
                terminal_bench_job_dir=None,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_24-compile-compcert-emulator")
            self.assertEqual(scenario["status"], "pass")
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["replay_status"], "pass")
            self.assertGreaterEqual(scenario["artifacts"]["llm_action_fixture_count"], 1)
            self.assertTrue(Path(scenario["artifacts"]["fixture_path"]).is_file())
            self.assertTrue(scenario["artifacts"]["budget_policy"]["diagnostic_budget"])
            self.assertEqual(scenario["artifacts"]["budget_policy"]["minimum_timeout_seconds"], 30.0)
            self.assertEqual(scenario["artifacts"]["ceiling"], {})
            self.assertIn("m6_24-compile-compcert-emulator: pass", text)

    def test_run_dogfood_m6_24_repository_test_tail_emulator_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_24-repository-test-tail-emulator",
                cleanup=False,
                terminal_bench_job_dir=None,
                terminal_bench_task=None,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_24-repository-test-tail-emulator")
            self.assertEqual(scenario["status"], "pass")
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["replay_status"], "pass")
            self.assertEqual(scenario["artifacts"]["task"], "build-cython-ext")
            self.assertTrue(scenario["artifacts"]["summary"]["repository_tail_failed"])
            self.assertTrue(scenario["artifacts"]["summary"]["upstream_tail_failed"])
            self.assertTrue(scenario["artifacts"]["summary"]["main_smoke_passed"])
            self.assertEqual(scenario["artifacts"]["summary"]["stop_reason"], "wall_timeout")
            self.assertTrue(scenario["artifacts"]["first_trial"]["current"]["active_compatibility_frontier"]["signature"])
            self.assertTrue(
                scenario["artifacts"]["first_trial"]["current"]["active_compatibility_frontier"]["next_action"]
            )
            self.assertGreaterEqual(
                scenario["artifacts"]["first_trial"]["current"]["active_compatibility_frontier"]["open_candidate_count"],
                1,
            )
            self.assertFalse(scenario["artifacts"]["managed_action_projection"]["lifecycle_lost"])
            self.assertFalse(scenario["artifacts"]["managed_action_projection"]["managed_lost"])
            self.assertFalse(scenario["artifacts"]["managed_action_projection"]["runtime_identity_mismatches"])
            self.assertFalse(scenario["artifacts"]["managed_action_projection"]["lifecycle_parameter_pollution"])
            self.assertTrue(Path(scenario["artifacts"]["fixture_path"]).is_file())
            self.assertIn("m6_24-repository-test-tail-emulator: pass", text)

    def test_run_dogfood_m6_24_repository_test_tail_emulator_accepts_historical_artifact_without_stored_frontier(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_dir = _write_repository_test_tail_emulator_fixture(root, task="build-cython-ext")
            report_path = next(Path(job_dir).rglob("mew-report.json"))
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            payload["resume"].pop("active_compatibility_frontier", None)
            report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            args = SimpleNamespace(
                workspace=str(root / "dog"),
                scenario="m6_24-repository-test-tail-emulator",
                cleanup=False,
                terminal_bench_job_dir=str(job_dir),
                terminal_bench_task="build-cython-ext",
            )

            report = run_dogfood_scenario(args)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["status"], "pass")
            self.assertTrue(
                scenario["artifacts"]["first_trial"]["current"]["active_compatibility_frontier"]["signature"]
            )
            self.assertEqual(
                scenario["artifacts"]["first_trial"]["stored"].get("active_compatibility_frontier"),
                {},
            )

    def test_run_dogfood_m6_24_repository_test_tail_emulator_accepts_historical_finish_false_positive(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_dir = _write_repository_test_tail_emulator_fixture(root, task="build-cython-ext")
            report_path = next(Path(job_dir).rglob("mew-report.json"))
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            payload["work_exit_code"] = 0
            payload["resume"].pop("active_compatibility_frontier", None)
            payload["work_report"]["stop_reason"] = "finish"
            payload["work_report"]["wall_timeout"] = False
            report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            args = SimpleNamespace(
                workspace=str(root / "dog"),
                scenario="m6_24-repository-test-tail-emulator",
                cleanup=False,
                terminal_bench_job_dir=str(job_dir),
                terminal_bench_task="build-cython-ext",
            )

            report = run_dogfood_scenario(args)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["status"], "pass")
            self.assertTrue(scenario["artifacts"]["summary"]["finish_false_positive"])

    def test_run_dogfood_m6_24_repository_test_tail_emulator_preserves_stored_frontier_for_finish_false_positive(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_dir = _write_repository_test_tail_emulator_fixture(root, task="build-cython-ext")
            report_path = next(Path(job_dir).rglob("mew-report.json"))
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            payload["work_exit_code"] = 0
            payload["work_report"]["stop_reason"] = "finish"
            payload["work_report"]["wall_timeout"] = False
            report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            args = SimpleNamespace(
                workspace=str(root / "dog"),
                scenario="m6_24-repository-test-tail-emulator",
                cleanup=False,
                terminal_bench_job_dir=str(job_dir),
                terminal_bench_task="build-cython-ext",
            )

            report = run_dogfood_scenario(args)
            scenario = report["scenarios"][0]
            first_trial = scenario["artifacts"]["first_trial"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["status"], "pass")
            self.assertTrue(scenario["artifacts"]["summary"]["finish_false_positive"])
            self.assertEqual(
                first_trial["current"]["active_compatibility_frontier"]["signature"],
                first_trial["stored"]["active_compatibility_frontier"]["signature"],
            )
            self.assertGreater(
                first_trial["stored"]["active_compatibility_frontier"]["evidence_ref_count"],
                0,
            )

    def test_run_dogfood_m6_24_repository_test_tail_emulator_rejects_malformed_stored_frontier_for_finish_false_positive(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_dir = _write_repository_test_tail_emulator_fixture(root, task="build-cython-ext")
            report_path = next(Path(job_dir).rglob("mew-report.json"))
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            payload["work_exit_code"] = 0
            payload["work_report"]["stop_reason"] = "finish"
            payload["work_report"]["wall_timeout"] = False
            frontier = payload["resume"]["active_compatibility_frontier"]
            frontier["failure_signature"]["family_key"] = ""
            frontier["evidence_refs"] = []
            frontier["sibling_candidates"] = []
            frontier["compact_summary"]["open_candidates"] = []
            frontier["compact_summary"]["evidence_refs"] = []
            report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            args = SimpleNamespace(
                workspace=str(root / "dog"),
                scenario="m6_24-repository-test-tail-emulator",
                cleanup=False,
                terminal_bench_job_dir=str(job_dir),
                terminal_bench_task="build-cython-ext",
            )

            report = run_dogfood_scenario(args)
            scenario = report["scenarios"][0]
            preserve_check = next(
                item
                for item in scenario["checks"]
                if item["name"] == "m6_24_repository_test_tail_emulator_preserves_active_frontier"
            )

            self.assertEqual(report["status"], "fail")
            self.assertFalse(preserve_check["passed"])

    def test_run_dogfood_m6_24_final_verifier_budget_emulator_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_dir = _write_repository_test_tail_emulator_fixture(root, task="build-cython-ext")
            report_path = next(Path(job_dir).rglob("mew-report.json"))
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            final_command = (
                "cd /tmp && python - <<'PY'\n"
                "import pyknotid\n"
                "from pyknotid.spacecurves import chelpers, ccomplexity\n"
                "from pyknotid import cinvariants\n"
                "print('final smoke')\n"
                "PY\n"
                "python -m pytest -q /app/pyknotid/tests "
                "--ignore=/app/pyknotid/tests/test_random_curves.py "
                "--ignore=/app/pyknotid/tests/test_catalogue.py"
            )
            final_contract = {
                "schema_version": 2,
                "purpose": "verification",
                "stage": "verification",
                "proof_role": "verifier",
                "acceptance_kind": "candidate_final_proof",
                "risk_class": "read_only",
                "continuation_policy": {
                    "mode": "managed",
                    "resume_policy": "same_resume_identity",
                    "terminal_required_for_acceptance": True,
                    "yield_after_seconds": 60,
                    "final_proof_reserve_seconds": 60,
                },
                "source_authority_requirement": {"mode": "consumes_authority", "required": True},
                "declared_target_refs": [
                    {"kind": "source_tree", "path": "/app/pyknotid", "ref": "source-tree:primary"},
                    {
                        "kind": "artifact",
                        "path": "/usr/local/lib/python3.13/site-packages/pyknotid",
                        "ref": "global-python-install",
                    },
                ],
            }
            raw_action = {
                "type": "run_tests",
                "cwd": "/app",
                "command": final_command,
                "timeout": 180,
                "foreground_budget_seconds": 60,
                "execution_contract": final_contract,
                "task_done": False,
            }
            blocked_action = dict(raw_action)
            blocked_action.update(
                {
                    "timeout": 4.658,
                    "long_command_budget": {
                        "action_kind": "start_long_command",
                        "stage": "verification",
                        "requested_timeout_seconds": 180.0,
                        "effective_timeout_seconds": 4.658,
                        "minimum_timeout_seconds": 61.0,
                        "diagnostic_budget": False,
                    },
                    "wall_timeout_ceiling": {
                        "blocked": True,
                        "stop_reason": "long_command_budget_blocked",
                        "reason": "long-command effective timeout cannot satisfy yield_after < effective_timeout_seconds",
                        "available_tool_timeout_seconds": 4.658,
                        "remaining_seconds": 64.658,
                        "reserve_seconds": 60.0,
                    },
                }
            )
            payload["work_report"]["stop_reason"] = "long_command_budget_blocked"
            payload["work_report"]["wall_timeout"] = True
            payload["resume"]["active_compatibility_frontier"] = {}
            payload["resume"]["next_action"] = "verify the world and review side-effecting work before retry"
            payload["work_report"]["steps"].append(
                {
                    "index": 3,
                    "status": "blocked",
                    "action": {"type": "wait", "reason": blocked_action["wall_timeout_ceiling"]["reason"]},
                    "model_turn": {
                        "id": 3,
                        "status": "failed",
                        "error": blocked_action["wall_timeout_ceiling"]["reason"],
                        "action_plan": {
                            "summary": "Run the final verifier after repair and smoke evidence.",
                            "action": raw_action,
                        },
                        "action": {
                            "type": "wait",
                            "reason": blocked_action["wall_timeout_ceiling"]["reason"],
                            "blocked_action": blocked_action,
                        },
                    },
                    "wall_timeout": blocked_action["wall_timeout_ceiling"],
                }
            )
            report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            args = SimpleNamespace(
                workspace=str(root / "dog"),
                scenario="m6_24-final-verifier-budget-emulator",
                cleanup=False,
                terminal_bench_job_dir=str(job_dir),
                terminal_bench_task="build-cython-ext",
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_24-final-verifier-budget-emulator")
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["replay_status"], "pass")
            self.assertEqual(scenario["artifacts"]["summary"]["stop_reason"], "long_command_budget_blocked")
            self.assertEqual(scenario["artifacts"]["summary"]["stage"], "verification")
            self.assertEqual(scenario["artifacts"]["summary"]["proof_role"], "verifier")
            self.assertTrue(Path(scenario["artifacts"]["fixture_path"]).is_file())
            self.assertIn("m6_24-final-verifier-budget-emulator: pass", text)

    def test_run_dogfood_m6_24_same_family_compatibility_emulator_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_24-same-family-compatibility-emulator",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_24-same-family-compatibility-emulator")
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["frontier"]["signature"], "same-family-frontier-fixture")
            self.assertEqual(scenario["artifacts"]["guard_decision"]["blocked_action_kind"], "broad_verifier")
            self.assertEqual(scenario["artifacts"]["replacement_action"]["type"], "read_file")

    def test_run_dogfood_m6_24_runtime_finish_gate_emulator_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_24-runtime-finish-gate-emulator",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_24-runtime-finish-gate-emulator")
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["import_only_decision"]["decision"], "block_continue")
            self.assertEqual(scenario["artifacts"]["behavior_decision"]["decision"], "allow_complete")

    def test_run_dogfood_m6_24_implement_v2_terminal_failure_reaction_emulator_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_24-implement-v2-terminal-failure-reaction-emulator",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_24-implement-v2-terminal-failure-reaction-emulator")
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertEqual(scenario["artifacts"]["status"], "completed")
            self.assertEqual(scenario["artifacts"]["first_tool_result_status"], "failed")
            self.assertEqual(scenario["artifacts"]["metrics"]["terminal_failure_reaction_turns_used"], 1)
            self.assertEqual(scenario["artifacts"]["metrics"]["command_closeout_count"], 1)
            self.assertTrue(Path(scenario["artifacts"]["repair_artifact"]).is_file())

    def test_m6_24_projection_detects_lifecycle_parameter_pollution(self):
        projection = _evaluate_managed_action_projection(
            [
                {
                    "report_path": "report.json",
                    "fixture": {
                        "raw_action": {
                            "type": "poll_command",
                            "command_run_id": "work_session:1:command_run:1",
                        },
                        "post_policy_action": {
                            "type": "poll_command",
                            "command_run_id": "work_session:1:command_run:1",
                        },
                    },
                    "session": {
                        "tool_calls": [
                            {
                                "id": 1,
                                "tool": "poll_command",
                                "parameters": {
                                    "command_run_id": "work_session:1:command_run:1",
                                    "cwd": "/app",
                                    "allow_shell": True,
                                    "allow_verify": True,
                                },
                            },
                            {
                                "id": 2,
                                "tool": "read_command_output",
                                "parameters": {
                                    "command_run_id": "work_session:1:command_run:1",
                                    "output_ref": "work-session/1/command/1/output.log",
                                    "allowed_write_roots": [],
                                    "cwd": "/app",
                                },
                            },
                            {
                                "id": 3,
                                "tool": "cancel_command",
                                "parameters": {
                                    "command_run_id": "work_session:1:command_run:1",
                                    "verify_cwd": "/app",
                                },
                            }
                        ]
                    },
                }
            ]
        )

        self.assertEqual(
            projection["lifecycle_parameter_pollution"],
            [
                {
                    "tool_call_id": 1,
                    "tool": "poll_command",
                    "polluted_keys": ["allow_shell", "allow_verify", "cwd"],
                },
                {
                    "tool_call_id": 2,
                    "tool": "read_command_output",
                    "polluted_keys": ["allowed_write_roots", "cwd"],
                },
                {
                    "tool_call_id": 3,
                    "tool": "cancel_command",
                    "polluted_keys": ["verify_cwd"],
                }
            ],
        )

    def test_m6_24_repository_summary_detects_finish_false_positive(self):
        stdout = """
PASSED ../tests/test_outputs.py::test_example_usage
FAILED ../tests/test_outputs.py::test_ccomplexity - AttributeError: module 'numpy' has no attribute 'int'
========================= 1 failed, 10 passed in 3.92s =========================
"""
        summary = _repository_test_tail_summary(
            stdout,
            {
                "trial_name": "build-cython-ext__wPScYFt",
                "external_reward": 0.0,
                "mew_exit_code": 0,
                "stop_reason": "finish",
                "wall_timeout": False,
            },
        )

        self.assertTrue(summary["finish_false_positive"])
        self.assertFalse(summary["repository_tail_failed"])
        self.assertEqual(summary["failed_count"], 1)
        self.assertIn("../tests/test_outputs.py::test_ccomplexity", summary["failed_tests"])

    def test_m6_24_repository_summary_does_not_treat_passed_repository_test_as_tail_failure(self):
        stdout = """
PASSED ../tests/test_outputs.py::test_pyknotid_repository_tests
FAILED ../tests/test_outputs.py::test_ccomplexity - AttributeError: module 'numpy' has no attribute 'int'
========================= 1 failed, 10 passed in 3.92s =========================
"""
        summary = _repository_test_tail_summary(
            stdout,
            {
                "trial_name": "build-cython-ext__wPScYFt",
                "external_reward": 0.0,
                "mew_exit_code": 0,
                "stop_reason": "finish",
                "wall_timeout": False,
            },
        )

        self.assertTrue(summary["finish_false_positive"])
        self.assertFalse(summary["repository_tail_failed"])
        self.assertFalse(summary["upstream_tail_failed"])

    def test_run_dogfood_m6_11_draft_timeout_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_11-draft-timeout",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_11-draft-timeout")
            self.assertEqual(scenario["status"], "pass")
            self.assertEqual(scenario["artifacts"]["resume_source"], "session_overlay")
            self.assertIs(scenario["artifacts"]["session_state_newer"], False)
            self.assertEqual(scenario["artifacts"]["follow_status"], "stale")
            self.assertEqual(scenario["artifacts"]["next_recovery_action"], "resume_draft_from_cached_windows")
            self.assertEqual(scenario["artifacts"]["recovery_plan_item_action"], "resume_draft_from_cached_windows")
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertIn("m6_11_draft_timeout_scenario_command_succeeds", {item["name"] for item in scenario["checks"]})
            self.assertIn("m6_11-draft-timeout: pass", text)

    def test_run_dogfood_m6_11_drafting_recovery_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_11-drafting-recovery",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_11-drafting-recovery")
            self.assertEqual(scenario["status"], "pass")
            self.assertIn("m6_11-drafting-recovery: pass", text)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertTrue(scenario["artifacts"]["blocker_code"])
            self.assertTrue(scenario["artifacts"]["blocker_detail"])
            self.assertTrue(scenario["artifacts"]["next_recovery_action"])
            self.assertTrue(scenario["artifacts"]["next_action"])
            self.assertTrue(scenario["artifacts"]["todo_id"])
            self.assertEqual(scenario["artifacts"]["resume_source"], "session_overlay")
            self.assertIs(scenario["artifacts"]["session_state_newer"], False)
            self.assertEqual(scenario["artifacts"]["follow_status"], "stale")
            self.assertEqual(scenario["artifacts"]["suggested_recovery_kind"], "needs_human_review")

    def test_run_dogfood_m6_11_refusal_separation_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_11-refusal-separation",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_11-refusal-separation")
            self.assertEqual(scenario["status"], "pass")
            self.assertEqual(scenario["command_count"], 1)
            self.assertEqual(scenario["artifacts"]["resume_source"], "session_overlay")
            self.assertIs(scenario["artifacts"]["session_state_newer"], False)
            self.assertEqual(scenario["artifacts"]["next_recovery_action"], "inspect_refusal")
            self.assertEqual(scenario["artifacts"]["recovery_plan_item_action"], "needs_user_review")
            self.assertTrue(scenario["artifacts"]["blocker_code"])
            self.assertTrue(scenario["artifacts"]["blocker_detail"])
            self.assertEqual(scenario["artifacts"]["blocker_code"], "model_returned_refusal")
            self.assertEqual(scenario["artifacts"]["suggested_recovery_kind"], "needs_human_review")
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertIn("m6_11_refusal_separation_phase_is_blocked_on_patch", {item["name"] for item in scenario["checks"]})
            self.assertIn("m6_11-refusal-separation: pass", text)

    def test_run_dogfood_m6_11_phase4_regression_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_11-phase4-regression",
                cleanup=False,
            )
            fixture_path = (
                Path(__file__).resolve().parents[1]
                / "tests"
                / "fixtures"
                / "work_loop"
                / "phase4_regression"
                / "m6_6_comparator_budget"
                / "scenario.json"
            )
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            artifacts = scenario["artifacts"]
            fixture_b0 = (fixture.get("B0") or {}).get("iter_wall")
            comparator_cases = fixture.get("comparator_cases", [])
            expected_mapping = {
                "M6.6-A": "M6.6-A",
                "M6.6-B": "M6.6-B",
                "M6.6-C": "M6.6-C",
            }
            expected_provenance = {
                item.get("case_id"): item.get("source_reference") for item in comparator_cases
            }

            case_walls = [case.get("iter_wall_seconds") for case in comparator_cases]
            median_wall = sorted(case_walls)[len(case_walls) // 2]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_11-phase4-regression")
            self.assertEqual(scenario["status"], "pass")
            self.assertEqual(scenario["command_count"], 0)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertIn("m6_11-phase4-regression: pass", text)
            self.assertEqual(artifacts["b0_iter_wall_seconds"], fixture_b0)
            self.assertEqual(artifacts["budget_wall_seconds"], fixture_b0 * 1.10)
            self.assertEqual(artifacts["median_wall_seconds"], median_wall)
            self.assertEqual(
                {case.get("case_id"): case.get("shape") for case in artifacts["comparator_cases"]},
                expected_mapping,
            )
            self.assertEqual(
                {case.get("case_id"): case.get("source_reference") for case in artifacts["comparator_cases"]},
                expected_provenance,
            )
            self.assertEqual(len(artifacts["comparator_cases"]), 3)

    def test_run_dogfood_m6_9_phase1_regression_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_9-phase1-regression",
                cleanup=False,
            )
            fixture_path = (
                Path(__file__).resolve().parents[1]
                / "tests"
                / "fixtures"
                / "work_loop"
                / "phase4_regression"
                / "m6_6_comparator_budget"
                / "scenario.json"
            )
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            artifacts = scenario["artifacts"]
            fixture_b0 = (fixture.get("B0") or {}).get("iter_wall")
            comparator_cases = fixture.get("comparator_cases", [])
            expected_mapping = {
                "M6.6-A": "M6.6-A",
                "M6.6-B": "M6.6-B",
                "M6.6-C": "M6.6-C",
            }
            expected_provenance = {
                item.get("case_id"): item.get("source_reference") for item in comparator_cases
            }
            case_walls = [case.get("iter_wall_seconds") for case in comparator_cases]
            median_wall = sorted(case_walls)[len(case_walls) // 2]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_9-phase1-regression")
            self.assertEqual(scenario["status"], "pass")
            self.assertEqual(scenario["command_count"], 0)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertIn("m6_9-phase1-regression: pass", text)
            self.assertEqual(artifacts["phase"], "phase1")
            self.assertEqual(artifacts["comparator_source"], "m6_6")
            self.assertTrue(artifacts["durable_recall_active"])
            self.assertEqual(artifacts["b0_comparator_wall_seconds"], fixture_b0)
            self.assertEqual(artifacts["budget_wall_seconds"], fixture_b0 * 1.15)
            self.assertEqual(artifacts["median_wall_seconds"], median_wall)
            self.assertEqual(
                {case.get("case_id"): case.get("shape") for case in artifacts["comparator_cases"]},
                expected_mapping,
            )
            self.assertEqual(
                {case.get("case_id"): case.get("source_reference") for case in artifacts["comparator_cases"]},
                expected_provenance,
            )
            self.assertEqual(len(artifacts["comparator_cases"]), 3)

    def test_run_dogfood_m6_9_phase2_regression_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m6_9-phase2-regression",
                cleanup=False,
            )
            fixture_path = (
                Path(__file__).resolve().parents[1]
                / "tests"
                / "fixtures"
                / "work_loop"
                / "phase4_regression"
                / "m6_6_comparator_budget"
                / "scenario.json"
            )
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            artifacts = scenario["artifacts"]
            fixture_b0 = (fixture.get("B0") or {}).get("iter_wall")
            comparator_cases = fixture.get("comparator_cases", [])
            expected_mapping = {
                "M6.6-A": "M6.6-A",
                "M6.6-B": "M6.6-B",
                "M6.6-C": "M6.6-C",
            }
            expected_provenance = {
                item.get("case_id"): item.get("source_reference") for item in comparator_cases
            }
            case_walls = [case.get("iter_wall_seconds") for case in comparator_cases]
            median_wall = sorted(case_walls)[len(case_walls) // 2]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m6_9-phase2-regression")
            self.assertEqual(scenario["status"], "pass")
            self.assertEqual(scenario["command_count"], 0)
            self.assertTrue(all(item["passed"] for item in scenario["checks"]))
            self.assertIn("m6_9-phase2-regression: pass", text)
            self.assertEqual(artifacts["phase"], "phase2")
            self.assertEqual(artifacts["comparator_source"], "m6_6")
            self.assertTrue(artifacts["durable_recall_active"])
            self.assertEqual(artifacts["budget_multiplier"], 1.0)
            self.assertEqual(artifacts["b0_comparator_wall_seconds"], fixture_b0)
            self.assertEqual(artifacts["budget_wall_seconds"], fixture_b0)
            self.assertEqual(artifacts["median_wall_seconds"], median_wall)
            self.assertLessEqual(artifacts["median_wall_seconds"], artifacts["b0_comparator_wall_seconds"])
            self.assertEqual(
                {case.get("case_id"): case.get("shape") for case in artifacts["comparator_cases"]},
                expected_mapping,
            )
            self.assertEqual(
                {case.get("case_id"): case.get("source_reference") for case in artifacts["comparator_cases"]},
                expected_provenance,
            )
            self.assertEqual(len(artifacts["comparator_cases"]), 3)

    def test_run_dogfood_m6_11_all_subset_aggregate_reflects_full_coverage(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "mew.dogfood.DOGFOOD_SCENARIOS",
                (
                    "m6_11-compiler-replay",
                    "m6_11-drafting-recovery",
                    "m6_11-draft-timeout",
                    "m6_11-refusal-separation",
                    "m6_11-phase4-regression",
                ),
            ):
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="all",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            by_name = {scenario["name"]: scenario for scenario in report["scenarios"]}

            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                set(by_name),
                {
                    "m6_11-compiler-replay",
                    "m6_11-drafting-recovery",
                    "m6_11-draft-timeout",
                    "m6_11-refusal-separation",
                    "m6_11-phase4-regression",
                },
            )
            self.assertEqual(by_name["m6_11-compiler-replay"]["status"], "pass")
            self.assertEqual(by_name["m6_11-drafting-recovery"]["status"], "pass")
            self.assertEqual(by_name["m6_11-draft-timeout"]["status"], "pass")
            self.assertEqual(by_name["m6_11-refusal-separation"]["status"], "pass")
            self.assertEqual(by_name["m6_11-phase4-regression"]["status"], "pass")
            self.assertIn("m6_11-compiler-replay: pass", text)
            self.assertIn("m6_11-draft-timeout: pass", text)
            self.assertIn("m6_11-drafting-recovery: pass", text)
            self.assertIn("m6_11-refusal-separation: pass", text)
            self.assertIn("m6_11-phase4-regression: pass", text)

    def test_run_dogfood_native_advance_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="native-advance",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "native-advance")
            self.assertIn("native_advance_invokes_mew_work_live_once_per_tick", text)
            self.assertIn("native_advance_pending_approval_records_recovery_hint", text)

    def test_run_dogfood_passive_recovery_loop_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="passive-recovery-loop",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "passive-recovery-loop")
            self.assertIn("passive_recovery_loop_recovers_interrupted_verifier", text)
            self.assertIn("passive_recovery_loop_resumes_native_advance", text)

    def test_run_dogfood_passive_auto_recovery_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="passive-auto-recovery",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "passive-auto-recovery")
            self.assertIn("passive_auto_recovery_reruns_interrupted_verifier", text)
            self.assertIn("passive_auto_recovery_resumes_native_advance", text)

    def test_run_dogfood_passive_auto_recovery_read_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="passive-auto-recovery-read",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "passive-auto-recovery-read")
            self.assertIn("passive_auto_recovery_read_reruns_interrupted_read", text)
            self.assertIn("passive_auto_recovery_read_resumes_native_advance", text)

    def test_run_dogfood_passive_auto_recovery_write_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="passive-auto-recovery-write",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "passive-auto-recovery-write")
            self.assertIn("passive_auto_recovery_write_reruns_interrupted_dry_run_preview", text)

    def test_run_dogfood_m4_file_write_recovery_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m4-file-write-recovery",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "m4-file-write-recovery")
            self.assertIn("m4_file_write_recovery_retries_not_started_apply_write", text)
            self.assertIn("m4_file_write_recovery_skips_completed_write_and_verifies", text)
            self.assertIn("m4_file_write_recovery_reports_target_diverged_review", text)
            self.assertIn("m4_file_write_recovery_reports_partial_review", text)
            self.assertIn("m4_file_write_recovery_reports_rollback_needed_review", text)

    def test_run_dogfood_m4_runtime_effect_recovery_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m4-runtime-effect-recovery",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "m4-runtime-effect-recovery")
            self.assertIn("m4_runtime_effect_recovery_doctor_previews_decisions", text)
            self.assertIn("m4_runtime_effect_recovery_requeues_precommit_event", text)
            self.assertIn("m4_runtime_effect_recovery_classifies_committing_write_review", text)
            self.assertIn("m4_runtime_effect_recovery_classifies_committing_verification_review", text)
            self.assertIn("m4_runtime_effect_recovery_requeues_not_started_write_intent", text)
            self.assertIn("m4_runtime_effect_recovery_reviews_completed_write_intent", text)
            self.assertIn("m4_runtime_effect_recovery_seeds_review_question", text)

    def test_run_dogfood_m4_close_gate_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m4-close-gate",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "m4-close-gate")
            self.assertIn("m4_close_gate_runtime_write_intent_auto_requeued", text)
            self.assertIn("m4_close_gate_verifier_auto_retried_and_superseded", text)
            self.assertIn("m4_close_gate_durable_approval_visible_in_focus_and_brief", text)
            self.assertIn("m4_close_gate_completed_external_write_stays_on_review", text)
            self.assertIn("m4_close_gate_no_manual_reconstruction_required", text)

    def test_run_dogfood_day_reentry_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="day-reentry",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "day-reentry")
            artifacts = report["scenarios"][0]["artifacts"]
            self.assertEqual(artifacts["synthetic_age_days"], 7)
            self.assertGreaterEqual(artifacts["observed_inactive_hours"], 168.0)
            contract = artifacts["reentry_contract"]
            self.assertTrue(contract["risk_present"])
            self.assertIn("hypothesis", contract["working_memory_keys"])
            self.assertIn("README.md", contract["world_state_files"])
            self.assertIn("focus", contract["surfaces"])
            self.assertIn("day_reentry_focus_surfaces_aged_active_session", text)
            self.assertIn("day_reentry_resume_restores_memory_and_world_state", text)

    def test_run_dogfood_continuity_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="continuity",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "continuity")
            self.assertIn("continuity_resume_scores_reentry_artifacts", text)
            self.assertIn("continuity_follow_snapshot_and_status_surface_score", text)
            self.assertIn("continuity_failed_edit_reentry_surfaces_safe_reobserve", text)

    def test_run_dogfood_m3_reentry_gate_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m3-reentry-gate",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            artifacts = scenario["artifacts"]
            fresh_cli_workspace = Path(artifacts["fresh_cli_workspace"])
            fresh_cli_template_path = Path(artifacts["fresh_cli_report_template"])
            fresh_cli_prompt_path = Path(artifacts["fresh_cli_restart_prompt"])
            fresh_cli_template = json.loads(fresh_cli_template_path.read_text(encoding="utf-8"))
            fresh_cli_prompt = fresh_cli_prompt_path.read_text(encoding="utf-8")

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m3-reentry-gate")
            self.assertIn("m3_reentry_gate_resume_brief_has_change_risk_next_action", text)
            self.assertIn("m3_reentry_gate_can_advance_to_verification_after_reentry", text)
            self.assertIn("m3_reentry_gate_writes_fresh_cli_comparison_assets", text)
            self.assertIn("M3 gate pending", (fresh_cli_workspace / "README.md").read_text(encoding="utf-8"))
            self.assertEqual(fresh_cli_template["schema_version"], 2)
            self.assertEqual(fresh_cli_template["context_mode"], "true_restart")
            self.assertIn("manual_rebrief_needed", fresh_cli_template)
            self.assertIn("repository_only_compliance", fresh_cli_template)
            self.assertIn("reconstruction_burden", fresh_cli_template)
            self.assertIn("persistent_advantage_signal", fresh_cli_template)
            self.assertEqual(fresh_cli_template["comparison_result"]["choice"], "unknown")
            self.assertEqual(fresh_cli_template["mew_evidence"]["continuity_status"], "strong")
            self.assertEqual(
                fresh_cli_template["mew_evidence"]["decisive_next_action"],
                "approve_pending_readme_edit_then_rerun_verifier",
            )
            self.assertIn("M3 Fresh CLI Reentry Comparator", fresh_cli_prompt)
            self.assertIn(str(fresh_cli_workspace), fresh_cli_prompt)
            self.assertIn("VERIFY_COMMAND.txt", fresh_cli_prompt)
            self.assertIn("reconstruction_burden", fresh_cli_prompt)
            self.assertNotIn("M3 gate complete", fresh_cli_prompt)
            self.assertNotIn("Approve the README.md dry-run edit", fresh_cli_prompt)

    def test_run_dogfood_m3_reentry_gate_merges_fresh_cli_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "fresh-cli-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "status": "complete_with_environment_note",
                        "manual_rebrief_needed": False,
                        "repository_only_compliance": True,
                        "verification_exit_code": 0,
                        "reconstruction_burden": {
                            "repository_only_steps_before_first_correct_action": 2,
                            "needed_to_read_verifier_before_action": True,
                            "needed_to_run_verifier_before_action": True,
                            "missing_context_that_mew_resume_had": ["pending dry-run edit diff"],
                            "mew_resume_would_have_changed_first_action": True,
                            "notes": "fresh had to reconstruct the pending edit from repo/test state",
                        },
                        "persistent_advantage_signal": {
                            "mew_saved_reconstruction": True,
                            "mew_saved_verifier_rerun": True,
                            "mew_prevented_wrong_first_action": False,
                            "reason": "mew resume already named the approval and verifier sequence",
                        },
                        "comparison_result": {
                            "choice": "parity",
                            "reason": "fresh restart and mew reached the same next action",
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                workspace=str(root / "dog"),
                scenario="m3-reentry-gate",
                cleanup=False,
                m3_comparison_report=str(report_path),
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            fresh_cli_report = scenario["artifacts"]["fresh_cli_report"]

            self.assertEqual(report["status"], "pass")
            self.assertIn("m3_reentry_gate_merges_fresh_cli_comparison_report", text)
            self.assertEqual(fresh_cli_report["status"], "loaded")
            self.assertEqual(fresh_cli_report["source"], str(report_path))
            self.assertFalse(fresh_cli_report["manual_rebrief_needed"])
            self.assertTrue(fresh_cli_report["repository_only_compliance"])
            self.assertEqual(fresh_cli_report["comparison_choice"], "parity")
            self.assertEqual(
                fresh_cli_report["reconstruction_burden"]["repository_only_steps_before_first_correct_action"],
                2,
            )
            self.assertTrue(fresh_cli_report["persistent_advantage_signal"]["mew_saved_reconstruction"])

    def test_run_dogfood_m3_source_reentry_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m3-source-reentry",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            artifacts = scenario["artifacts"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m3-source-reentry")
            self.assertEqual(artifacts["continuity_status"], "strong")
            self.assertEqual(artifacts["pending_approval_count"], 1)
            self.assertEqual(artifacts["unresolved_failure_tool"], "run_tests")
            self.assertEqual(artifacts["source_file"], "mew_status.py")
            self.assertIn("m3_source_reentry_resume_has_source_edit_test_risk_next_action", text)
            self.assertIn("m3_source_reentry_can_advance_to_passing_unittest", text)

    def test_run_dogfood_chat_cockpit_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="chat-cockpit",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "chat-cockpit")
            self.assertIn("chat-cockpit: pass", text)
            self.assertIn("chat_work_respects_kind_scope", text)
            self.assertIn("chat_transcript_records_inputs", text)
            self.assertIn("code_entrypoint_starts_work_mode_chat", text)
            self.assertIn("code_startup_controls_stay_short", text)

    def test_run_dogfood_work_session_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="work-session",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["scenarios"][0]["name"], "work-session")
            self.assertIn("work-session: pass", text)
            self.assertIn("work_source_edit_pairing_advisory", text)
            self.assertIn("work_ai_paired_test_approval_auto_defers_verification", text)
            self.assertIn("work_ai_accept_edits_auto_applies_preview", text)
            self.assertIn("work_ai_accept_edits_defers_paired_test_first_verification", text)
            self.assertIn("work_ai_accept_edits_auto_approves_paired_write_batch", text)
            self.assertIn("work_approve_tool_can_defer_verification", text)
            self.assertIn("closed_session_follow_status_surfaces_mark_task_done", text)
            self.assertIn("stale_follow_snapshot_surfaces_session_state_newer", text)
            self.assertIn("work_unpaired_source_approval_requires_override", text)
            self.assertIn("work_zero_test_pytest_invalid_verifier_confidence", text)
            self.assertIn("work_low_yield_search_trap_surfaces_in_resume", text)
            command = report["scenarios"][0]["commands"][0]
            self.assertIn("stdout_tail", command)
            self.assertIn("stdout_chars", command)
            self.assertNotIn("stdout", command)
            self.assertLess(len(json.dumps(report, ensure_ascii=False)), 145_000)

    def test_run_dogfood_m2_comparative_scenario_writes_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                workspace=str(Path(tmp) / "dog"),
                scenario="m2-comparative",
                cleanup=False,
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            artifacts = scenario["artifacts"]
            protocol_path = Path(artifacts["json"])
            runbook_path = Path(artifacts["markdown"])
            fresh_cli_template_path = Path(artifacts["fresh_cli_report_template"])
            fresh_cli_prompt_path = Path(artifacts["fresh_cli_restart_prompt"])
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            runbook = runbook_path.read_text(encoding="utf-8")
            fresh_cli_template = json.loads(fresh_cli_template_path.read_text(encoding="utf-8"))
            fresh_cli_prompt = fresh_cli_prompt_path.read_text(encoding="utf-8")

            self.assertEqual(report["status"], "pass")
            self.assertEqual(scenario["name"], "m2-comparative")
            self.assertTrue(protocol_path.exists())
            self.assertTrue(runbook_path.exists())
            self.assertTrue(fresh_cli_template_path.exists())
            self.assertTrue(fresh_cli_prompt_path.exists())
            self.assertIn("m2-comparative: pass", text)
            self.assertIn("artifacts:", text)
            self.assertIn("m2_comparative_protocol_records_resident_preference", text)
            self.assertIn("m2_comparative_protocol_maps_to_m2_done_when", text)
            self.assertIn("m2_comparative_protocol_has_fillable_comparison_result", text)
            self.assertIn("m2_comparative_protocol_tracks_interruption_resume_gate", text)
            self.assertIn("m2_comparative_protocol_tracks_fresh_cli_restart_context", text)
            self.assertIn("m2_comparative_protocol_writes_fresh_cli_restart_assets", text)
            self.assertEqual(fresh_cli_template["fresh_cli_context_mode"], "true_restart")
            self.assertFalse(fresh_cli_template["fresh_cli_session_resumed"])
            self.assertFalse(fresh_cli_template["fresh_cli_handoff_note_used"])
            self.assertIn("M2 Fresh CLI Restart Comparator", fresh_cli_prompt)
            self.assertIn("fresh_cli_context_mode", fresh_cli_prompt)
            self.assertTrue(protocol["generated_at"])
            self.assertEqual(
                protocol["observer_tip"],
                (
                    "When approving only one half of a paired source/test change, "
                    "apply it with deferred verification and run the verifier after "
                    "the companion change lands."
                ),
            )
            self.assertEqual(protocol["comparison_result"]["status"], "unknown")
            self.assertIn("parity", protocol["comparison_result"]["allowed_statuses"])
            self.assertEqual(protocol["comparison_result"]["next_blocker"], "")
            self.assertEqual(protocol["comparison_result"]["notes"], "")
            self.assertEqual(protocol["task_shape"]["recommended_next"], "interruption_resume")
            self.assertIn("interruption_resume", protocol["task_shape"]["allowed_values"])
            self.assertIn("test_discovery", protocol["task_shape"]["allowed_values"])
            self.assertIn("approval_pairing", protocol["task_shape"]["allowed_values"])
            self.assertIn("process_stop", protocol["task_shape"]["allowed_values"])
            self.assertEqual(protocol["interruption_resume_gate"]["status"], "unknown")
            self.assertIn("proved", protocol["interruption_resume_gate"]["allowed_statuses"])
            fresh_gate = protocol["interruption_resume_gate"]["fresh_cli"]
            self.assertEqual(fresh_gate["context_mode"], "unknown")
            self.assertIn("true_restart", fresh_gate["allowed_context_modes"])
            self.assertIn("same_session_resume", fresh_gate["allowed_context_modes"])
            self.assertIsNone(fresh_gate["session_resumed"])
            self.assertIsNone(fresh_gate["handoff_note_used"])
            self.assertEqual(fresh_gate["restart_comparator_status"], "unknown")
            self.assertIn("mew", protocol["comparison_result"]["run_summaries"])
            self.assertIn("fresh_cli", protocol["comparison_result"]["run_summaries"])
            self.assertIn("## Task Shape", runbook)
            self.assertIn("## Observer Tip", runbook)
            self.assertIn("## Interruption Resume Gate", runbook)
            self.assertIn("apply it with deferred verification", runbook)
            self.assertIn("## Comparison Result", runbook)
            self.assertIn("- next_blocker:", runbook)
            self.assertIn("  - fresh_cli:", runbook)
            self.assertIn("mew", protocol["resident_preference"]["allowed_values"])

    def test_run_dogfood_m2_comparative_prefills_mew_session_evidence(self):
        previous_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            state_dir = root / STATE_DIR
            state_dir.mkdir(parents=True)
            state = default_state()
            state["tasks"].append(
                {
                    "id": 3,
                    "title": "M2 evidence task",
                    "description": "Implement a synthetic M2 evidence path.",
                    "status": "done",
                    "priority": "medium",
                    "kind": "coding",
                    "notes": "Synthetic M2 dogfood evidence.",
                }
            )
            state["work_sessions"].append(
                {
                    "id": 7,
                    "task_id": 3,
                    "status": "closed",
                    "phase": "done",
                    "created_at": "2026-04-19T10:00:00Z",
                    "updated_at": "2026-04-19T10:05:00Z",
                    "default_options": {
                        "allow_read": ["."],
                        "allow_write": ["."],
                        "allow_shell": False,
                        "allow_verify": True,
                        "approval_mode": "accept-edits",
                        "verify_command": "pytest -q",
                    },
                    "working_memory": {
                        "current_goal": "prefill M2 evidence",
                        "next_action": "Run the matching fresh CLI comparison.",
                    },
                    "model_turns": [
                        {
                            "id": 1,
                            "status": "completed",
                            "action": {"type": "batch"},
                            "tool_call_ids": [11, 12],
                            "started_at": "2026-04-19T10:00:00Z",
                            "finished_at": "2026-04-19T10:00:20Z",
                        }
                    ],
                    "tool_calls": [
                        {
                            "id": 11,
                            "tool": "edit_file",
                            "status": "completed",
                            "approval_status": "applied",
                            "started_at": "2026-04-19T10:01:00Z",
                            "finished_at": "2026-04-19T10:02:00Z",
                            "parameters": {"path": "tests/test_dogfood.py"},
                            "result": {
                                "dry_run": True,
                                "changed": True,
                            },
                        },
                        {
                            "id": 12,
                            "tool": "edit_file",
                            "status": "completed",
                            "approval_status": "applied",
                            "started_at": "2026-04-19T10:02:00Z",
                            "finished_at": "2026-04-19T10:03:00Z",
                            "parameters": {"path": "src/mew/dogfood.py"},
                            "result": {
                                "dry_run": True,
                                "changed": True,
                                "verification": {"command": "pytest -q", "exit_code": 0},
                                "verification_exit_code": 0,
                            },
                        },
                        {
                            "id": 13,
                            "tool": "run_tests",
                            "status": "completed",
                            "started_at": "2026-04-19T10:03:00Z",
                            "finished_at": "2026-04-19T10:04:00Z",
                            "parameters": {"command": "pytest -q"},
                            "result": {"command": "pytest -q", "exit_code": 0, "stdout": "ok\n"},
                        },
                    ],
                }
            )
            state["work_sessions"].append(
                {
                    "id": 8,
                    "task_id": 4,
                    "status": "closed",
                    "phase": "done",
                    "created_at": "2026-04-19T09:00:00Z",
                    "updated_at": "2026-04-19T09:01:00Z",
                    "tool_calls": [],
                    "model_turns": [],
                }
            )
            (root / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
            try:
                os.chdir(root)
                args = SimpleNamespace(
                    workspace=str(root / "dog"),
                    scenario="m2-comparative",
                    cleanup=False,
                    mew_session_id="latest",
                )

                report = run_dogfood_scenario(args)
            finally:
                os.chdir(previous_cwd)

            text = format_dogfood_scenario_report(report)
            summary = summarize_dogfood_scenario_json(report)
            scenario = report["scenarios"][0]
            protocol_path = Path(scenario["artifacts"]["json"])
            runbook_path = Path(scenario["artifacts"]["markdown"])
            fresh_cli_template_path = Path(scenario["artifacts"]["fresh_cli_report_template"])
            fresh_cli_prompt_path = Path(scenario["artifacts"]["fresh_cli_restart_prompt"])
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            runbook = runbook_path.read_text(encoding="utf-8")
            fresh_cli_template = json.loads(fresh_cli_template_path.read_text(encoding="utf-8"))
            fresh_cli_prompt = fresh_cli_prompt_path.read_text(encoding="utf-8")
            mew_summary = protocol["comparison_result"]["run_summaries"]["mew"]

            self.assertEqual(report["status"], "pass")
            self.assertIn("m2_comparative_protocol_prefills_mew_run_evidence", text)
            self.assertEqual(protocol["mew_run_evidence"]["status"], "found")
            self.assertEqual(protocol["mew_run_evidence"]["session_argument"], "latest")
            self.assertEqual(protocol["mew_run_evidence"]["mew_session_argument"], "latest")
            self.assertEqual(protocol["mew_run_evidence"]["work_session_id"], 7)
            self.assertEqual(protocol["mew_run_evidence"]["verification"]["status"], "passed")
            self.assertEqual(protocol["mew_run_evidence"]["approval_mode"], "accept-edits")
            self.assertEqual(
                protocol["mew_run_evidence"]["default_permission_posture"],
                {
                    "allow_read": True,
                    "allow_write": True,
                    "allow_shell": False,
                    "allow_verify": True,
                },
            )
            self.assertIn("- approval_mode: accept-edits", runbook)
            self.assertIn("- default_permission_posture:", runbook)
            self.assertIn("- paired_write_batch: proved", runbook)
            self.assertEqual(protocol["mew_run_evidence"]["approval_counts"]["applied"], 2)
            self.assertEqual(protocol["mew_run_evidence"]["paired_write_batch"]["status"], "proved")
            self.assertEqual(protocol["mew_run_evidence"]["paired_write_batch"]["tool_call_ids"], [11, 12])
            self.assertEqual(protocol["mew_run_evidence"]["paired_write_batch"]["applied_count"], 2)
            self.assertEqual(protocol["mew_run_evidence"]["resume_gate"]["status"], "not_proved")
            self.assertTrue(protocol["mew_run_evidence"]["resume_gate"]["changed_or_pending_work"])
            self.assertEqual(protocol["interruption_resume_gate"]["mew"]["status"], "not_proved")
            self.assertIn("session #7 task #3", mew_summary["summary"])
            self.assertIn("passed exit=0 command=pytest -q", mew_summary["verification_result"])
            self.assertIn("mew work 3 --session --resume --allow-read .", mew_summary["preference_signal"])
            self.assertEqual(
                protocol["resume_behavior"]["mew_resume_command"],
                "mew work 3 --session --resume --allow-read .",
            )
            self.assertIn("## Mew Run Evidence", runbook)
            self.assertIn("## Interruption Resume Gate", runbook)
            self.assertIn("- work_session_id: 7", runbook)
            self.assertIn("Implement a synthetic M2 evidence path.", runbook)
            self.assertIn("`pytest -q`", runbook)
            self.assertEqual(fresh_cli_template["task_summary"], "M2 evidence task")
            self.assertEqual(
                fresh_cli_template["task_description"],
                "Implement a synthetic M2 evidence path.",
            )
            self.assertIn(
                "./mew dogfood --scenario m2-comparative --mew-session-id latest --m2-comparison-report <report.json>",
                fresh_cli_prompt,
            )
            self.assertEqual(fresh_cli_template["verification"][0]["command"], "pytest -q")
            self.assertIn("M2 evidence task", fresh_cli_prompt)
            self.assertIn("Implement a synthetic M2 evidence path.", fresh_cli_prompt)
            self.assertIn("pytest -q", fresh_cli_prompt)
            self.assertIn("fresh_cli", protocol["resident_preference"]["allowed_values"])
            self.assertIn("parity", protocol["resident_preference"]["allowed_values"])
            self.assertIn("dead_waits_over_30s", protocol["friction_counts"])
            self.assertIn("artifacts", summary["scenarios"][0])

    def test_run_dogfood_m2_comparative_counts_preserved_stop_request_as_resume_risk(self):
        previous_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            state_dir = root / STATE_DIR
            state_dir.mkdir(parents=True)
            state = default_state()
            state["tasks"].append(
                {
                    "id": 3,
                    "title": "M2 stopped no-change evidence task",
                    "description": "Resume after a deliberate stop and finish with no source change.",
                    "status": "done",
                    "priority": "medium",
                    "kind": "coding",
                }
            )
            state["work_sessions"].append(
                {
                    "id": 7,
                    "task_id": 3,
                    "status": "closed",
                    "phase": "done",
                    "created_at": "2026-04-19T10:00:00Z",
                    "updated_at": "2026-04-19T10:05:00Z",
                    "last_stop_request": {
                        "requested_at": "2026-04-19T10:02:00Z",
                        "reason": "intentional final-gate stop before resume",
                        "action": "",
                        "submit_text": "",
                    },
                    "working_memory": {
                        "hypothesis": "the stopped session resumed and reached a no-change conclusion",
                        "next_step": "review the no-change evidence",
                        "last_verified_state": "pytest passed",
                    },
                    "model_turns": [
                        {
                            "id": 1,
                            "status": "completed",
                            "started_at": "2026-04-19T10:00:00Z",
                            "finished_at": "2026-04-19T10:04:00Z",
                        }
                    ],
                    "tool_calls": [
                        {
                            "id": 11,
                            "tool": "edit_file",
                            "status": "completed",
                            "approval_status": "applied",
                            "started_at": "2026-04-19T10:01:00Z",
                            "finished_at": "2026-04-19T10:02:00Z",
                            "parameters": {"path": "tests/test_dogfood.py"},
                            "result": {"dry_run": True, "changed": True},
                        },
                        {
                            "id": 12,
                            "tool": "run_tests",
                            "status": "completed",
                            "started_at": "2026-04-19T10:04:00Z",
                            "finished_at": "2026-04-19T10:05:00Z",
                            "parameters": {"command": "pytest -q"},
                            "result": {"command": "pytest -q", "exit_code": 0, "stdout": "ok\n"},
                        },
                    ],
                }
            )
            (root / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
            try:
                os.chdir(root)
                args = SimpleNamespace(
                    workspace=str(root / "dog"),
                    scenario="m2-comparative",
                    cleanup=False,
                    mew_session_id="7",
                )

                report = run_dogfood_scenario(args)
            finally:
                os.chdir(previous_cwd)

            protocol_path = Path(report["scenarios"][0]["artifacts"]["json"])
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            gate = protocol["mew_run_evidence"]["resume_gate"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(gate["status"], "proved")
            self.assertTrue(gate["risk_or_interruption_preserved"])
            self.assertNotIn("resume did not preserve an interruption, failure, or recovery risk", gate["evidence_gap"])
            self.assertEqual(protocol["interruption_resume_gate"]["mew"]["status"], "proved")

    def test_run_dogfood_m2_comparative_prefills_task_chain_evidence(self):
        previous_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            state_dir = root / STATE_DIR
            state_dir.mkdir(parents=True)
            state = default_state()
            state["tasks"].append(
                {
                    "id": 3,
                    "title": "M2 process stop evidence task",
                    "status": "todo",
                    "priority": "high",
                    "kind": "coding",
                    "notes": "Continue from the interrupted first session.",
                }
            )
            state["work_sessions"].append(
                {
                    "id": 7,
                    "task_id": 3,
                    "status": "closed",
                    "phase": "interrupted",
                    "created_at": "2026-04-19T10:00:00Z",
                    "updated_at": "2026-04-19T10:02:00Z",
                    "working_memory": {
                        "hypothesis": "first session was interrupted",
                        "next_step": "start a new session and continue",
                    },
                    "model_turns": [
                        {
                            "id": 1,
                            "status": "interrupted",
                            "started_at": "2026-04-19T10:00:00Z",
                            "finished_at": "2026-04-19T10:00:30Z",
                            "error": "Interrupted by user during follow.",
                        }
                    ],
                    "tool_calls": [
                        {
                            "id": 11,
                            "tool": "edit_file",
                            "status": "completed",
                            "approval_status": "applied",
                            "started_at": "2026-04-19T10:01:00Z",
                            "finished_at": "2026-04-19T10:02:00Z",
                            "parameters": {"path": "tests/test_dogfood.py"},
                            "result": {"dry_run": True, "changed": True},
                        }
                    ],
                }
            )
            state["work_sessions"].append(
                {
                    "id": 8,
                    "task_id": 3,
                    "status": "closed",
                    "phase": "done",
                    "created_at": "2026-04-19T10:03:00Z",
                    "updated_at": "2026-04-19T10:06:00Z",
                    "working_memory": {
                        "hypothesis": "second session completed the interrupted task",
                        "next_step": "review and commit the verified change",
                        "last_verified_state": "pytest passed",
                    },
                    "model_turns": [
                        {
                            "id": 2,
                            "status": "completed",
                            "started_at": "2026-04-19T10:03:00Z",
                            "finished_at": "2026-04-19T10:04:00Z",
                        }
                    ],
                    "tool_calls": [
                        {
                            "id": 12,
                            "tool": "run_tests",
                            "status": "completed",
                            "started_at": "2026-04-19T10:05:00Z",
                            "finished_at": "2026-04-19T10:06:00Z",
                            "parameters": {"command": "pytest -q"},
                            "result": {"command": "pytest -q", "exit_code": 0, "stdout": "ok\n"},
                        }
                    ],
                }
            )
            (root / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
            try:
                os.chdir(root)
                args = SimpleNamespace(
                    workspace=str(root / "dog"),
                    scenario="m2-comparative",
                    cleanup=False,
                    mew_session_id="task:3",
                )

                report = run_dogfood_scenario(args)
            finally:
                os.chdir(previous_cwd)

            scenario = report["scenarios"][0]
            protocol_path = Path(scenario["artifacts"]["json"])
            runbook_path = Path(scenario["artifacts"]["markdown"])
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            runbook = runbook_path.read_text(encoding="utf-8")
            evidence = protocol["mew_run_evidence"]
            gate = protocol["interruption_resume_gate"]["mew"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(evidence["evidence_mode"], "task_chain")
            self.assertEqual(evidence["session_argument"], "task:3")
            self.assertEqual(evidence["mew_session_argument"], "task:3")
            self.assertEqual(evidence["work_session_ids"], [7, 8])
            self.assertEqual(gate["status"], "proved")
            self.assertEqual(gate["evidence_mode"], "task_chain")
            self.assertEqual(gate["risk_session_ids"], [7])
            self.assertEqual(gate["verification_session_ids"], [8])
            self.assertIn(
                "task-chain sessions #7,#8",
                protocol["comparison_result"]["run_summaries"]["mew"]["summary"],
            )
            self.assertIn("- evidence_mode: task_chain", runbook)

    def test_format_m2_fresh_cli_restart_prompt_falls_back_to_session_argument(self):
        prompt = format_m2_fresh_cli_restart_prompt(
            {
                "mew_run_evidence": {
                    "session_argument": "task:3",
                    "task_title": "Fallback task",
                    "verification": {"command": "pytest -q"},
                }
            }
        )

        self.assertIn(
            "./mew dogfood --scenario m2-comparative --mew-session-id task:3 --m2-comparison-report <report.json>",
            prompt,
        )

    def test_run_dogfood_m2_comparative_uses_task_level_verification_for_task_chain(self):
        previous_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            state_dir = root / STATE_DIR
            state_dir.mkdir(parents=True)
            state = default_state()
            state["tasks"].append(
                {
                    "id": 3,
                    "title": "M2 supervisor completion task",
                    "description": "Complete a task after a failed mew source attempt.",
                    "status": "done",
                    "priority": "high",
                    "kind": "coding",
                    "notes": "Supervisor finished after the session failed verification.",
                }
            )
            state["work_sessions"].append(
                {
                    "id": 7,
                    "task_id": 3,
                    "status": "closed",
                    "phase": "closed",
                    "created_at": "2026-04-19T10:00:00Z",
                    "updated_at": "2026-04-19T10:05:00Z",
                    "working_memory": {
                        "current_goal": "preserve M2 merge command evidence",
                        "next_action": "review the supervisor-completed fix",
                    },
                    "model_turns": [
                        {
                            "id": 1,
                            "status": "completed",
                            "started_at": "2026-04-19T10:00:00Z",
                            "finished_at": "2026-04-19T10:01:00Z",
                        }
                    ],
                    "tool_calls": [
                        {
                            "id": 11,
                            "tool": "edit_file",
                            "status": "failed",
                            "approval_status": "rejected",
                            "started_at": "2026-04-19T10:02:00Z",
                            "finished_at": "2026-04-19T10:03:00Z",
                            "parameters": {"path": "src/mew/dogfood.py"},
                            "result": {
                                "dry_run": False,
                                "changed": True,
                                "verification": {
                                    "command": "uv run pytest --no-testmon -q tests/test_dogfood.py -k m2_comparative",
                                    "exit_code": 1,
                                },
                                "verification_exit_code": 1,
                            },
                        }
                    ],
                }
            )
            state["verification_runs"].append(
                {
                    "id": 99,
                    "event_id": None,
                    "task_id": 3,
                    "reason": "user-reported completion verification",
                    "command": "user-reported",
                    "argv": [],
                    "cwd": ".",
                    "exit_code": 0,
                    "stdout": "Supervisor ran uv run pytest --no-testmon -q tests/test_dogfood.py; result: passed.",
                    "stderr": "",
                    "started_at": "2026-04-19T10:06:00Z",
                    "finished_at": "2026-04-19T10:06:00Z",
                    "created_at": "2026-04-19T10:06:00Z",
                    "updated_at": "2026-04-19T10:06:00Z",
                }
            )
            (root / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
            try:
                os.chdir(root)
                args = SimpleNamespace(
                    workspace=str(root / "dog"),
                    scenario="m2-comparative",
                    cleanup=False,
                    mew_session_id="task:3",
                )

                report = run_dogfood_scenario(args)
            finally:
                os.chdir(previous_cwd)

            scenario = report["scenarios"][0]
            protocol_path = Path(scenario["artifacts"]["json"])
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            evidence = protocol["mew_run_evidence"]
            gate = protocol["interruption_resume_gate"]["mew"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(evidence["verification"]["status"], "passed")
            self.assertEqual(evidence["verification"]["source"], "task_verification")
            self.assertEqual(evidence["verification"]["verification_run_id"], 99)
            self.assertEqual(gate["status"], "proved")
            self.assertEqual(gate["verification_run_ids"], [99])
            self.assertNotIn("no passing verification was recorded after a risk session", gate["evidence_gap"])

    def test_run_dogfood_m2_task_shape_sets_selected_from_cli(self):
        for shape in ("test_discovery", "approval_pairing", "process_stop"):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as tmp:
                args = SimpleNamespace(
                    workspace=str(Path(tmp) / "dog"),
                    scenario="m2-comparative",
                    cleanup=False,
                    m2_task_shape=shape,
                )

                report = run_dogfood_scenario(args)
                scenario = report["scenarios"][0]
                protocol_path = Path(scenario["artifacts"]["json"])
                runbook_path = Path(scenario["artifacts"]["markdown"])
                protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
                runbook = runbook_path.read_text(encoding="utf-8")

                self.assertEqual(report["status"], "pass")
                self.assertEqual(protocol["task_shape"]["selected"], shape)
                self.assertIn(f"- selected: {shape}", runbook)

    def test_run_dogfood_m2_comparative_merges_fresh_cli_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "fresh-cli-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "status": "inconclusive",
                        "next_blocker": "Run one more paired task with a write.",
                        "notes": "Fresh CLI comparison imported from an external agent run.",
                        "fresh_cli": {
                            "summary": "fresh CLI completed the same task with two tool calls",
                            "verification_result": "passed exit=0 command=pytest -q",
                            "friction_summary": "manual_status_probes=1 dead_waits_over_30s=0",
                            "preference_signal": "fast, but no durable resume bundle",
                            "context_mode": "true_restart",
                            "session_resumed": False,
                            "handoff_note_used": True,
                            "restart_comparator_status": "proved",
                        },
                        "friction_counts": {
                            "manual_status_probes": 1,
                            "dead_waits_over_30s": 0,
                        },
                        "resident_preference": {
                            "choice": "inconclusive",
                            "reason": "fresh CLI was faster, mew preserved better continuity",
                            "blocking_gap": "need a write-heavy paired task",
                        },
                        "task_shape": {
                            "selected": "interruption_resume",
                        },
                        "interruption_resume_gate": {
                            "fresh_cli": {
                                "status": "not_proved",
                                "manual_rebrief_needed": True,
                                "evidence_gap": ["fresh CLI was not interrupted in this run"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                workspace=str(root / "dog"),
                scenario="m2-comparative",
                cleanup=False,
                m2_comparison_report=str(report_path),
            )

            report = run_dogfood_scenario(args)
            text = format_dogfood_scenario_report(report)
            scenario = report["scenarios"][0]
            protocol_path = Path(scenario["artifacts"]["json"])
            runbook_path = Path(scenario["artifacts"]["markdown"])
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            runbook = runbook_path.read_text(encoding="utf-8")
            fresh_cli = protocol["comparison_result"]["run_summaries"]["fresh_cli"]

            self.assertEqual(report["status"], "pass")
            self.assertIn("m2_comparative_protocol_merges_comparison_report", text)
            self.assertEqual(protocol["comparison_report"]["status"], "loaded")
            self.assertEqual(protocol["comparison_result"]["status"], "inconclusive")
            self.assertEqual(protocol["comparison_result"]["next_blocker"], "Run one more paired task with a write.")
            self.assertIn("two tool calls", fresh_cli["summary"])
            self.assertEqual(protocol["friction_counts"]["manual_status_probes"], 1)
            self.assertEqual(protocol["resident_preference"]["choice"], "inconclusive")
            self.assertEqual(protocol["task_shape"]["selected"], "interruption_resume")
            self.assertEqual(protocol["interruption_resume_gate"]["fresh_cli"]["status"], "not_proved")
            self.assertTrue(protocol["interruption_resume_gate"]["fresh_cli"]["manual_rebrief_needed"])
            self.assertEqual(protocol["interruption_resume_gate"]["fresh_cli"]["context_mode"], "true_restart")
            self.assertFalse(protocol["interruption_resume_gate"]["fresh_cli"]["session_resumed"])
            self.assertTrue(protocol["interruption_resume_gate"]["fresh_cli"]["handoff_note_used"])
            self.assertEqual(
                protocol["interruption_resume_gate"]["fresh_cli"]["restart_comparator_status"],
                "proved",
            )
            self.assertIn("## Comparison Report", runbook)
            self.assertIn("- comparison_status: inconclusive", runbook)
            self.assertIn("- next_blocker: Run one more paired task with a write.", runbook)
            self.assertIn("manual_rebrief_needed", runbook)
            self.assertIn(str(report_path), runbook)

    def test_run_dogfood_m2_comparative_merges_flat_fresh_cli_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "fresh-cli-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "task_summary": "fresh CLI completed the approval_pairing task shape",
                        "verification": [
                            {
                                "command": "uv run pytest -q tests/test_dogfood.py -k m2_task_shape",
                                "exit_code": 0,
                                "summary": "2 passed",
                            }
                        ],
                        "manual_rebrief_needed": False,
                        "fresh_cli_context_mode": "resumed_session",
                        "fresh_cli_session_resumed": True,
                        "fresh_cli_handoff_note_used": True,
                        "fresh_cli_restart_comparator_status": "not_proved",
                        "interruption_resume_gate": "unknown",
                        "friction_summary": "no material friction",
                        "resident_preference": {
                            "choice": "fresh_cli",
                            "reason": "fresh CLI completed the task faster",
                        },
                        "notes": "Fresh CLI was not interrupted.",
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                workspace=str(root / "dog"),
                scenario="m2-comparative",
                cleanup=False,
                m2_comparison_report=str(report_path),
            )

            report = run_dogfood_scenario(args)
            scenario = report["scenarios"][0]
            protocol_path = Path(scenario["artifacts"]["json"])
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            fresh_cli = protocol["comparison_result"]["run_summaries"]["fresh_cli"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(protocol["comparison_result"]["status"], "fresh_cli_preferred")
            self.assertIn("approval_pairing", fresh_cli["summary"])
            self.assertIn("exit=0", fresh_cli["verification_result"])
            self.assertEqual(fresh_cli["friction_summary"], "no material friction")
            self.assertEqual(protocol["resident_preference"]["choice"], "fresh_cli")
            self.assertEqual(protocol["interruption_resume_gate"]["fresh_cli"]["status"], "unknown")
            self.assertFalse(protocol["interruption_resume_gate"]["fresh_cli"]["manual_rebrief_needed"])
            self.assertEqual(
                protocol["interruption_resume_gate"]["fresh_cli"]["context_mode"],
                "same_session_resume",
            )
            self.assertTrue(protocol["interruption_resume_gate"]["fresh_cli"]["session_resumed"])
            self.assertTrue(protocol["interruption_resume_gate"]["fresh_cli"]["handoff_note_used"])
            self.assertEqual(
                protocol["interruption_resume_gate"]["fresh_cli"]["restart_comparator_status"],
                "not_proved",
            )
            self.assertIn("true fresh CLI restart", protocol["comparison_result"]["next_blocker"])

    def test_run_dogfood_m2_comparative_accepts_parity_comparison_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "fresh-cli-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "task_summary": "fresh CLI reached the same no-change conclusion",
                        "verification": [
                            {
                                "command": "uv run pytest -q tests/test_metrics.py tests/test_brief.py",
                                "exit_code": 0,
                                "summary": "57 passed",
                            }
                        ],
                        "fresh_cli_context_mode": "true_restart",
                        "fresh_cli_session_resumed": False,
                        "fresh_cli_handoff_note_used": False,
                        "fresh_cli_restart_comparator_status": "proved",
                        "interruption_resume_gate": "not_proved",
                        "preference_signal": "parity",
                        "resident_preference": {
                            "choice": "parity",
                            "reason": "both runs made the same no-change decision",
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                workspace=str(root / "dog"),
                scenario="m2-comparative",
                cleanup=False,
                m2_comparison_report=str(report_path),
            )

            report = run_dogfood_scenario(args)
            protocol_path = Path(report["scenarios"][0]["artifacts"]["json"])
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "pass")
            self.assertEqual(protocol["comparison_result"]["status"], "parity")
            self.assertEqual(protocol["resident_preference"]["choice"], "parity")
            self.assertIn("parity", protocol["comparison_result"]["allowed_statuses"])
            self.assertIn("parity", protocol["resident_preference"]["allowed_values"])

    def test_m2_comparative_parity_with_mew_evidence_clears_review_blocker(self):
        protocol = build_m2_comparative_protocol(
            mew_run_evidence={
                "status": "found",
                "work_session_id": 7,
                "task_id": 3,
                "session_status": "closed",
                "phase": "done",
                "model_turns": 1,
                "tool_calls": 1,
                "effort": {},
                "approval_counts": {},
                "verification": {"status": "passed", "exit_code": 0, "command": "pytest -q"},
                "continuity": {"score": "9/9", "status": "strong"},
                "resume_command": "mew work 3 --session --resume --allow-read .",
                "resume_gate": {"status": "proved", "evidence_gap": []},
            },
            comparison_report={
                "preference_signal": "parity",
                "fresh_cli": {
                    "summary": "fresh CLI reached the same no-change conclusion",
                    "verification_result": "passed exit=0 command=pytest -q",
                },
                "resident_preference": {
                    "choice": "parity",
                    "reason": "both runs reached the same conclusion",
                    "blocking_gap": "",
                },
            },
        )

        self.assertEqual(protocol["comparison_result"]["status"], "parity")
        self.assertEqual(protocol["comparison_result"]["next_blocker"], "")
        self.assertEqual(protocol["resident_preference"]["choice"], "parity")

    def test_run_dogfood_m2_comparative_derives_interruption_gate_from_children(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "fresh-cli-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "task_shape": {"selected": "interruption_resume"},
                        "fresh_cli": {
                            "summary": "fresh CLI interruption gate proved",
                            "verification_result": "not relevant for this fixture",
                            "friction_summary": "manual_rebrief_needed=False",
                            "preference_signal": "fixture",
                        },
                        "interruption_resume_gate": {
                            "mew": {"status": "proved", "evidence_gap": []},
                            "fresh_cli": {
                                "status": "proved",
                                "manual_rebrief_needed": False,
                                "evidence_gap": [],
                            },
                        },
                        "resident_preference": {
                            "choice": "inconclusive",
                            "reason": "this fixture only verifies aggregate gate status",
                            "blocking_gap": "",
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                workspace=str(root / "dog"),
                scenario="m2-comparative",
                cleanup=False,
                m2_comparison_report=str(report_path),
            )

            report = run_dogfood_scenario(args)
            scenario = report["scenarios"][0]
            protocol_path = Path(scenario["artifacts"]["json"])
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "pass")
            self.assertEqual(protocol["interruption_resume_gate"]["status"], "proved")
            self.assertEqual(protocol["interruption_resume_gate"]["mew"]["status"], "proved")
            self.assertEqual(protocol["interruption_resume_gate"]["fresh_cli"]["status"], "proved")

    def test_summarize_dogfood_scenario_json_omits_passing_details(self):
        report = {
            "generated_at": "now",
            "workspace": "/tmp/dog",
            "kept": False,
            "scenario": "work-session",
            "status": "fail",
            "scenarios": [
                {
                    "name": "work-session",
                    "status": "fail",
                    "workspace": "/tmp/dog",
                    "command_count": 2,
                    "commands": [{"stdout_tail": ["x" * 1000], "stdout_chars": 1000}],
                    "checks": [
                        {"name": "passes", "passed": True, "observed": {"large": "x" * 5000}},
                        {"name": "fails", "passed": False, "observed": {"large": "x" * 5000}, "expected": "small"},
                    ],
                }
            ],
        }

        summary = summarize_dogfood_scenario_json(report)

        scenario = summary["scenarios"][0]
        self.assertNotIn("commands", scenario)
        self.assertNotIn("observed", scenario["checks"][0])
        self.assertIn("observed", scenario["checks"][1])
        self.assertLess(len(json.dumps(summary, ensure_ascii=False)), 2000)

    def test_copy_source_workspace_skips_sensitive_state_and_large_files(self):
        with tempfile.TemporaryDirectory() as source_tmp, tempfile.TemporaryDirectory() as workspace_tmp:
            source = Path(source_tmp)
            workspace = Path(workspace_tmp)
            (source / "src").mkdir()
            (source / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
            (source / "auth.json").write_text("secret", encoding="utf-8")
            (source / ".mew").mkdir()
            (source / ".mew" / "state.json").write_text("{}", encoding="utf-8")
            (source / "large.txt").write_text("x" * 200, encoding="utf-8")

            result = copy_source_workspace(source, workspace, max_file_bytes=100)

            self.assertEqual(result["copied_files"], 1)
            self.assertTrue((workspace / "src" / "app.py").exists())
            self.assertFalse((workspace / "auth.json").exists())
            self.assertFalse((workspace / ".mew").exists())
            self.assertFalse((workspace / "large.txt").exists())

    def test_build_report_summarizes_state_and_runtime_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / ".mew").mkdir()
            state = default_state()
            state["runtime_status"]["last_cycle_reason"] = "passive_tick"
            state["runtime_status"]["last_cycle_duration_seconds"] = 1.25
            state["runtime_status"]["last_processed_count"] = 1
            event = add_event(state, "passive_tick", "runtime")
            event["processed_at"] = "done"
            event["decision_plan"] = {
                "summary": "x",
                "schema_issues": [{"level": "warning", "path": "decisions[0].type", "message": "unsupported"}],
            }
            add_outbox_message(state, "info", "hello", event_id=event["id"])
            read_message = add_outbox_message(
                state,
                "info",
                f"Read file {workspace / 'README.md'} and saved the observation to memory.",
                event_id=event["id"],
            )
            read_message["read_at"] = "read"
            add_outbox_message(
                state,
                "info",
                f"Skipped repeated read_file for {workspace / 'README.md'}; recent context already contains that inspection.",
                event_id=event["id"],
            )
            state["thought_journal"].append(
                {
                    "id": 1,
                    "event_id": event["id"],
                    "event_type": "passive_tick",
                    "summary": "Inspected workspace.",
                    "actions": [{"type": "inspect_dir", "path": str(workspace)}],
                    "counts": {"actions": 1, "messages": 1},
                    "open_threads": [],
                    "resolved_threads": [],
                    "dropped_threads": [],
                }
            )
            state["agent_runs"].append(
                {
                    "id": 1,
                    "task_id": 1,
                    "plan_id": 2,
                    "purpose": "implementation",
                    "status": "running",
                    "model": "codex-ultra",
                    "external_pid": 123,
                }
            )
            state["agent_runs"].append(
                {
                    "id": 2,
                    "task_id": 1,
                    "plan_id": 2,
                    "purpose": "review",
                    "status": "completed",
                    "followup_processed_at": "done",
                    "followup_task_id": 3,
                }
            )
            state["memory"]["deep"]["project_snapshot"] = {
                "updated_at": "now",
                "project_types": ["python"],
                "roots": [],
                "files": [],
                "searches": [],
                "package": {"name": "mew"},
            }
            state["runtime_effects"].append(
                {
                    "id": 1,
                    "event_id": event["id"],
                    "reason": "passive_tick",
                    "status": "verified",
                    "action_types": ["run_verification"],
                    "verification_run_ids": [1],
                    "write_run_ids": [],
                }
            )
            state["work_sessions"].append(
                {
                    "id": 1,
                    "task_id": 1,
                    "status": "active",
                    "notes": [
                        {
                            "created_at": "later",
                            "source": "runtime",
                            "text": "runtime passive advance step completed: mew work 1 --live",
                        }
                    ],
                }
            )
            state["runtime_status"]["last_native_work_step"] = {
                "session_id": 1,
                "task_id": 1,
                "outcome": "completed",
            }
            state["runtime_status"]["last_native_work_step_skip"] = "session_started_this_cycle"
            state["runtime_status"]["native_work_step_skips"] = [
                {
                    "at": "now",
                    "event_id": event["id"],
                    "phase": "select",
                    "reason": "session_started_this_cycle",
                }
            ]
            state["runtime_status"]["last_native_work_skip_recovery"] = {
                "action": "wait_next_tick",
                "command": "mew work 1 --session --resume --allow-read .",
            }
            state["runtime_status"]["last_native_work_recovery"] = {
                "action": "auto_retry_verification_completed",
                "status": "completed",
                "command": "python -V",
            }
            (workspace / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
            (workspace / LOG_FILE).write_text(
                "- now: think_phase codex ok event=1\n- now: act_phase codex ok event=1\n",
                encoding="utf-8",
            )
            (workspace / MODEL_TRACE_FILE).write_text(
                json.dumps(
                    {
                        "at": "now",
                        "phase": "think",
                        "event_id": event["id"],
                        "event_type": event["type"],
                        "status": "ok",
                        "backend": "codex",
                        "model": "test",
                        "prompt_chars": 12,
                        "prompt_sha256": "abc",
                        "prompt": "hidden in report",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            runtime_out_path = workspace / STATE_DIR / "dogfood-runtime.out"
            runtime_out_path.write_text(
                "mew runtime started pid=1\nprocessed 1 event(s) reason=startup\nmew runtime stopped\n",
                encoding="utf-8",
            )

            report = build_dogfood_report(workspace, ["mew", "run", "--trace-model"], 0, 1.5)
            report["agent_reflex_results"] = [
                {
                    "phase": "review_wait",
                    "agent_wait_results": [
                        {
                            "run_id": 9,
                            "exit_code": 1,
                            "timed_out": True,
                            "stdout_tail": [],
                            "stderr_tail": ["wait timed out"],
                        }
                    ],
                }
            ]
            text = format_dogfood_report(report)

            self.assertEqual(report["events"]["processed"], 1)
            self.assertEqual(report["model_phases"]["think_ok"], 1)
            self.assertTrue(report["trace_model_enabled"])
            self.assertEqual(report["model_traces"]["total"], 1)
            self.assertEqual(report["runtime_effects"]["total"], 1)
            self.assertEqual(report["runtime_effects"]["by_status"], {"verified": 1})
            self.assertNotIn("prompt", report["model_traces"]["latest"][0])
            self.assertEqual(report["runtime_status"]["last_cycle_reason"], "passive_tick")
            self.assertEqual(report["actions"], {"inspect_dir": 1})
            self.assertEqual(report["read_inspection"]["read_progress_messages"], 1)
            self.assertEqual(report["read_inspection"]["read_progress_unread"], 0)
            self.assertEqual(report["read_inspection"]["repeated_read_skips"], 1)
            self.assertEqual(report["read_inspection"]["repeated_read_skips_unread"], 0)
            self.assertEqual(report["agent_runs"]["total"], 2)
            self.assertEqual(report["agent_runs"]["by_status"], {"completed": 1, "running": 1})
            self.assertEqual(report["programmer_loop"]["implementation_runs"], 1)
            self.assertEqual(report["programmer_loop"]["review_runs"], 1)
            self.assertEqual(report["programmer_loop"]["reviews_with_followup_processed"], 1)
            self.assertEqual(report["programmer_loop"]["followup_task_ids"], [3])
            self.assertEqual(report["native_work_advance"]["attempts"], 1)
            self.assertEqual(report["native_work_advance"]["by_outcome"], {"completed": 1})
            self.assertEqual(report["native_work_advance"]["last_step"]["outcome"], "completed")
            self.assertEqual(report["native_work_advance"]["skip_count"], 1)
            self.assertEqual(
                report["native_work_advance"]["by_skip_reason"],
                {"session_started_this_cycle": 1},
            )
            self.assertEqual(report["native_work_advance"]["recent_skips"][0]["phase"], "select")
            self.assertEqual(report["native_work_advance"]["last_skip_recovery"]["action"], "wait_next_tick")
            self.assertEqual(
                report["native_work_advance"]["last_recovery"]["action"],
                "auto_retry_verification_completed",
            )
            self.assertEqual(report["plan_schema_issues"]["count"], 1)
            self.assertEqual(report["project_snapshot"]["project_types"], ["python"])
            self.assertEqual(report["active_dropped_threads"]["thought_count"], 0)
            self.assertIn("Recent activity", text)
            self.assertIn(
                "model_traces: enabled=True total=1 by_status={'ok': 1} by_phase={'think': 1} latest=1",
                text,
            )
            self.assertIn("Project snapshot", text)
            self.assertIn("runtime_cycle:", text)
            self.assertIn("runtime_effects: total=1 by_status={'verified': 1} latest=1", text)
            self.assertIn("read_inspection:", text)
            self.assertIn("agent_runs:", text)
            self.assertIn("programmer_loop:", text)
            self.assertIn("native_work_advance:", text)
            self.assertIn("agent_reflex_results: 1", text)
            self.assertIn("run #9 exit=1 timed_out=True", text)
            self.assertEqual(len(report["runtime_output_tail"]), 3)
            self.assertIn("Runtime output (last lines)", text)
            self.assertIn("mew runtime stopped", text)
            self.assertIn("plan_schema_issues", text)

    def test_injected_message_status_reports_unprocessed_messages(self):
        state = default_state()
        processed = add_event(state, "user_message", "user", {"text": "handled"})
        processed["processed_at"] = "done"
        add_event(state, "user_message", "user", {"text": "pending"})

        status = injected_message_status(state, ["handled", "pending", "missing"])

        self.assertEqual(status["total"], 3)
        self.assertEqual(status["matched"], 2)
        self.assertEqual(status["processed"], 1)
        self.assertEqual(status["unprocessed"], 2)
        self.assertEqual(status["unmatched"], ["missing"])

    def test_injected_message_status_prefers_event_ids(self):
        state = default_state()
        old = add_event(state, "user_message", "user", {"text": "same"})
        old["processed_at"] = "done"
        new = add_event(state, "user_message", "user", {"text": "same"})

        status = injected_message_status(state, ["same"], event_ids=[new["id"]])

        self.assertEqual(status["matched"], 1)
        self.assertEqual(status["processed"], 0)
        self.assertEqual(status["unprocessed"], 1)
        self.assertEqual(status["events"][0]["id"], new["id"])

    def test_queued_message_event_id_parses_message_output(self):
        self.assertEqual(queued_message_event_id("queued message event #42\n"), 42)
        self.assertIsNone(queued_message_event_id("no id"))

    def test_format_dogfood_report_warns_for_unprocessed_injected_messages(self):
        report = {
            "generated_at": "now",
            "workspace": "/tmp/dog",
            "exit_code": 0,
            "duration_seconds": 1.0,
            "events": {"processed": 1, "total": 2, "by_type": {"startup": 1, "user_message": 1}},
            "runtime_status": {},
            "model_phases": {},
            "outbox": {"total": 0, "unread": 0, "by_type": {}},
            "actions": {},
            "read_inspection": {},
            "tasks": {},
            "agent_runs": {},
            "programmer_loop": {},
            "verification_runs": 0,
            "write_runs": 0,
            "injected_messages": {"total": 1, "processed": 0, "unprocessed": 1},
            "model_enabled": True,
            "next_move": "inspect",
        }

        text = format_dogfood_report(report)

        self.assertIn("injected_messages: processed=0/1 unprocessed=1", text)
        self.assertIn("warning: injected user message(s) were left unprocessed", text)
        self.assertIn("model_enabled: True", text)

    def test_suppress_processed_injected_dropped_threads(self):
        report = {
            "injected_messages": {
                "events": [
                    {"text": "handled request", "processed": True},
                    {"text": "pending request", "processed": False},
                ]
            },
            "active_dropped_threads": {
                "thought_count": 2,
                "latest": [
                    "User request context: handled request",
                    "User request context: pending request",
                ],
                "thought_id": 7,
            },
        }

        suppress_processed_injected_dropped_threads(report)

        self.assertEqual(report["active_dropped_threads"]["thought_count"], 1)
        self.assertEqual(report["active_dropped_threads"]["latest"], ["User request context: pending request"])

    def test_prepopulate_project_snapshot_writes_dogfood_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "src").mkdir()
            (workspace / "tests").mkdir()
            (workspace / "README.md").write_text("# Demo\n", encoding="utf-8")
            (workspace / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")

            report = prepopulate_project_snapshot(workspace)
            state = json.loads((workspace / STATE_FILE).read_text(encoding="utf-8"))

            self.assertEqual(len(report["read_files"]), 2)
            self.assertEqual(state["memory"]["deep"]["project_snapshot"]["package"]["name"], "demo")
            self.assertEqual(state["dogfood"]["pre_snapshot"]["path"], str(workspace.resolve()))

    def test_seed_ready_coding_task_creates_dispatchable_planned_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)

            summary = seed_ready_coding_task(workspace)
            second = seed_ready_coding_task(workspace)
            state = json.loads((workspace / STATE_FILE).read_text(encoding="utf-8"))

            self.assertEqual(summary["status"], "ready")
            self.assertTrue(summary["auto_execute"])
            self.assertEqual(second["id"], summary["id"])
            self.assertEqual(len(state["tasks"]), 1)
            task = state["tasks"][0]
            self.assertEqual(task["kind"], "coding")
            self.assertEqual(task["status"], "ready")
            self.assertTrue(task["auto_execute"])
            self.assertIn("Proposed by mew", task["notes"])
            self.assertGreaterEqual(len(task["plans"]), 1)
            self.assertEqual(task["latest_plan_id"], second["plan_id"])

    def test_seed_ready_coding_task_clears_stale_shell_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            seed_ready_coding_task(workspace)
            state_path = workspace / STATE_FILE
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["tasks"][0]["command"] = "echo stale"
            state["tasks"][0]["agent_run_id"] = 99
            state_path.write_text(json.dumps(state), encoding="utf-8")

            seed_ready_coding_task(workspace)
            state = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertEqual(state["tasks"][0]["command"], "")
            self.assertIsNone(state["tasks"][0]["agent_run_id"])

    def test_seed_ready_coding_task_preserves_active_agent_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            seed_ready_coding_task(workspace)
            state_path = workspace / STATE_FILE
            state = json.loads(state_path.read_text(encoding="utf-8"))
            task = state["tasks"][0]
            initial_plan_count = len(task["plans"])
            state["agent_runs"].append(
                {
                    "id": 7,
                    "task_id": task["id"],
                    "plan_id": task["latest_plan_id"],
                    "purpose": "implementation",
                    "status": "running",
                }
            )
            task["status"] = "running"
            task["agent_run_id"] = 7
            state_path.write_text(json.dumps(state), encoding="utf-8")

            summary = seed_ready_coding_task(workspace)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            task = state["tasks"][0]

            self.assertEqual(summary["active_run_id"], 7)
            self.assertEqual(task["status"], "running")
            self.assertEqual(task["agent_run_id"], 7)
            self.assertEqual(len(task["plans"]), initial_plan_count)

    def test_wait_for_active_agent_runs_invokes_agent_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / STATE_DIR).mkdir()
            state = default_state()
            state["agent_runs"].append({"id": 7, "status": "running", "external_pid": 123})
            state["agent_runs"].append({"id": 8, "status": "completed"})
            (workspace / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")

            class Result:
                returncode = 0
                stdout = "waited\n"
                stderr = ""

            collect = {"command": ["mew"], "exit_code": 0, "stdout": "line1\nline2\n", "stderr": ""}
            with patch(
                "mew.dogfood.run_command",
                return_value=collect,
            ) as collector:
                with patch("mew.dogfood.subprocess.run", return_value=Result()) as waiter:
                    results = wait_for_active_agent_runs(workspace, 5.0, env={"PYTHONPATH": "src"})

            self.assertEqual(active_agent_run_ids(workspace), [7])
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["run_id"], 7)
            wait_command = waiter.call_args.args[0]
            self.assertEqual(wait_command[:3], ["ai-cli", "wait", "123"])
            self.assertIn("--timeout", wait_command)
            collect_command = collector.call_args.args[0]
            self.assertEqual(collect_command[2:5], ["mew", "agent", "result"])
            self.assertIn("7", collect_command)
            self.assertEqual(results[0]["stdout_tail"], ["waited"])
            self.assertEqual(results[0]["collect_result"]["stdout_tail"], ["line1", "line2"])

    def test_tail_lines_clips_long_report_lines(self):
        text = "short\n" + ("x" * 1200)

        self.assertEqual(tail_lines(text, limit=2)[0], "short")
        self.assertTrue(tail_lines(text, limit=2)[1].endswith("...<truncated>"))
        self.assertLessEqual(len(tail_lines(text, limit=2)[1]), 1014)

    def test_wait_for_active_agent_runs_timeout_leaves_state_uncollected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / STATE_DIR).mkdir()
            state = default_state()
            state["agent_runs"].append({"id": 7, "status": "running", "external_pid": 123})
            (workspace / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")

            with patch("mew.dogfood.subprocess.run", side_effect=subprocess.TimeoutExpired(["ai-cli"], 1)):
                with patch("mew.dogfood.run_command") as collector:
                    results = wait_for_active_agent_runs(workspace, 0.01)

            self.assertTrue(results[0]["timed_out"])
            collector.assert_not_called()
            state = json.loads((workspace / STATE_FILE).read_text(encoding="utf-8"))
            self.assertEqual(state["agent_runs"][0]["status"], "running")

    def test_wait_for_active_agent_runs_marks_ai_cli_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / STATE_DIR).mkdir()
            state = default_state()
            state["agent_runs"].append({"id": 7, "status": "running", "external_pid": 123})
            (workspace / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")

            class Result:
                returncode = 1
                stdout = ""
                stderr = "Timed out after 180 seconds waiting for processes"

            with patch("mew.dogfood.subprocess.run", return_value=Result()):
                with patch("mew.dogfood.run_command") as collector:
                    results = wait_for_active_agent_runs(workspace, 5.0)

            self.assertTrue(results[0]["timed_out"])
            collector.assert_not_called()

    def test_post_wait_agent_reflex_runs_sweeps_around_review_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            args = SimpleNamespace(
                allow_agent_run=True,
                wait_agent_runs=5.0,
                review_model="codex-ultra",
                agent_stale_minutes=3.0,
                agent_result_timeout=4.0,
                agent_start_timeout=6.0,
            )
            command_result = {"command": ["mew"], "exit_code": 0, "stdout": "swept\n", "stderr": ""}
            with patch("mew.dogfood.run_command", return_value=command_result) as runner:
                with patch(
                    "mew.dogfood.wait_for_active_agent_runs",
                    return_value=[{"run_id": 9, "exit_code": 0}],
                ) as waiter:
                    results = run_post_wait_agent_reflex(workspace, args, env={"PYTHONPATH": "src"})

            self.assertEqual([result["phase"] for result in results], ["post_wait_sweep", "review_wait", "post_review_sweep"])
            self.assertEqual(waiter.call_count, 1)
            self.assertEqual(runner.call_count, 2)
            first_command = runner.call_args_list[0].args[0]
            self.assertEqual(first_command[:5], [sys.executable, "-m", "mew", "agent", "sweep"])
            self.assertIn("--start-reviews", first_command)
            self.assertEqual(first_command[first_command.index("--agent-model") + 1], "codex-ultra")
            self.assertEqual(first_command[first_command.index("--stale-minutes") + 1], "3.0")
            self.assertEqual(first_command[first_command.index("--agent-result-timeout") + 1], "4.0")
            self.assertEqual(first_command[first_command.index("--agent-start-timeout") + 1], "6.0")
            self.assertEqual(runner.call_args_list[0].kwargs["timeout"], 60.0)

    def test_agent_reflex_sweep_timeout_honors_large_agent_timeouts(self):
        args = SimpleNamespace(agent_result_timeout=90.0, agent_start_timeout=45.0)

        self.assertEqual(agent_reflex_sweep_timeout(args), 165.0)

    def test_run_dogfood_skips_cleanup_when_agent_run_is_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "dog"
            workspace.mkdir()
            args = SimpleNamespace(
                workspace=None,
                source_workspace=None,
                pre_snapshot=False,
                seed_ready_coding_task=False,
                cleanup=True,
            )
            report = {"agent_runs": {"by_status": {"running": 1}}, "kept": False}

            with patch("mew.dogfood.prepare_dogfood_workspace", return_value=(workspace, True)):
                with patch("mew.dogfood._run_dogfood_in_workspace", return_value=report):
                    result = run_dogfood(args)

            self.assertTrue(workspace.exists())
            self.assertTrue(result["kept"])
            self.assertEqual(result["cleanup_skipped_reason"], "active_agent_runs")

    def test_run_dogfood_loop_keeps_workspace_on_exception_with_active_agent_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "dog"
            workspace.mkdir()
            args = SimpleNamespace(
                workspace=None,
                source_workspace=None,
                pre_snapshot=False,
                seed_ready_coding_task=False,
                cleanup=True,
                cycles=2,
                cycle_gap=0,
            )
            report = {"agent_runs": {"by_status": {"running": 1}}, "kept": False}

            with patch("mew.dogfood.prepare_dogfood_workspace", return_value=(workspace, True)):
                with patch("mew.dogfood._run_dogfood_in_workspace", side_effect=[report, RuntimeError("boom")]):
                    with self.assertRaises(RuntimeError):
                        run_dogfood_loop(args)

            self.assertTrue(workspace.exists())

    def test_format_dogfood_loop_report_summarizes_cycles(self):
        text = format_dogfood_loop_report(
            {
                "generated_at": "now",
                "workspace": "/tmp/dog",
                "cycle_count": 2,
                "exit_codes": [0, 0],
                "final_events": {"processed": 3, "total": 3},
                "final_model_phases": {"think_ok": 2, "act_ok": 2},
                "final_runtime_status": {
                    "last_cycle_reason": "passive_tick",
                    "last_cycle_duration_seconds": 1.2,
                    "last_processed_count": 3,
                },
                "final_plan_schema_issues": {"count": 1, "by_level": {"warning": 1}, "latest": []},
                "final_agent_runs": {"total": 1, "by_status": {"running": 1}},
                "final_dropped_threads": {"thought_count": 1, "latest": ["carry this"]},
                "final_active_dropped_threads": {"thought_count": 1, "thought_id": 2, "latest": ["carry this"]},
                "final_next_move": "keep going",
                "final_project_snapshot": {"updated_at": "now", "project_types": ["python"]},
                "cycles": [
                    {
                        "cycle": 1,
                        "exit_code": 0,
                        "duration_seconds": 1.2,
                        "events": {"processed": 1, "total": 1},
                        "model_phases": {"think_ok": 1, "act_ok": 1},
                        "dropped_threads": {"thought_count": 0, "latest": []},
                        "active_dropped_threads": {"thought_count": 0, "latest": []},
                        "plan_schema_issues": {"count": 0, "by_level": {}, "latest": []},
                        "agent_runs": {"total": 0},
                        "next_move": "cycle one",
                    },
                    {
                        "cycle": 2,
                        "exit_code": 0,
                        "duration_seconds": 1.4,
                        "events": {"processed": 3, "total": 3},
                        "model_phases": {"think_ok": 2, "act_ok": 2},
                        "dropped_threads": {"thought_count": 1, "latest": ["carry this"]},
                        "active_dropped_threads": {"thought_count": 1, "thought_id": 2, "latest": ["carry this"]},
                        "plan_schema_issues": {"count": 1, "by_level": {"warning": 1}, "latest": []},
                        "agent_runs": {"total": 1},
                        "agent_wait_results": [{"run_id": 1, "exit_code": 0, "stdout_tail": ["done"]}],
                        "next_move": "keep going",
                    },
                ],
            }
        )

        self.assertIn("cycles: 2", text)
        self.assertIn("Cycle summaries", text)
        self.assertIn("final_dropped_threads", text)
        self.assertIn("final_active_dropped_threads", text)
        self.assertIn("dropped_threads=1", text)
        self.assertIn("active_dropped_threads=1", text)
        self.assertIn("schema_issues=1", text)
        self.assertIn("final_plan_schema_issues", text)
        self.assertIn("final_agent_runs", text)
        self.assertIn("agent_runs=1", text)
        self.assertIn("agent_waits=1", text)
        self.assertIn("wait run #1", text)
        self.assertIn("final_runtime_cycle", text)
        self.assertIn("Final project snapshot", text)
        self.assertIn("Final next useful move: keep going", text)


if __name__ == "__main__":
    unittest.main()
