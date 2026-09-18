"""Counter delta and traffic statistics calculations."""

from statistics import quantiles


def counter_delta(current: float, previous: float, bits: int = 64) -> float:
    """Return a wrap-safe counter delta."""
    if current >= previous:
        return current - previous
    return (2 ** bits - previous) + current


INTERFACE_RATE_TOLERANCE = 1.10


def interface_rate_mbps(
    current: float | None,
    previous: float | None,
    elapsed: float,
    speed_bps: float | None = None,
) -> float | None:
    """Calculate a rate only from a proven monotonic counter interval."""
    if current is None or previous is None or elapsed <= 0 or current < previous:
        return None
    rate = (float(current) - float(previous)) * 8 / elapsed / 1_000_000
    if speed_bps is not None and speed_bps > 0:
        capacity_mbps = speed_bps / 1_000_000
        if rate > capacity_mbps * INTERFACE_RATE_TOLERANCE:
            return None
    return round(rate, 3)


def percentile95(values: list[float]) -> float | None:
    """Return the 95th percentile, or None for empty input."""
    if not values:
        return None
    return values[0] if len(values) < 2 else quantiles(values, n=100, method="inclusive")[94]
