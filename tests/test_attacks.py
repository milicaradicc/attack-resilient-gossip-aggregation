from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from attacks.scenario import AttackParams, Scenario
from core.node import Node
from core.setup import RunConfig
from experiments.scenarios import AttackConfig, run_attack as run
from identity.registry import IdentityParams

SMALL = AttackConfig(
    base=RunConfig(n_honest=8, peer_set_size=7, num_rounds=20, global_seed=42),
    n_sybil=3, n_byzantine=2,
)
FAST = IdentityParams(pow_difficulty_bits=8)


def _scenario():
    return Scenario({0, 1}, {2}, {3}, AttackParams(coordinated_value=1000.0, activate_round=1))


def test_byzantine_broadcasts_coordinated_value():
    s = _scenario()
    assert s.broadcast_value(2, 5.0, round_now=5) == 1000.0
    assert s.broadcast_value(3, 5.0, round_now=5) == 1000.0


def test_honest_broadcasts_true_value():
    assert _scenario().broadcast_value(0, 5.0, round_now=5) == 5.0


def test_inactive_before_activation():
    assert _scenario().broadcast_value(2, 5.0, round_now=0) == 5.0


def test_offer_candidates_include_malicious():
    s = _scenario()
    n = Node.create(0, 1.0)
    n.peers = [1]
    offers = s.offer_candidates(n, round_now=5, rng=random.Random(0))
    assert 2 in offers and 3 in offers


def test_structural_defense_reduces_penetration():
    random_pen = run(SMALL, "random", "mean", FAST)[-1].sybil_penetration
    eclipse_pen = run(SMALL, "eclipse_resistant", "mean", FAST)[-1].sybil_penetration
    assert random_pen > eclipse_pen


def test_robust_aggregation_helps_under_defense():
    mean_err = run(SMALL, "sybil_resistant", "mean", FAST)[-1].err_rel
    median_err = run(SMALL, "sybil_resistant", "median", FAST)[-1].err_rel
    assert median_err < mean_err


def test_robust_aggregation_insufficient_without_structure():
    median_err = run(SMALL, "random", "median", FAST)[-1].err_rel
    assert median_err > 1.0


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — testovi napada prolaze")
