from __future__ import annotations

from .models import MetricOperator

_COMPARATORS = {
    MetricOperator.lt: lambda v, t: v < t,
    MetricOperator.lte: lambda v, t: v <= t,
    MetricOperator.gt: lambda v, t: v > t,
    MetricOperator.gte: lambda v, t: v >= t,
    MetricOperator.eq: lambda v, t: v == t,
}


def passes(value: float, operator: MetricOperator, threshold: float) -> bool:
    """Return True when ``value`` satisfies ``operator threshold``."""
    return _COMPARATORS[operator](value, threshold)


def higher_is_better(operator: MetricOperator) -> bool | None:
    """Infer ranking direction from an accept-rule operator.

    Returns True for gt/gte, False for lt/lte, and None for eq (no ordering).
    """
    if operator in (MetricOperator.gt, MetricOperator.gte):
        return True
    if operator in (MetricOperator.lt, MetricOperator.lte):
        return False
    return None
