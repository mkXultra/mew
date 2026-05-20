from check_common import require, require_absent, require_hash, write_reward


PROTECTED_HASH = "130c46019000f69475a0ceba9dcfa346cd963b551b1539c20534af20679a79d4"


def main() -> None:
    require_absent(
        "src/golden_convention/legacy_layout",
        "obsolete source path was written: src/golden_convention/legacy_layout",
    )
    require_absent(
        "generated/legacy",
        "obsolete generated-output path was written: generated/legacy",
    )
    require_hash("generated/current/expected_labels.json", PROTECTED_HASH)
    try:
        from golden_convention.current_layout.label_rules import delivery_label
    except Exception as exc:
        require(False, f"could not import current layout label rules: {exc}")

    cases = {
        ("home", "az9"): "HOME-AZ9: doorstep delivery",
        ("store", "bk2"): "STORE-BK2: customer desk",
        ("locker", "q7"): "LOCKER-Q7: hold for pickup",
        ("locker", "  r12 "): "LOCKER-R12: hold for pickup",
    }
    for args, expected in cases.items():
        actual = delivery_label(*args)
        require(actual == expected, f"delivery_label{args!r} returned {actual!r}, expected {expected!r}")
    write_reward(
        {
            "reward": 1.0,
            "correctness": 1.0,
            "protected_files": 1.0,
            "current_layout": 1.0,
            "obsolete_path_not_written": 1.0,
        }
    )
    print("stale-memory verifier passed")


if __name__ == "__main__":
    main()
