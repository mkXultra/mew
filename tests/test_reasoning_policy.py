import os
import unittest

from mew.reasoning_policy import (
    CODEX_REASONING_ENV,
    codex_reasoning_effort_scope,
    select_work_reasoning_policy,
)


class ReasoningPolicyTests(unittest.TestCase):
    def test_selects_low_for_read_only_exploration(self):
        policy = select_work_reasoning_policy(
            {"title": "Inspect project shape", "kind": "coding"},
            capabilities={"allowed_write_roots": [], "allow_verify": False},
            env={},
        )

        self.assertEqual(policy["effort"], "low")
        self.assertEqual(policy["work_type"], "exploration")

    def test_selects_medium_for_small_implementation(self):
        policy = select_work_reasoning_policy(
            {"title": "Add metrics output", "kind": "coding"},
            capabilities={"allowed_write_roots": ["src/mew", "tests"], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "medium")
        self.assertEqual(policy["work_type"], "small_implementation")

    def test_selects_high_for_safety_recovery_or_roadmap_work(self):
        policy = select_work_reasoning_policy(
            {"title": "Update roadmap recovery gate", "kind": "coding"},
            capabilities={"allowed_write_roots": ["."], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "high")
        self.assertEqual(policy["work_type"], "high_risk")
        self.assertIn("roadmap", policy["matched_terms"])
        self.assertIn("recovery", policy["matched_terms"])

    def test_ignores_historical_commit_context_for_small_implementation(self):
        policy = select_work_reasoning_policy(
            {
                "title": "Improve mew itself",
                "kind": "coding",
                "description": (
                    "Focus:\n"
                    "M7: add a minimal RSS signal fetcher.\n\n"
                    "Recently completed git commits. Do not repeat these topics:\n"
                    "8c12154 Support M6 daemon Docker proofs\n"
                    "0b51fae Record enhanced M6 proof gate\n"
                ),
            },
            capabilities={"allowed_write_roots": ["src/mew", "tests"], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "medium")
        self.assertEqual(policy["work_type"], "small_implementation")

    def test_ignores_historical_task_notes_for_small_implementation(self):
        policy = select_work_reasoning_policy(
            {
                "title": "Improve mew itself",
                "kind": "coding",
                "description": "Focus:\nM7: add a minimal RSS signal fetcher.",
                "notes": (
                    "Dogfood note: previous M6 daemon proof and recovery work "
                    "used high effort, but that is historical context."
                ),
            },
            capabilities={"allowed_write_roots": ["src/mew", "tests"], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "medium")
        self.assertEqual(policy["work_type"], "small_implementation")

    def test_milestone_number_alone_does_not_make_work_high_risk(self):
        policy = select_work_reasoning_policy(
            {
                "title": "Improve mew itself",
                "kind": "coding",
                "description": (
                    "Focus:\n"
                    "M6.5 clean speed dogfood: add explicit atom source kind support."
                ),
            },
            capabilities={"allowed_write_roots": ["src/mew", "tests"], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "medium")
        self.assertEqual(policy["work_type"], "small_implementation")

    def test_env_override_wins(self):
        policy = select_work_reasoning_policy(
            {"title": "Inspect project shape", "kind": "coding"},
            capabilities={},
            env={CODEX_REASONING_ENV: "xhigh"},
        )

        self.assertEqual(policy["effort"], "xhigh")
        self.assertEqual(policy["source"], "env_override")

    def test_codex_reasoning_effort_scope_restores_environment(self):
        old_value = os.environ.get(CODEX_REASONING_ENV)
        os.environ[CODEX_REASONING_ENV] = "high"
        try:
            with codex_reasoning_effort_scope("medium"):
                self.assertEqual(os.environ[CODEX_REASONING_ENV], "medium")
            self.assertEqual(os.environ[CODEX_REASONING_ENV], "high")
        finally:
            if old_value is None:
                os.environ.pop(CODEX_REASONING_ENV, None)
            else:
                os.environ[CODEX_REASONING_ENV] = old_value
