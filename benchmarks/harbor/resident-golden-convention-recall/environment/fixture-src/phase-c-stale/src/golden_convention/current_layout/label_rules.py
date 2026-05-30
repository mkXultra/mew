def delivery_label(channel: str, code: str) -> str:
    normalized = code.strip().upper()
    if channel == "home":
        return f"HOME-{normalized}: doorstep delivery"
    if channel == "store":
        return f"STORE-{normalized}: customer desk"
    raise ValueError(f"unsupported delivery channel: {channel}")
