from __future__ import annotations

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from attacks.scenario import AttackParams, Scenario
from experiments.config import RunSpec
from experiments.matrix import run_single

RNG = random.Random(0)


def _scenario(unresponsive_p):
    return Scenario({0, 1}, {2}, set(), AttackParams(activate_round=1, unresponsive_p=unresponsive_p))


def test_honest_always_responds():
    s = _scenario(1.0)
    assert s.responds(0, 5, RNG) is True


def test_malicious_silent_when_unresponsive():
    s = _scenario(1.0)
    assert s.responds(2, 5, RNG) is False


def test_malicious_responds_when_disabled():
    s = _scenario(0.0)
    assert s.responds(2, 5, RNG) is True


def _spec(unresponsive_p, timeout_rounds):
    return RunSpec(10, 0.3, "sybil_resistant", "mean", 1, 7, 50, 1000.0, 11, 8, 8, 0.34,
                   0.05, 20, "coordinated", 0, 0, 1.0, timeout_rounds, unresponsive_p)


def test_timeout_evicts_silent_peers():
    m = run_single(_spec(unresponsive_p=0.9, timeout_rounds=2))
    assert sum(r.timeouts for r in m.rows) > 0


def test_no_timeouts_when_all_respond():
    m = run_single(_spec(unresponsive_p=0.0, timeout_rounds=2))
    assert sum(r.timeouts for r in m.rows) == 0


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — testovi heartbeat/timeout prolaze")
