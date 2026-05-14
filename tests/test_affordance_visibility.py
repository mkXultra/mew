import pytest

from mew.implement_lane.affordance_visibility import (
    CANONICAL_FORBIDDEN_PROVIDER_VISIBLE_FIELDS,
    DEFAULT_AFFORDANCE_VISIBILITY_CAPS,
    caps_fixture_matches_default,
    fields_from_forbidden_violations,
    load_affordance_visibility_caps_fixture,
    scan_forbidden_provider_visible,
)


@pytest.mark.parametrize("field", CANONICAL_FORBIDDEN_PROVIDER_VISIBLE_FIELDS)
@pytest.mark.parametrize("surface", ("prompt_sections", "task_contract", "compact_digest", "tool_output_card"))
def test_canonical_forbidden_provider_visible_field_fixtures_fail(field: str, surface: str) -> None:
    payload = {
        "prompt_sections": {},
        "task_contract": {},
        "compact_digest": {},
        "tool_output_card": {},
    }
    payload[surface] = {field: "leak"}

    violations = scan_forbidden_provider_visible(payload, surface=surface)

    assert field in fields_from_forbidden_violations(violations)


def test_generic_forbidden_words_are_not_rejected_as_plain_prose() -> None:
    payload = {
        "instructions": (
            "Use proof only as an English noun here; this sentence is not a "
            "rendered proof state object, todo object, or frontier object."
        )
    }

    violations = scan_forbidden_provider_visible(payload)

    assert fields_from_forbidden_violations(violations) == []


@pytest.mark.parametrize(
    ("text", "field"),
    (
        ("todo=patch src/app.py", "todo"),
        ("<frontier>incomplete</frontier>", "frontier"),
        ("## WorkFrame\nrequired_next: patch", "WorkFrame"),
        ('Return JSON with "tool_calls": []', "tool_calls"),
    ),
)
def test_generic_forbidden_words_fail_as_rendered_state_markers(text: str, field: str) -> None:
    violations = scan_forbidden_provider_visible({"instructions": text})

    assert field in fields_from_forbidden_violations(violations)


def test_proof_is_allowed_as_task_domain_text_but_not_as_structural_key() -> None:
    prose = "Complete the proof in plus_comm.v and compile the proof using coqc."

    assert fields_from_forbidden_violations(scan_forbidden_provider_visible({"instructions": prose})) == []
    assert "proof" in fields_from_forbidden_violations(
        scan_forbidden_provider_visible({"proof": {"status": "model-authored"}})
    )


def test_affordance_visibility_caps_fixture_matches_default_contract() -> None:
    fixture = load_affordance_visibility_caps_fixture()

    assert caps_fixture_matches_default(fixture)
    assert fixture == DEFAULT_AFFORDANCE_VISIBILITY_CAPS
