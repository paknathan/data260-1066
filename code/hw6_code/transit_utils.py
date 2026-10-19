"""Helper generated for Part 4.4 - must follow every coding rule in AGENT.md."""

DELAY_BANDS = ((0, "on_time"), (5, "minor"), (15, "moderate"), (30, "severe"))


def classify_delay(delay_minutes: int) -> str:
    """Return the delay band (on_time/minor/moderate/severe) for a delay in whole minutes."""
    if isinstance(delay_minutes, bool) or not isinstance(delay_minutes, int):
        raise ValueError(f"delay_minutes must be an int, got {type(delay_minutes).__name__}")
    if delay_minutes < 0:
        raise ValueError(f"delay_minutes must be >= 0, got {delay_minutes}")
    band = DELAY_BANDS[0][1]
    for threshold, name in DELAY_BANDS:
        if delay_minutes >= threshold:
            band = name
    return band
