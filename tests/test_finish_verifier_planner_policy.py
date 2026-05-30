from mew.implement_lane.finish_verifier_planner_policy import (
    finish_verifier_planner_policy,
)


def test_finish_verifier_planner_policy_defaults_enabled() -> None:
    policy = finish_verifier_planner_policy({})

    assert policy.enabled is True
    assert policy.selection_source == "default_enabled"


def test_finish_verifier_planner_policy_accepts_canonical_enabled() -> None:
    policy = finish_verifier_planner_policy(
        {"finish_verifier_planner_enabled": True}
    )

    assert policy.enabled is True
    assert policy.selection_source == "explicit_enabled"


def test_finish_verifier_planner_policy_accepts_canonical_disabled() -> None:
    policy = finish_verifier_planner_policy(
        {"finish_verifier_planner_enabled": False}
    )

    assert policy.enabled is False
    assert policy.selection_source == "explicit_disabled"


def test_finish_verifier_planner_policy_canonical_key_wins_over_aliases() -> None:
    policy = finish_verifier_planner_policy(
        {
            "finish_verifier_planner_enabled": False,
            "finish_verifier_planner": True,
            "experimental_finish_verifier_planner": True,
        }
    )

    assert policy.enabled is False
    assert policy.selection_source == "explicit_disabled"


def test_finish_verifier_planner_policy_accepts_compatibility_alias() -> None:
    policy = finish_verifier_planner_policy({"finish_verifier_planner": True})

    assert policy.enabled is True
    assert policy.selection_source == "explicit_enabled_alias"


def test_finish_verifier_planner_policy_accepts_compatibility_opt_out() -> None:
    policy = finish_verifier_planner_policy({"finish_verifier_planner": False})

    assert policy.enabled is False
    assert policy.selection_source == "explicit_disabled_legacy_alias"


def test_finish_verifier_planner_policy_accepts_experimental_alias() -> None:
    policy = finish_verifier_planner_policy(
        {"experimental_finish_verifier_planner": True}
    )

    assert policy.enabled is True
    assert policy.selection_source == "explicit_enabled_legacy_alias"


def test_finish_verifier_planner_policy_accepts_experimental_opt_out() -> None:
    policy = finish_verifier_planner_policy(
        {"experimental_finish_verifier_planner": False}
    )

    assert policy.enabled is False
    assert policy.selection_source == "explicit_disabled_legacy_alias"
