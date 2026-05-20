def render_total(cents: int, mode: str = "standard") -> str:
    if mode != "standard":
        raise ValueError(f"unsupported total render mode: {mode}")
    dollars, remainder = divmod(cents, 100)
    return f"${dollars}.{remainder:02d}"
