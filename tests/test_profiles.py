from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import RunSpec
from in_process.matrix import run_single


def _spec(profile, overlay="eclipse_resistant", aggregation="mean", flooding=0):
    return RunSpec(10, 0.3, overlay, aggregation, 1, 7, 20, 1000.0, 1, 8, 8, 0.34,
                   0.05, 10, profile, flooding, 0, 1.0, 0, 0.0)


def test_extreme_hurts_mean():
    assert run_single(_spec("extreme", overlay="random",
                            aggregation="mean")).rows[-1].err_rel > 1.0


def test_admission_blocks_extreme_attack():
    protected = run_single(_spec("extreme", overlay="sybil_resistant", aggregation="mean"))
    assert protected.rows[-1].err_rel < 1.0
    assert protected.rows[-1].sybil_penetration == 0.0


def test_median_robust_across_profiles():
    a = run_single(_spec("coordinated", aggregation="median")).rows[-1].err_rel
    b = run_single(_spec("extreme", aggregation="median")).rows[-1].err_rel
    assert abs(a - b) < 1e-9


def test_flooding_raises_rejections_and_overhead():
    base = run_single(_spec("coordinated", overlay="sybil_resistant", flooding=0))
    flood = run_single(_spec("coordinated", overlay="sybil_resistant", flooding=20))
    assert (sum(r.rejected for r in flood.rows)
            > sum(r.rejected for r in base.rows))
    assert sum(r.rej_invalid_pow for r in flood.rows) > 0
    assert sum(r.rej_invalid_pow for r in base.rows) == 0
    assert flood.control_overhead(10) > base.control_overhead(10)


def test_all_profiles_run():
    for p in ("coordinated", "extreme", "random", "low_biased"):
        assert run_single(_spec(p)).rows[-1].err_rel >= 0.0


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — testovi profila napada prolaze")