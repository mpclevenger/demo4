"""Rounding that every calculation shares, so a displayed number is rounded the same way everywhere."""
from decimal import Decimal, ROUND_HALF_UP

PERCENT_OF_WHOLE = 100


def r1(x):
    """One decimal place, half up (D-04): 12.25 gives 12.3."""
    return float(Decimal(str(x)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def percent(numerator, denominator):
    """The numerator out of the denominator as a percent, one decimal, half up: 24 of 27 releases gives 88.9."""
    return r1(PERCENT_OF_WHOLE * numerator / denominator)
