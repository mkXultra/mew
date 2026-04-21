import os
import tempfile
import unittest
from unittest.mock import patch

from mew.brief import (
    build_brief,
    build_brief_data,
    build_focus_data,
    coding_self_improve_focus_from_friction,
    format_focus,
    next_move,
    review_runs_needing_followup,
)
from mew.programmer import (
    create_follow_up_task_from_review,
    create_implementation_run_from_plan,
    create_review_run_for_implementation,
    create_task_plan,
)
from mew.state import add_outbox_message, add_question, default_state, mark_question_deferred


def add_task(
    state,
    status="todo",
    auto_execute=False,
    task_id=1,
    title="Implement next move",
    priority="normal",
    kind="",
):
    task = {
        "id": task_id,
        "title": title,
        "description": "Make brief actionable.",
        "status": status,
        "priority": priority,
        "kind": kind,
        "notes": "",
        "command": "",
        "cwd": ".",
        "auto_execute": auto_execute,
        "agent_backend": "",
        "agent_model": "",
        "agent_prompt": "",
        "agent_run_id": None,
        "plans": [],
        "latest_plan_id": None,
        "runs": [],
        "created_at": "t",
        "updated_at": "t",
    }
    state["tasks"].append(task)
    return task


class BriefTests(unittest.TestCase):
    def test_next_move_waits_when_idle(self):
        self.assertEqual(next_move(default_state()), "wait for the next user request")

    def test_next_move_coding_filter_suggests_native_self_improve_when_no_tasks(self):
        with patch(
            "mew.brief.coding_self_improve_focus_from_friction",
            return_value="Advance M5 audited self-improvement loop",
        ):
            self.assertEqual(
                next_move(default_state(), kind="coding"),
                "start a native self-improvement session with `./mew self-improve --start-session --focus 'Advance M5 audited self-improvement loop'`",
            )

    def test_next_move_coding_filter_prefers_same_day_context_checkpoint_recovery_while_waiting_for_agent(self):
        state = default_state()
        state["user_status"] = {"mode": "waiting_for_agent"}

        with patch("mew.brief.now_iso", return_value="2026-04-21T12:00:00Z"), patch(
            "mew.brief.latest_context_checkpoint",
            return_value={
                "name": "Long session checkpoint: M6.7 reentry",
                "created_at": "2026-04-21T07:12:09Z",
            },
        ):
            self.assertEqual(
                next_move(state, kind="coding"),
                "recover the latest context checkpoint with `./mew context --load --limit 1`",
            )
            data = build_focus_data(state, limit=3)
            self.assertEqual(
                data["coding_next_move"],
                "recover the latest context checkpoint with `./mew context --load --limit 1`",
            )

    def test_next_move_coding_filter_keeps_self_improve_for_stale_context_checkpoint_while_waiting_for_agent(self):
        state = default_state()
        state["user_status"] = {"mode": "waiting_for_agent"}

        with patch("mew.brief.now_iso", return_value="2026-04-21T12:00:00Z"), patch(
            "mew.brief.latest_context_checkpoint",
            return_value={
                "name": "Older checkpoint",
                "created_at": "2026-04-20T23:59:59Z",
            },
        ), patch(
            "mew.brief.coding_self_improve_focus_from_friction",
            return_value="Advance M5 audited self-improvement loop",
        ):
            self.assertEqual(
                next_move(state, kind="coding"),
                "start a native self-improvement session with `./mew self-improve --start-session --focus 'Advance M5 audited self-improvement loop'`",
            )
            data = build_focus_data(state, limit=3)
            self.assertEqual(
                data["coding_next_move"],
                "start a native self-improvement session with `./mew self-improve --start-session --focus 'Advance M5 audited self-improvement loop'`",
            )

    def test_next_move_skips_blocked_task_for_self_improve(self):
        state = default_state()
        add_task(state, status="blocked", task_id=1, title="Wait for long proof", kind="coding")

        with patch(
            "mew.brief.coding_self_improve_focus_from_friction",
            return_value="Advance M5 audited self-improvement loop",
        ):
            self.assertEqual(
                next_move(state, kind="coding"),
                "start a native self-improvement session with `./mew self-improve --start-session --focus 'Advance M5 audited self-improvement loop'`",
            )

    def test_next_move_coding_filter_in_empty_project_suggests_task_creation(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                self.assertEqual(
                    next_move(default_state(), kind="coding"),
                    "add a coding task with `mew task add ... --kind coding --ready`",
                )
                data = build_focus_data(default_state(), limit=3)
                self.assertEqual(
                    data["coding_next_move"],
                    "add a coding task with `mew task add ... --kind coding --ready`",
                )
                self.assertIn("Coding: add a coding task", format_focus(data))
            finally:
                os.chdir(old_cwd)

    def test_coding_self_improve_focus_keeps_generic_fallback_outside_mew(self):
        with patch("mew.brief.current_project_looks_like_mew", return_value=False):
            self.assertEqual(
                coding_self_improve_focus_from_friction(default_state(), kind="coding"),
                "Pick the next small mew improvement",
            )
        self.assertEqual(
            coding_self_improve_focus_from_friction(default_state(), kind="research"),
            "Pick the next small mew improvement",
        )

    def test_next_move_prefers_open_question(self):
        state = default_state()
        add_task(state)
        add_question(state, "What should I do?", related_task_id=1)

        self.assertIn("mew reply", next_move(state))

    def test_next_move_prefers_running_task_over_unrelated_question(self):
        state = default_state()
        add_task(state, status="ready", task_id=1, title="Implement later task")
        add_task(
            state,
            status="running",
            task_id=2,
            title="Implement active task",
            priority="high",
        )
        add_question(state, "What should I do with task #1?", related_task_id=1)

        self.assertEqual(next_move(state), "advance coding task #2: Implement active task")

    def test_next_move_answers_running_task_question_first(self):
        state = default_state()
        add_task(state, status="ready", task_id=1, title="Implement later task")
        add_task(
            state,
            status="running",
            task_id=2,
            title="Implement active task",
            priority="high",
        )
        add_question(state, "What should I do with task #1?", related_task_id=1)
        running_question, _created = add_question(
            state,
            "What should I do with task #2?",
            related_task_id=2,
        )

        self.assertEqual(
            next_move(state),
            f"answer question #{running_question.get('id')} with `./mew reply {running_question.get('id')} \"...\"`",
        )

    def test_next_move_ignores_deferred_question(self):
        state = default_state()
        add_task(state)
        question, _ = add_question(state, "What should I do?", related_task_id=1)
        mark_question_deferred(state, question, reason="later")

        self.assertEqual(next_move(state), "enter coding cockpit for task #1 with `./mew code 1`")

    def test_next_move_kind_filter_ignores_unrelated_questions(self):
        state = default_state()
        add_task(state, task_id=1, title="補助金について調べる", kind="research")
        add_task(state, task_id=2, title="Improve work cockpit", kind="coding")
        add_question(state, "Which city should I research?", related_task_id=1)

        self.assertIn("mew reply", next_move(state))
        self.assertEqual(next_move(state, kind="coding"), "enter coding cockpit for task #2 with `./mew code 2`")

    def test_focus_global_surfaces_coding_next_move(self):
        state = default_state()
        add_task(state, task_id=1, title="Research grants", kind="research")
        add_task(state, task_id=2, title="Improve cockpit", kind="coding")
        add_question(state, "Which city?", related_task_id=1)

        data = build_focus_data(state, limit=3)
        focus = format_focus(data)

        self.assertIn("mew reply", data["next_move"])
        self.assertEqual(
            data["coding_next_move"],
            "enter coding cockpit for task #2 with `./mew code 2`",
        )
        self.assertIn("Coding: enter coding cockpit for task #2", focus)

    def test_focus_global_surfaces_mew_self_improve_when_research_blocks(self):
        state = default_state()
        add_task(state, task_id=1, title="Research grants", kind="research")
        add_question(state, "Which city?", related_task_id=1)

        with patch("mew.brief.current_project_looks_like_mew", return_value=True), patch(
            "mew.brief.coding_self_improve_focus_from_friction",
            return_value="Advance M5 audited self-improvement loop",
        ):
            data = build_focus_data(state, limit=3)
        focus = format_focus(data)

        self.assertIn("mew reply", data["next_move"])
        self.assertEqual(
            data["coding_next_move"],
            "start a native self-improvement session with `./mew self-improve --start-session --focus 'Advance M5 audited self-improvement loop'`",
        )
        self.assertIn("Coding: start a native self-improvement session", focus)

    def test_brief_kind_filter_scopes_tasks_questions_and_messages(self):
        state = default_state()
        add_task(state, task_id=1, title="Research grants", kind="research")
        add_task(state, task_id=2, title="Improve work cockpit", kind="coding")
        add_question(state, "Which city should I research?", related_task_id=1)
        for index in range(6):
            add_outbox_message(state, "info", f"research message {index}", related_task_id=1)
        add_outbox_message(state, "info", "coding message", related_task_id=2)
        state["verification_runs"].extend(
            [
                {"id": 1, "task_id": 1, "command": "research verify", "exit_code": 0},
                {"id": 2, "task_id": 2, "command": "coding verify", "exit_code": 0},
            ]
        )
        state["write_runs"].extend(
            [
                {"id": 1, "task_id": 1, "operation": "write_file", "path": "research.md"},
                {"id": 2, "task_id": 2, "operation": "write_file", "path": "coding.md"},
            ]
        )
        state["runtime_effects"].extend(
            [
                {"id": 1, "task_id": 1, "status": "verified", "reason": "research"},
                {"id": 2, "task_id": 2, "status": "verified", "reason": "coding"},
            ]
        )

        brief = build_brief(state, kind="coding")
        data = build_brief_data(state, kind="coding")
        focus = build_focus_data(state, kind="coding")

        self.assertIn("Mew brief (coding)", brief)
        self.assertIn("Improve work cockpit", brief)
        self.assertIn("coding message", brief)
        self.assertNotIn("Research grants", brief)
        self.assertNotIn("Which city should I research?", brief)
        self.assertNotIn("research message", brief)
        self.assertIn("coding verify", brief)
        self.assertIn("coding.md", brief)
        self.assertIn("reason=coding", brief)
        self.assertNotIn("research verify", brief)
        self.assertNotIn("research.md", brief)
        self.assertNotIn("reason=research", brief)
        self.assertEqual(data["kind"], "coding")
        self.assertEqual(data["open_task_count"], 1)
        self.assertEqual(data["unread_outbox_count"], 1)
        self.assertEqual(data["unread_outbox"][0]["text"], "coding message")
        self.assertEqual(data["recent_verification"][0]["command"], "coding verify")
        self.assertEqual(data["recent_writes"][0]["path"], "coding.md")
        self.assertEqual(data["recent_runtime_effects"][0]["reason"], "coding")
        self.assertEqual(data["recent_activity"], [])
        self.assertEqual(data["thought_journal"], [])
        self.assertEqual(data["recent_steps"], [])
        self.assertEqual(
            data["next_move"],
            "enter coding cockpit for task #2 with `./mew code 2`",
        )
        self.assertEqual(focus["unread_outbox_count"], 1)

    def test_next_move_recommends_review_for_completed_implementation(self):
        state = default_state()
        task = add_task(state)
        plan = create_task_plan(state, task)
        run = create_implementation_run_from_plan(state, task, plan, dry_run=True)
        run["status"] = "completed"

        self.assertEqual(next_move(state), "review implementation run #1 with `./mew agent review 1`")
        self.assertIn("review needed: run #1", build_brief(state))

    def test_dry_run_review_does_not_hide_needed_real_review(self):
        state = default_state()
        task = add_task(state)
        plan = create_task_plan(state, task)
        implementation = create_implementation_run_from_plan(state, task, plan, dry_run=True)
        implementation["status"] = "completed"
        review = create_review_run_for_implementation(state, task, implementation, plan=plan)
        review["status"] = "dry_run"

        self.assertEqual(next_move(state), "review implementation run #1 with `./mew agent review 1`")
        self.assertIn("review needed: run #1", build_brief(state))

    def test_next_move_recommends_dispatch_for_ready_planned_task(self):
        state = default_state()
        task = add_task(state, status="ready", auto_execute=True)
        create_task_plan(state, task)

        self.assertIn("mew task dispatch 1", next_move(state))
        self.assertIn("dispatchable: task #1", build_brief(state))

    def test_next_move_recommends_starting_buddy_dry_run(self):
        state = default_state()
        task = add_task(state, status="ready", auto_execute=False)
        plan = create_task_plan(state, task)
        create_implementation_run_from_plan(state, task, plan, dry_run=True)

        self.assertEqual(
            next_move(state),
            "dispatch dry-run task #1 for real with `./mew buddy --task 1 --dispatch`",
        )
        self.assertIn("dry-run ready: run #1 task=#1", build_brief(state))
        data = build_brief_data(state)
        self.assertEqual(data["programmer_queue"]["dry_run_ready"][0]["id"], 1)

    def test_next_move_recommends_plan_for_unplanned_task(self):
        state = default_state()
        add_task(state)

        self.assertEqual(next_move(state), "enter coding cockpit for task #1 with `./mew code 1`")

    def test_next_move_does_not_programmer_plan_admin_task(self):
        state = default_state()
        task = add_task(state)
        task["title"] = "Pay the electric bill"
        task["kind"] = "admin"

        self.assertEqual(
            next_move(state),
            "take one concrete admin step on task #1: Pay the electric bill",
        )

    def test_next_move_does_not_dispatch_admin_task_with_existing_plan(self):
        state = default_state()
        task = add_task(state, status="ready", auto_execute=True)
        task["title"] = "Pay the electric bill"
        task["kind"] = "admin"
        task["plans"] = [{"id": 1, "status": "planned"}]
        task["latest_plan_id"] = 1

        self.assertEqual(
            next_move(state),
            "take one concrete admin step on task #1: Pay the electric bill",
        )

    def test_processed_review_does_not_keep_needing_followup(self):
        state = default_state()
        task = add_task(state)
        review = {
            "id": 2,
            "task_id": task["id"],
            "purpose": "review",
            "status": "completed",
            "result": "STATUS: pass\nFOLLOW_UP:\n- none",
            "stdout": "",
            "followup_task_id": None,
        }

        create_follow_up_task_from_review(state, task, review)
        state["agent_runs"].append(review)

        self.assertEqual(review_runs_needing_followup(state), [])

    def test_brief_surfaces_recent_verification(self):
        state = default_state()
        state["verification_runs"].append(
            {
                "id": 1,
                "command": "python -m unittest",
                "exit_code": 0,
                "finished_at": "done",
            }
        )

        brief = build_brief(state)

        self.assertIn("Recent verification", brief)
        self.assertIn("#1 [passed]", brief)

    def test_brief_surfaces_recent_writes(self):
        state = default_state()
        state["write_runs"].append(
            {
                "id": 1,
                "operation": "write_file",
                "path": "/tmp/project/note.md",
                "changed": True,
                "dry_run": False,
                "written": True,
                "verification_run_id": 7,
                "verification_exit_code": 0,
                "updated_at": "done",
            }
        )

        brief = build_brief(state)
        data = build_brief_data(state)

        self.assertIn("Recent writes", brief)
        self.assertIn("#1 [write_file]", brief)
        self.assertIn("verification=#7 exit=0", brief)
        self.assertEqual(data["recent_writes"][0]["path"], "/tmp/project/note.md")
        self.assertEqual(data["recent_writes"][0]["verification_run_id"], 7)

    def test_brief_surfaces_recent_runtime_effects(self):
        state = default_state()
        state["runtime_effects"].append(
            {
                "id": 1,
                "event_id": 2,
                "reason": "passive_tick",
                "status": "verified",
                "action_types": ["run_verification"],
                "verification_run_ids": [3],
                "write_run_ids": [],
            }
        )

        brief = build_brief(state)
        data = build_brief_data(state)

        self.assertIn("Recent runtime effects", brief)
        self.assertIn("#1 [verified] event=#2 reason=passive_tick", brief)
        self.assertEqual(data["recent_runtime_effects"][0]["status"], "verified")

    def test_brief_surfaces_native_work_skip_recovery(self):
        state = default_state()
        state["runtime_status"]["last_native_work_step_skip"] = "pending_write_approval"
        state["runtime_status"]["last_native_work_skip_recovery"] = {
            "action": "resolve_pending_write_approval",
            "command": "mew work 1 --approve-tool 3",
        }
        state["runtime_status"]["last_native_work_recovery"] = {
            "action": "auto_retry_verification_completed",
            "status": "completed",
            "command": "python -V",
        }
        state["runtime_status"]["last_startup_repair_at"] = "2026-04-18T09:00:00Z"
        state["runtime_status"]["last_startup_repairs"] = [
            {
                "type": "interrupted_runtime_effect",
                "effect_id": 1,
                "old_status": "planning",
                "new_status": "interrupted",
                "recovery_decision": {
                    "action": "rerun_event",
                    "effect_classification": "no_action_committed",
                },
                "recovery_followup": {
                    "action": "requeue_event",
                    "status": "requeued",
                    "command": "./mew run --once",
                },
            }
        ]

        brief = build_brief(state)

        self.assertIn(
            "native_work_skip: pending_write_approval next=mew work 1 --approve-tool 3",
            brief,
        )
        self.assertIn(
            "native_work_recovery: auto_retry_verification_completed status=completed command=python -V",
            brief,
        )
        self.assertIn(
            "startup_repair: 1 item(s) at=2026-04-18T09:00:00Z "
            "types=interrupted_runtime_effect decisions=rerun_event followups=requeue_event",
            brief,
        )

    def test_brief_hides_stale_native_work_skip_when_active_work_session_exists(self):
        state = default_state()
        add_task(state, task_id=7, title="Resume active coding task", kind="coding")
        state["runtime_status"]["last_native_work_step_skip"] = "no_active_work_session"
        state["runtime_status"]["last_native_work_skip_recovery"] = {
            "action": "focus_coding",
            "command": "./mew focus --kind coding",
        }
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Resume active coding task",
                "goal": "Keep brief aligned with the actual active work session.",
                "created_at": "then",
                "updated_at": "now",
                "tool_calls": [],
                "model_turns": [],
            }
        )

        brief = build_brief(state, kind="coding")

        self.assertNotIn("native_work_skip:", brief)
        self.assertIn("Next useful move: enter coding cockpit for active work session #3 task #7", brief)

    def test_brief_prefers_continue_command_for_interrupted_active_work_session(self):
        state = default_state()
        add_task(state, task_id=7, title="Resume interrupted coding task", kind="coding")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Resume interrupted coding task",
                "goal": "Keep brief aligned with the actual interrupted work session.",
                "created_at": "then",
                "updated_at": "now",
                "default_options": {
                    "auth": "auth.json",
                    "model_backend": "codex",
                    "allow_read": ["."],
                    "allow_write": ["."],
                    "allow_verify": True,
                    "verify_command": "uv run python -m unittest tests.test_brief",
                    "compact_live": True,
                    "no_prompt_approval": True,
                },
                "tool_calls": [],
                "model_turns": [
                    {
                        "id": 12,
                        "status": "failed",
                        "error": "request timed out",
                        "model_metrics": {
                            "think": {"prompt_chars": 63842, "timeout_seconds": 45.0},
                        },
                    }
                ],
            }
        )

        brief = build_brief(state, kind="coding")

        self.assertIn(
            "Next useful move: resume interrupted active work session #3 task #7 with "
            "`./mew work 7 --live --auth auth.json --model-backend codex --allow-read . "
            "--allow-write . --allow-verify --verify-command 'uv run python -m unittest "
            "tests.test_brief' --compact-live --no-prompt-approval --max-steps 1`.",
            brief,
        )

    def test_brief_leaves_paused_active_work_session_paused(self):
        state = default_state()
        add_task(state, task_id=7, title="Paused debug target", kind="coding")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Paused debug target",
                "goal": "Leave this paused until a real invalidation appears.",
                "created_at": "then",
                "updated_at": "now",
                "stop_requested_at": "2026-04-21T15:00:00Z",
                "stop_reason": "paused debug target",
                "default_options": {"allow_read": ["."]},
                "tool_calls": [],
                "model_turns": [],
            }
        )

        brief = build_brief(state, kind="coding")

        self.assertIn("Next useful move: leave paused work session #3 task #7 paused", brief)

    def test_brief_uses_checkpoint_guided_last_request_for_same_day_coding_reentry(self):
        state = default_state()
        state["user_status"] = {
            "mode": "waiting_for_agent",
            "last_request": "No. Do not continue #333 in its current 3-file shape.",
        }

        with patch("mew.brief.now_iso", return_value="2026-04-21T15:35:26Z"), patch(
            "mew.brief.latest_context_checkpoint",
            return_value={
                "name": "Long session checkpoint: post-m6-9-prep-docs",
                "created_at": "2026-04-21T15:35:25Z",
            },
        ):
            brief = build_brief(state, kind="coding", include_context_checkpoint=True)

        self.assertIn(
            "user: waiting_for_agent last_request=(checkpoint-guided reentry; see context checkpoint)",
            brief,
        )
        self.assertNotIn("No. Do not continue #333", brief)

    def test_brief_hides_plan_needed_for_task_with_active_work_session(self):
        state = default_state()
        add_task(state, task_id=7, title="Do not duplicate active task", kind="coding")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Do not duplicate active task",
                "goal": "Avoid queue duplication.",
                "created_at": "then",
                "updated_at": "now",
                "tool_calls": [],
                "model_turns": [],
            }
        )

        brief = build_brief(state, kind="coding")
        data = build_brief_data(state, kind="coding")

        self.assertNotIn("- plan needed: task #7", brief)
        self.assertEqual(data["programmer_queue"]["plan_needed"], [])

    def test_brief_marks_rolled_back_recent_writes(self):
        state = default_state()
        state["write_runs"].append(
            {
                "id": 2,
                "operation": "edit_file",
                "path": "/tmp/project/app.py",
                "changed": True,
                "dry_run": False,
                "written": True,
                "rolled_back": True,
            }
        )

        brief = build_brief(state)
        data = build_brief_data(state)

        self.assertIn("rolled_back=true", brief)
        self.assertTrue(data["recent_writes"][0]["rolled_back"])

    def test_brief_surfaces_recent_thought_journal(self):
        state = default_state()
        add_task(state)
        state["thought_journal"].append(
            {
                "id": 1,
                "event_id": 2,
                "event_type": "passive_tick",
                "at": "now",
                "summary": "Continue the self-improvement thread.",
                "open_threads": ["Check the verification result next."],
                "resolved_threads": [],
                "counts": {"actions": 1},
            }
        )

        brief = build_brief(state)

        self.assertIn("Thought journal", brief)
        self.assertIn("#1 passive_tick#2", brief)
        self.assertIn("open_threads=1", brief)

    def test_brief_hides_internal_thread_counts_when_idle(self):
        state = default_state()
        state["thought_journal"].append(
            {
                "id": 1,
                "event_id": 2,
                "event_type": "passive_tick",
                "at": "now",
                "summary": "Idle bookkeeping.",
                "open_threads": ["Internal memory thread."],
                "dropped_threads": ["Old internal thread."],
                "resolved_threads": [],
                "counts": {"actions": 1},
            }
        )

        brief = build_brief(state)

        self.assertIn("Thought journal", brief)
        self.assertIn("Idle bookkeeping.", brief)
        self.assertNotIn("open_threads=1", brief)
        self.assertNotIn("dropped_threads=1", brief)

    def test_brief_surfaces_recent_activity(self):
        state = default_state()
        state["thought_journal"].append(
            {
                "id": 1,
                "event_id": 2,
                "event_type": "passive_tick",
                "at": "now",
                "summary": "Inspected the workspace.",
                "open_threads": [],
                "resolved_threads": [],
                "actions": [
                    {"type": "inspect_dir", "path": "/tmp/project"},
                    {"type": "read_file", "path": "/tmp/project/README.md"},
                ],
                "counts": {"actions": 2, "messages": 2},
            }
        )

        brief = build_brief(state)
        data = build_brief_data(state)

        self.assertIn("Recent activity", brief)
        self.assertIn("inspect_dir /tmp/project", brief)
        self.assertEqual(data["recent_activity"][0]["summary"], "Inspected the workspace.")

    def test_brief_labels_manual_step_activity(self):
        state = default_state()
        state["thought_journal"].append(
            {
                "id": 1,
                "event_id": 2,
                "event_type": "passive_tick",
                "cycle_reason": "manual_step",
                "at": "now",
                "summary": "Read and remembered one thing.",
                "open_threads": [],
                "resolved_threads": [],
                "actions": [{"type": "read_file", "path": "/tmp/project/README.md"}],
                "counts": {"actions": 1, "messages": 1},
            }
        )

        brief = build_brief(state)

        self.assertIn("passive_tick/manual_step", brief)

    def test_brief_surfaces_recent_step_runs(self):
        state = default_state()
        state["step_runs"].append(
            {
                "id": 1,
                "at": "now",
                "event_id": 2,
                "index": 1,
                "summary": "Read and remembered one thing.",
                "stop_reason": "max_steps",
                "actions": [{"type": "read_file", "path": "README.md"}],
                "skipped_actions": [{"type": "write_file", "path": "README.md"}],
                "effects": [{"type": "message", "id": 3, "message_type": "info", "text": "Read."}],
                "counts": {"actions": 1, "messages": 1},
            }
        )

        brief = build_brief(state)
        data = build_brief_data(state)

        self.assertIn("Recent steps", brief)
        self.assertIn("stop=max_steps", brief)
        self.assertIn("skipped=1", brief)
        self.assertIn("effects=1", brief)
        self.assertEqual(data["recent_steps"][0]["summary"], "Read and remembered one thing.")

    def test_brief_surfaces_project_snapshot(self):
        state = default_state()
        state["memory"]["deep"]["project_snapshot"] = {
            "updated_at": "now",
            "project_types": ["python"],
            "package": {"name": "mew"},
            "roots": [{"path": "/repo"}],
            "files": [{"path": "/repo/README.md"}],
        }

        brief = build_brief(state)
        data = build_brief_data(state)

        self.assertIn("project_snapshot: types=python package=mew roots=1 files=1", brief)
        self.assertEqual(data["memory"]["project_snapshot"]["package_name"], "mew")

    def test_brief_shows_latest_unread_messages_first(self):
        state = default_state()
        for index in range(7):
            add_outbox_message(state, "info", f"message {index + 1}")

        brief = build_brief(state, limit=3)
        data = build_brief_data(state, limit=3)

        self.assertIn("showing latest 3; 4 older unread omitted", brief)
        self.assertIn("#7 [info] message 7", brief)
        self.assertNotIn("#1 [info] message 1", brief)
        self.assertEqual([message["id"] for message in data["unread_outbox"]], [7, 6, 5])
        self.assertEqual(data["unread_outbox_count"], 7)

    def test_brief_and_focus_show_routine_unread_cleanup_hint(self):
        state = default_state()
        add_outbox_message(state, "info", "Agent run #1 completed.", agent_run_id=1)
        add_outbox_message(state, "warning", "Needs attention.")

        brief = build_brief(state, limit=3)
        data = build_brief_data(state, limit=3)
        focus = format_focus(build_focus_data(state, limit=3))

        self.assertIn("routine info: 1; clear with `./mew ack --routine`", brief)
        self.assertEqual(data["routine_unread_info_count"], 1)
        self.assertIn("Routine info: 1 clear with `./mew ack --routine`", focus)

    def test_focus_surfaces_recent_metrics_friction(self):
        state = default_state()
        add_task(state, task_id=7, title="Improve focus", kind="coding")
        state["work_sessions"].append(
            {
                "id": 9,
                "task_id": 7,
                "status": "closed",
                "created_at": "2026-04-18T23:59:15Z",
                "updated_at": "2026-04-19T00:01:00Z",
                "notes": [{"created_at": "2026-04-19T00:00:12Z", "text": "Recovered manually after rollback."}],
                "model_turns": [
                    {
                        "id": 1,
                        "status": "completed",
                        "tool_call_id": 1,
                        "started_at": "2026-04-18T23:59:15Z",
                        "finished_at": "2026-04-18T23:59:16Z",
                        "summary": "Compare the focus surface before editing.",
                    },
                    {
                        "id": 2,
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:45Z",
                        "finished_at": "2026-04-19T00:00:46Z",
                    },
                ],
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "edit_file",
                        "status": "completed",
                        "approval_status": "rejected",
                        "rejected_at": "2026-04-19T00:00:50Z",
                        "started_at": "2026-04-19T00:00:03Z",
                        "finished_at": "2026-04-19T00:00:04Z",
                        "parameters": {
                            "path": "tests/test_brief.py",
                            "summary": "Speculative focus edit.",
                            "reason": "Add paired test first.",
                        },
                        "result": {"dry_run": True, "changed": True},
                    },
                    {
                        "id": 2,
                        "tool": "edit_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:10Z",
                        "finished_at": "2026-04-19T00:00:11Z",
                        "parameters": {"path": "src/mew/brief.py"},
                        "result": {
                            "dry_run": False,
                            "verification_exit_code": 1,
                            "rolled_back": True,
                            "verification": {
                                "command": "uv run pytest -q tests/test_brief.py",
                                "stderr": "FAILED tests/test_brief.py::BriefTests::test_focus",
                            },
                        },
                    },
                ],
            }
        )

        with patch(
            "mew.brief.coding_self_improve_focus_from_friction",
            return_value="Advance M5 audited self-improvement loop",
        ):
            data = build_focus_data(state, limit=3, kind="coding")
        focus = format_focus(data)

        self.assertEqual(data["recent_friction"]["rates"]["approval_rejection"], 1.0)
        self.assertEqual(data["recent_friction"]["active_blocker_count"], 0)
        self.assertIn("Recent friction (historical; no active blockers)", focus)
        self.assertIn("approval_rejection=1.0", focus)
        self.assertIn("verification_failure=1.0", focus)
        self.assertIn("first_tool_start_p95=", focus)
        self.assertIn("model_resume_p95=", focus)
        self.assertIn("perceived_idle_ratio=", focus)
        self.assertIn("high_idle_sessions=", focus)
        self.assertIn("high idle session#9 task=#7 idle_ratio=", focus)
        self.assertIn("rejected edit_file#1 task=#7 path=tests/test_brief.py: Add paired test first.", focus)
        self.assertIn("failed edit_file#2 task=#7 path=src/mew/brief.py exit=1: note: Recovered manually after rollback.", focus)
        self.assertIn("approval wait edit_file#1 task=#7 approval=rejected 41.0s path=tests/test_brief.py", focus)
        self.assertIn("first tool edit_file#1 task=#7 48.0s path=tests/test_brief.py first_turn=#1", focus)
        self.assertIn("Compare the focus surface before editing.", focus)
        self.assertIn("model resume edit_file#2 task=#7", focus)
        self.assertIn("next_turn=#2", focus)

    def test_coding_next_move_targets_recent_metrics_friction_when_idle(self):
        state = default_state()
        add_task(state, task_id=7, title="Improve focus", status="done", kind="coding")
        state["work_sessions"].append(
            {
                "id": 9,
                "task_id": 7,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:00:20Z",
                "model_turns": [
                    {
                        "id": 1,
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:01Z",
                        "finished_at": "2026-04-19T00:00:02Z",
                    }
                ],
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "edit_file",
                        "status": "completed",
                        "approval_status": "rejected",
                        "started_at": "2026-04-19T00:00:03Z",
                        "finished_at": "2026-04-19T00:00:04Z",
                        "parameters": {"path": "tests/test_brief.py", "reason": "Needs paired source."},
                        "result": {"dry_run": True, "changed": True},
                    },
                    {
                        "id": 2,
                        "tool": "edit_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:05Z",
                        "finished_at": "2026-04-19T00:00:06Z",
                        "parameters": {"path": "src/mew/brief.py"},
                        "result": {
                            "dry_run": False,
                            "verification_exit_code": 1,
                            "rolled_back": True,
                            "verification": {"command": "uv run pytest -q tests/test_brief.py"},
                        },
                    },
                ],
            }
        )

        with patch("mew.brief.active_roadmap_self_improve_focus", return_value=""):
            data = build_focus_data(state, kind="coding")

        self.assertIn(
            "Reproduce or retire historical M2 approval/verification friction from recent coding metrics",
            data["next_move"],
        )

        with patch(
            "mew.brief.active_roadmap_self_improve_focus",
            return_value="Prove M3 persistent advantage in resident reentry",
        ):
            data = build_focus_data(state, kind="coding")

        self.assertIn("Prove M3 persistent advantage in resident reentry", data["next_move"])

    def test_focus_surfaces_active_work_session_reentry(self):
        state = default_state()
        add_task(state, task_id=7, title="Implement cockpit polish")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Implement cockpit polish",
                "goal": "Make reentry obvious.",
                "created_at": "then",
                "updated_at": "now",
                "tool_calls": [],
                "model_turns": [
                    {
                        "id": 1,
                        "status": "completed",
                        "decision_plan": {
                            "working_memory": {
                                "hypothesis": "Cockpit polish needs one readable reentry cue.",
                                "next_step": "Surface memory in focus.",
                            }
                        },
                        "action_plan": {},
                        "action": {"type": "finish", "reason": "focus next"},
                        "summary": "focus next",
                    }
                ],
            }
        )

        data = build_focus_data(state, limit=3)
        focus = format_focus(data)

        self.assertEqual(data["active_work_sessions"][0]["id"], 3)
        self.assertEqual(data["active_work_sessions"][0]["phase"], "idle")
        self.assertEqual(
            data["active_work_sessions"][0]["working_memory"]["hypothesis"],
            "Cockpit polish needs one readable reentry cue.",
        )
        self.assertEqual(
            data["next_move"],
            "enter coding cockpit for active work session #3 task #7 with `./mew code 7`",
        )
        self.assertIn("Active work sessions", focus)
        self.assertIn("#3 task=#7 phase=idle Implement cockpit polish", focus)
        self.assertIn("memory: Cockpit polish needs one readable reentry cue.", focus)
        self.assertIn("memory_next: Surface memory in focus.", focus)
        self.assertIn("resume: ./mew work 7 --session --resume", focus)
        self.assertIn("continue: ./mew work 7 --live --max-steps 1", focus)
        self.assertIn("follow: ./mew work 7 --follow --max-steps 10", focus)

    def test_next_move_keeps_usable_active_work_continuity_on_cockpit(self):
        state = default_state()
        add_task(state, task_id=7, title="Usable continuity", kind="coding")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Usable continuity",
                "goal": "Make reentry obvious.",
                "created_at": "then",
                "updated_at": "now",
                "tool_calls": [],
                "model_turns": [],
            }
        )

        data = build_focus_data(state, limit=3, kind="coding")
        focus = format_focus(data)

        self.assertEqual(data["active_work_sessions"][0]["continuity"]["status"], "usable")
        self.assertEqual(
            data["next_move"],
            "enter coding cockpit for active work session #3 task #7 with `./mew code 7`",
        )
        self.assertIn("continuity_next: refresh working memory", focus)

    def test_next_move_repairs_broken_active_work_continuity_with_live_step(self):
        state = default_state()
        add_task(state, task_id=7, title="Recover continuity", kind="coding")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Recover continuity",
                "goal": "Make reentry obvious.",
                "created_at": "then",
                "updated_at": "now",
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "edit_file",
                        "status": "completed",
                        "parameters": {"path": "README.md"},
                        "result": {"dry_run": True, "changed": True, "path": "README.md"},
                    }
                ],
                "model_turns": [],
            }
        )

        data = build_focus_data(state, limit=3, kind="coding")

        self.assertEqual(data["active_work_sessions"][0]["continuity"]["status"], "broken")
        self.assertIn("repair continuity for active work session #3:", data["next_move"])
        self.assertIn("via `./mew work 7 --live --max-steps 1`", data["next_move"])

    def test_focus_surfaces_active_work_session_unresolved_risk(self):
        state = default_state()
        add_task(state, task_id=7, title="Recover verifier", kind="coding")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Recover verifier",
                "created_at": "then",
                "updated_at": "now",
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "run_tests",
                        "status": "failed",
                        "result": {"exit_code": 1},
                        "error": "old verifier was recovered",
                        "recovery_status": "superseded",
                        "recovered_by_tool_call_id": 2,
                    },
                    {
                        "id": 3,
                        "tool": "run_tests",
                        "status": "failed",
                        "result": {"exit_code": 1},
                        "error": "retry failed after interrupted verifier recovery",
                        "recovery_status": "retry_failed",
                        "recovered_by_tool_call_id": 4,
                    },
                    {
                        "id": 5,
                        "tool": "run_tests",
                        "status": "failed",
                        "result": {"exit_code": 1},
                        "error": "newer recovered failure one",
                        "recovery_status": "superseded",
                        "recovered_by_tool_call_id": 8,
                    },
                    {
                        "id": 6,
                        "tool": "run_tests",
                        "status": "failed",
                        "result": {"exit_code": 1},
                        "error": "newer recovered failure two",
                        "recovery_status": "superseded",
                        "recovered_by_tool_call_id": 9,
                    },
                    {
                        "id": 7,
                        "tool": "run_tests",
                        "status": "failed",
                        "result": {"exit_code": 1},
                        "error": "newer recovered failure three",
                        "recovery_status": "superseded",
                        "recovered_by_tool_call_id": 10,
                    },
                ],
                "model_turns": [],
            }
        )

        data = build_focus_data(state, limit=3, kind="coding")
        focus = format_focus(data)

        self.assertEqual(
            data["active_work_sessions"][0]["risk"],
            "run_tests#3 failed exit=1: retry failed after interrupted verifier recovery",
        )
        self.assertIn("risk: run_tests#3 failed exit=1: retry failed after interrupted verifier recovery", focus)
        self.assertNotIn("old verifier was recovered", focus)
        self.assertNotIn("newer recovered failure", focus)

    def test_focus_surfaces_latest_failed_model_turn_for_active_work_session(self):
        state = default_state()
        add_task(state, task_id=7, title="Recover timed-out planner", kind="coding")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Recover timed-out planner",
                "created_at": "then",
                "updated_at": "now",
                "tool_calls": [],
                "model_turns": [
                    {
                        "id": 12,
                        "status": "failed",
                        "error": "request timed out",
                        "model_metrics": {
                            "think": {
                                "prompt_chars": 63842,
                                "timeout_seconds": 45.0,
                            },
                            "write_ready_fast_path": True,
                            "write_ready_fast_path_reason": "paired_cached_windows_edit_ready",
                        },
                    }
                ],
            }
        )

        data = build_focus_data(state, limit=3, kind="coding")
        focus = format_focus(data)

        latest_failure = data["active_work_sessions"][0]["latest_model_failure"]
        self.assertEqual(latest_failure["model_turn_id"], 12)
        self.assertEqual(latest_failure["status"], "failed")
        self.assertEqual(latest_failure["summary"], "request timed out")
        self.assertEqual(latest_failure["prompt_chars"], 63842)
        self.assertEqual(latest_failure["timeout_seconds"], 45.0)
        self.assertTrue(latest_failure["write_ready_fast_path"])
        self.assertEqual(
            latest_failure["write_ready_fast_path_reason"],
            "paired_cached_windows_edit_ready",
        )
        self.assertIn("latest_model_failure: turn=#12 status=failed request timed out", focus)
        self.assertIn(
            "latest_model_failure_metrics: prompt_chars=63842 timeout_seconds=45.0 "
            "write_ready_fast_path=True write_ready_fast_path_reason=paired_cached_windows_edit_ready",
            focus,
        )

    def test_focus_surfaces_stop_request_for_paused_active_work_session(self):
        state = default_state()
        add_task(state, task_id=7, title="Paused debug target", kind="coding")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Paused debug target",
                "created_at": "then",
                "updated_at": "2026-04-21T15:25:14Z",
                "stop_requested_at": "2026-04-21T15:00:00Z",
                "stop_reason": "paused debug target",
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "read_file",
                        "status": "completed",
                        "finished_at": "2026-04-21T13:25:16Z",
                    }
                ],
                "model_turns": [],
            }
        )

        with patch("mew.brief.now_iso", return_value="2026-04-21T15:25:29Z"):
            data = build_focus_data(state, limit=3, kind="coding")
            focus = format_focus(data)

        self.assertIn("stop_request: paused debug target", focus)
        self.assertIn("Next: leave paused work session #3 task #7 paused", focus)
        self.assertIn("last_active: 2026-04-21T13:25:16Z (2.0h ago)", focus)

    def test_focus_surfaces_active_work_session_age(self):
        state = default_state()
        add_task(state, task_id=7, title="Resume after a day", kind="coding")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Resume after a day",
                "goal": "Make old work easy to reenter.",
                "created_at": "2026-04-16T08:00:00Z",
                "updated_at": "2026-04-16T12:00:00Z",
                "tool_calls": [],
                "model_turns": [],
            }
        )

        with patch("mew.brief.now_iso", return_value="2026-04-18T00:00:00Z"):
            data = build_focus_data(state, limit=3, kind="coding")
            focus = format_focus(data)

        session = data["active_work_sessions"][0]
        self.assertEqual(session["updated_at"], "2026-04-16T12:00:00Z")
        self.assertEqual(session["inactive_hours"], 36.0)
        self.assertEqual(session["inactive_for"], "1.5d")
        self.assertIn("last_active: 2026-04-16T12:00:00Z (1.5d ago)", focus)

    def test_focus_reentry_commands_reuse_work_session_defaults(self):
        state = default_state()
        add_task(state, task_id=7, title="Use saved cockpit defaults")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Use saved cockpit defaults",
                "goal": "Make focus reentry copy-paste ready.",
                "created_at": "then",
                "updated_at": "now",
                "default_options": {
                    "auth": "auth.json",
                    "model_backend": "codex",
                    "allow_read": ["."],
                    "allow_write": ["."],
                    "allow_verify": True,
                    "verify_command": "uv run pytest -q",
                    "act_mode": "deterministic",
                    "compact_live": True,
                },
                "tool_calls": [],
                "model_turns": [],
            }
        )

        data = build_focus_data(state, limit=3)
        session = data["active_work_sessions"][0]
        focus = format_focus(data)

        expected_continue = (
            "./mew work 7 --live --auth auth.json --model-backend codex --allow-read . "
            "--allow-write . --allow-verify --verify-command 'uv run pytest -q' "
            "--act-mode deterministic --compact-live --max-steps 1"
        )
        expected_follow = expected_continue.replace("--live", "--follow").replace("--max-steps 1", "--max-steps 10")
        expected_resume = "./mew work 7 --session --resume --allow-read ."
        self.assertEqual(session["resume_command"], expected_resume)
        self.assertEqual(session["continue_command"], expected_continue)
        self.assertEqual(session["follow_command"], expected_follow)
        self.assertIn(f"resume: {expected_resume}", focus)
        self.assertIn(f"continue: {expected_continue}", focus)
        self.assertIn(f"follow: {expected_follow}", focus)

    def test_focus_marks_stale_active_work_session_memory(self):
        state = default_state()
        add_task(state, task_id=7, title="Recheck stale memory")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Recheck stale memory",
                "goal": "Avoid treating old memory_next as current.",
                "created_at": "then",
                "updated_at": "now",
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "read_file",
                        "status": "completed",
                        "parameters": {"path": "README.md"},
                        "result": {"path": "README.md", "content": "new evidence"},
                        "summary": "read README",
                    }
                ],
                "model_turns": [
                    {
                        "id": 1,
                        "status": "completed",
                        "tool_call_id": 1,
                        "decision_plan": {
                            "working_memory": {
                                "hypothesis": "README still needs inspection.",
                                "next_step": "Read README.md next.",
                            }
                        },
                        "action_plan": {},
                        "action": {"type": "read_file", "path": "README.md"},
                        "summary": "read README",
                    }
                ],
            }
        )

        data = build_focus_data(state, limit=3)
        focus = format_focus(data)

        memory = data["active_work_sessions"][0]["working_memory"]
        self.assertEqual(memory["stale_after_tool_call_id"], 1)
        self.assertIn("memory: README still needs inspection. (stale)", focus)
        self.assertIn(
            "memory_stale: tool #1 read_file ran after this memory; refresh before relying on next step",
            focus,
        )
        self.assertNotIn("memory_next: Read README.md next.", focus)

    def test_focus_ignores_stale_blocked_active_work_session(self):
        state = default_state()
        add_task(state, task_id=7, title="Waiting on reviewer", status="blocked", kind="coding")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Waiting on reviewer",
                "goal": "Resume only when reviewer unblocks it.",
                "created_at": "2026-04-16T08:00:00Z",
                "updated_at": "2026-04-16T12:00:00Z",
                "tool_calls": [],
                "model_turns": [],
            }
        )

        with patch(
            "mew.brief.coding_self_improve_focus_from_friction",
            return_value="Advance M5 audited self-improvement loop",
        ), patch("mew.brief.now_iso", return_value="2026-04-18T00:00:00Z"):
            data = build_focus_data(state, limit=3, kind="coding")

        self.assertEqual(data["active_work_sessions"], [])
        self.assertEqual(
            data["next_move"],
            "start a native self-improvement session with `./mew self-improve --start-session --focus 'Advance M5 audited self-improvement loop'`",
        )

    def test_focus_ignores_active_work_session_for_done_task(self):
        state = default_state()
        add_task(state, task_id=7, title="Implemented already", status="done", kind="coding")
        state["work_sessions"].append(
            {
                "id": 3,
                "task_id": 7,
                "status": "active",
                "title": "Implemented already",
                "goal": "Stale session.",
                "created_at": "then",
                "updated_at": "now",
                "tool_calls": [],
                "model_turns": [],
            }
        )

        with patch(
            "mew.brief.coding_self_improve_focus_from_friction",
            return_value="Advance M5 audited self-improvement loop",
        ):
            data = build_focus_data(state, limit=3, kind="coding")

        self.assertEqual(data["active_work_sessions"], [])
        self.assertEqual(
            data["next_move"],
            "start a native self-improvement session with `./mew self-improve --start-session --focus 'Advance M5 audited self-improvement loop'`",
        )

    def test_focus_kind_filter_shows_matching_tasks_and_questions(self):
        state = default_state()
        add_task(state, task_id=1, title="Research grants", kind="research")
        add_task(state, task_id=2, title="Improve cockpit", kind="coding")
        add_question(state, "Which area?", related_task_id=1)
        add_question(state, "Which file?", related_task_id=2)

        data = build_focus_data(state, limit=3, kind="coding")
        focus = format_focus(data)

        self.assertEqual(data["kind"], "coding")
        self.assertEqual(data["tasks"][0]["id"], 2)
        self.assertEqual(data["open_questions"][0]["related_task_id"], 2)
        self.assertIn("Mew focus (coding)", focus)
        self.assertIn("Which file?", focus)
        self.assertNotIn("Which area?", focus)

    def test_focus_shows_question_waiting_age(self):
        state = default_state()
        add_task(state, task_id=1, title="Answer old prompt", kind="coding")
        add_question(state, "Still relevant?", related_task_id=1)
        state["questions"][0]["created_at"] = "2026-04-16T00:00:00Z"
        state["questions"][0]["updated_at"] = None

        with patch("mew.brief.now_iso", return_value="2026-04-18T00:00:00Z"):
            data = build_focus_data(state, limit=3)
            focus = format_focus(data)
            brief = build_brief(state, limit=3)

        self.assertEqual(data["open_questions"][0]["waiting_hours"], 48.0)
        self.assertEqual(data["open_questions"][0]["waiting_for"], "2.0d")
        self.assertIn("- #1 task=#1 (waiting=2.0d): Still relevant?", focus)
        self.assertIn("- #1 task=#1 (waiting=2.0d): Still relevant?", brief)

    def test_next_move_surfaces_latest_failed_verification(self):
        state = default_state()
        state["verification_runs"].append(
            {
                "id": 2,
                "command": "python -m unittest",
                "exit_code": 1,
                "finished_at": "done",
            }
        )

        self.assertEqual(next_move(state), "inspect verification run #2 with `./mew verification`")

    def test_next_move_kind_filter_ignores_unrelated_failed_verification(self):
        state = default_state()
        add_task(state, task_id=1, title="Research grants", kind="research")
        add_task(state, task_id=2, title="Improve cockpit", kind="coding")
        state["verification_runs"].append(
            {
                "id": 7,
                "task_id": 1,
                "command": "python -m unittest",
                "exit_code": 1,
                "finished_at": "done",
            }
        )

        self.assertEqual(next_move(state, kind="coding"), "enter coding cockpit for task #2 with `./mew code 2`")


if __name__ == "__main__":
    unittest.main()
