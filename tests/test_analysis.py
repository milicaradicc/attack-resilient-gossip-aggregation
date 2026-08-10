from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from analysis.loader import filter_rows, group_stats, group_values

ROWS = [
    {"overlay": "random", "seed": 1, "err": 1.0},
    {"overlay": "random", "seed": 2, "err": 3.0},
    {"overlay": "sybil", "seed": 1, "err": 0.1},
    {"overlay": "sybil", "seed": 2, "err": 0.3},
]


def test_group_stats_mean_std():
    stats = group_stats(ROWS, ("overlay",), "err")
    assert stats[("random",)][0] == 2.0
    assert stats[("sybil",)][0] == 0.2


def test_filter_rows():
    assert len(filter_rows(ROWS, overlay="random")) == 2


def test_group_values():
    g = group_values(ROWS, ("overlay",), "err")
    assert sorted(g[("random",)]) == [1.0, 3.0]


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — testovi analize prolaze")
