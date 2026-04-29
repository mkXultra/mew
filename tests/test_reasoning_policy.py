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

    def test_selects_high_for_complex_implementation_terms(self):
        policy = select_work_reasoning_policy(
            {
                "title": "Build MIPS interpreter",
                "kind": "coding",
                "description": "Implement a MIPS interpreter that loads an ELF and executes the program.",
            },
            capabilities={"allowed_write_roots": ["."], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "high")
        self.assertEqual(policy["work_type"], "complex_implementation")
        self.assertIn("interpreter", policy["matched_terms"])

    def test_selects_high_for_hard_source_toolchain_task_without_interpreter_word(self):
        policy = select_work_reasoning_policy(
            {
                "title": "Build doomgeneric_mips",
                "kind": "coding",
                "description": (
                    "I provided source code for Doom and a special doomgeneric_img.c. "
                    "Build the MIPS ELF so the provided vm.js can run it and write /tmp/frame.bmp."
                ),
            },
            capabilities={"allowed_write_roots": ["."], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "high")
        self.assertEqual(policy["work_type"], "complex_implementation")
        self.assertIn("mips", policy["matched_terms"])
        self.assertIn("elf", policy["matched_terms"])
        self.assertIn("provided source", policy["matched_terms"])

    def test_selects_high_for_checkpoint_tokenizer_inference_implementation(self):
        policy = select_work_reasoning_policy(
            {
                "title": "Implement compact GPT sampler",
                "kind": "coding",
                "description": (
                    "Write a dependency-free C file that reads gpt2-124M.ckpt "
                    "and vocab.bpe, then performs model inference to continue "
                    "the output for the next 20 tokens."
                ),
            },
            capabilities={"allowed_write_roots": ["."], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "high")
        self.assertEqual(policy["work_type"], "complex_implementation")
        self.assertIn(".ckpt", policy["matched_terms"])
        self.assertIn("vocab.bpe", policy["matched_terms"])
        self.assertIn("model inference", policy["matched_terms"])

    def test_selects_high_for_long_implementation_spec(self):
        policy = select_work_reasoning_policy(
            {
                "title": "Implement benchmark task",
                "kind": "coding",
                "description": "Implement the requested program.\n" + ("Acceptance detail. " * 90),
            },
            capabilities={"allowed_write_roots": ["."], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "high")
        self.assertEqual(policy["work_type"], "complex_implementation")
        self.assertIn("task text is long enough", policy["reason"])

    def test_complex_terms_do_not_raise_read_only_exploration(self):
        policy = select_work_reasoning_policy(
            {"title": "Inspect interpreter architecture", "kind": "coding"},
            capabilities={"allowed_write_roots": [], "allow_verify": False},
            env={},
        )

        self.assertEqual(policy["effort"], "low")
        self.assertEqual(policy["work_type"], "exploration")

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

    def test_high_risk_takes_precedence_over_complex_implementation(self):
        policy = select_work_reasoning_policy(
            {"title": "Update security policy for interpreter runtime", "kind": "coding"},
            capabilities={"allowed_write_roots": ["."], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "high")
        self.assertEqual(policy["work_type"], "high_risk")
        self.assertIn("policy", policy["matched_terms"])
        self.assertIn("security", policy["matched_terms"])

    def test_high_risk_title_is_not_suppressed_by_out_of_scope_guidance(self):
        policy = select_work_reasoning_policy(
            {"title": "Update roadmap recovery gate", "kind": "coding"},
            capabilities={"allowed_write_roots": ["src/mew/timeutil.py", "tests/test_timeutil.py"], "allow_verify": True},
            env={},
            guidance="Do not edit ROADMAP_STATUS.md.",
        )

        self.assertEqual(policy["effort"], "high")
        self.assertEqual(policy["work_type"], "high_risk")
        self.assertIn("roadmap", policy["matched_terms"])
        self.assertIn("recovery", policy["matched_terms"])

    def test_bounded_task_not_high_risk_due_to_reasoning_policy_phrase(self):
        for title in (
            "reasoning-policy",
            "reasoning_policy",
            "reasoning policy",
        ):
            policy = select_work_reasoning_policy(
                {"title": title, "kind": "coding"},
                capabilities={
                    "allowed_write_roots": ["src/mew/timeutil.py", "tests/test_timeutil.py"],
                    "allow_verify": True,
                },
                env={},
            )

            self.assertEqual(policy["effort"], "medium")
            self.assertEqual(policy["work_type"], "small_implementation")

    def test_approval_policy_flow_remains_high_risk(self):
        policy = select_work_reasoning_policy(
            {"title": "Update approval policy flow", "kind": "coding"},
            capabilities={"allowed_write_roots": ["."], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "high")
        self.assertEqual(policy["work_type"], "high_risk")
        self.assertIn("policy", policy["matched_terms"])

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

    def test_current_notes_after_historical_note_still_drive_high_risk(self):
        policy = select_work_reasoning_policy(
            {
                "title": "Improve mew itself",
                "kind": "coding",
                "notes": (
                    "Dogfood note: previous M6 daemon proof and recovery work used high effort.\n"
                    "Update approval flow before resuming the task."
                ),
            },
            capabilities={"allowed_write_roots": ["src/mew", "tests"], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "high")
        self.assertEqual(policy["work_type"], "high_risk")
        self.assertIn("approval", policy["matched_terms"])

    def test_bookkeeping_notes_do_not_trigger_high_risk_when_bounded(self):
        policy = select_work_reasoning_policy(
            {
                "title": "Reverse symbol-index query",
                "kind": "coding",
                "notes": "Keep ROADMAP_STATUS.md and proof-artifacts dirty while implementing.",
            },
            capabilities={
                "allowed_write_roots": ["src/mew/timeutil.py", "tests/test_timeutil.py"],
                "allow_verify": True,
            },
            guidance="Do not edit ROADMAP_STATUS.md.",
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

    def test_scope_fence_negated_governance_stays_medium(self):
        policy = select_work_reasoning_policy(
            {
                "title": "Reverse symbol-index query",
                "kind": "coding",
                "notes": (
                    "Scope fence: src/mew/cli.py, src/mew/commands.py only. "
                    "Reviewer-owned governance files out of scope."
                ),
            },
            capabilities={"allowed_write_roots": ["src/mew", "tests"], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "medium")
        self.assertEqual(policy["work_type"], "small_implementation")

    def test_non_negated_governance_line_still_stays_high(self):
        policy = select_work_reasoning_policy(
            {
                "title": "Reverse symbol-index query",
                "kind": "coding",
                "notes": (
                    "Scope fence: docs are out of scope.\n"
                    "Update governance approval flow before resuming the task."
                ),
            },
            capabilities={"allowed_write_roots": ["src/mew", "tests"], "allow_verify": True},
            env={},
        )

        self.assertEqual(policy["effort"], "high")
        self.assertEqual(policy["work_type"], "high_risk")
        self.assertIn("governance", policy["matched_terms"])

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
