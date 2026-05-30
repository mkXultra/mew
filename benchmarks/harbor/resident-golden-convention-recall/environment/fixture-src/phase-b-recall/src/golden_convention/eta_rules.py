def delivery_summary(status: str, business_days: int) -> str:
    if status == "queued":
        return f"Leaves warehouse in {business_days} business days"
    if status == "shipped":
        return f"Arrives in {business_days} business days"
    raise ValueError(f"unsupported delivery status: {status}")
