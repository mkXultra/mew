from check_common import require, require_hash, write_reward


PROTECTED_HASH = "67da28cda9f9038eafbcaeb3882e2b30c4da418398214fe6d33a80638b2b65da"


def main() -> None:
    require_hash("generated/expected_totals.json", PROTECTED_HASH)
    try:
        from golden_convention.price_rules import render_total
    except Exception as exc:
        require(False, f"could not import price rules: {exc}")

    cases = {
        (0, "standard"): "$0.00",
        (1299, "standard"): "$12.99",
        (99999, "compact"): "$999.99",
        (100000, "compact"): "$1k",
        (125000, "compact"): "$1.2k",
        (2500000, "compact"): "$25k",
    }
    for args, expected in cases.items():
        actual = render_total(*args)
        require(actual == expected, f"render_total{args!r} returned {actual!r}, expected {expected!r}")
    write_reward({"reward": 1.0, "correctness": 1.0, "protected_files": 1.0})
    print("seed-convention verifier passed")


if __name__ == "__main__":
    main()
