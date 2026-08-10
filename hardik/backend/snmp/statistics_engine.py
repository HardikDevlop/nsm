"""Counter delta and traffic statistics calculations."""

from statistics import quantiles


def counter_delta(current: float, previous: float, bits: int = 64) -> float:
    """Return a wrap-safe counter delta."""
    if current >= previous:
        return current - previous
    return (2 ** bits - previous) + current


def percentile95(values: list[float]) -> float | None:
    """Return the 95th percentile, or None for empty input."""
    if not values:
        return None
    return values[0] if len(values) < 2 else quantiles(values, n=100, method="inclusive")[94]
