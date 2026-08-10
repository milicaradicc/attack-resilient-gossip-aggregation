from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aggregation import get_aggregation

EPS = 1e-9


def approx(a, b):
    return abs(a - b) <= EPS


def test_mean_basic():
    assert approx(get_aggregation("mean").aggregate(2, [4, 6]), 4.0)


def test_median_odd():
    assert approx(get_aggregation("median").aggregate(1, [2, 3]), 2.0)


def test_median_even():
    assert approx(get_aggregation("median").aggregate(1, [2, 3, 4]), 2.5)


def test_median_robust_to_outlier():
    assert approx(get_aggregation("median").aggregate(100, [100, 100, 1_000_000]), 100.0)


def test_trimmed_removes_outlier():
    assert approx(get_aggregation("trimmed_mean", alpha=0.2).aggregate(1, [2, 3, 4, 1000]), 3.0)


def test_trimmed_zero_trim_equals_mean():
    vals = [4, 6]
    trimmed = get_aggregation("trimmed_mean", alpha=0.0).aggregate(2, vals)
    plain = get_aggregation("mean").aggregate(2, vals)
    assert approx(trimmed, plain)


def test_empty_received():
    for name in ("mean", "median", "trimmed_mean"):
        assert approx(get_aggregation(name).aggregate(5.0, []), 5.0)


def test_unknown_raises():
    try:
        get_aggregation("nope")
        assert False
    except ValueError:
        pass


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — testovi agregacije prolaze")
