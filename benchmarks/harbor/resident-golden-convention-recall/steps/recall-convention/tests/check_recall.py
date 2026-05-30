from check_common import require, require_hash, write_reward


PROTECTED_HASH = "36fc9528d3495ca5e50372dc0459532b74c23df125555a0d5ef1b3432d9473c9"


def main() -> None:
    require_hash("generated/expected_delivery.json", PROTECTED_HASH)
    try:
        from golden_convention.eta_rules import delivery_summary
    except Exception as exc:
        require(False, f"could not import ETA rules: {exc}")

    cases = {
        ("queued", 2): "Leaves warehouse in 2 business days",
        ("shipped", 4): "Arrives in 4 business days",
        ("delayed", 1): "Delayed; new estimate is 1 business days",
        ("delayed", 9): "Delayed; new estimate is 9 business days",
    }
    for args, expected in cases.items():
        actual = delivery_summary(*args)
        require(actual == expected, f"delivery_summary{args!r} returned {actual!r}, expected {expected!r}")
    write_reward({"reward": 1.0, "correctness": 1.0, "protected_files": 1.0})
    print("recall-convention verifier passed")


if __name__ == "__main__":
    main()
