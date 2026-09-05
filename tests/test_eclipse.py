from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import spec_from
from experiments.matrix import run_single


def _spec(overlay, beta=0.4, targets=1):
    # ciljani Eclipse: napadac koncentrise sve identitete na jednu zrtvu
    return spec_from(n_honest=20, beta=beta, overlay=overlay, aggregation="trimmed_mean",
                     seed=1, num_rounds=50, activate_round=1, pow_difficulty_bits=8,
                     eclipse_targets=targets, poison_honest_offers=0)


def test_targets_are_deterministic():
    from core.setup import build_world
    a = build_world(_spec("random", targets=2)).scenario.targets()
    b = build_world(_spec("random", targets=2)).scenario.targets()
    assert a == b and len(a) == 2


def test_no_targets_means_broad_attack():
    from core.setup import build_world
    w = build_world(_spec("random", targets=0))
    assert w.scenario.targets() == []


def test_targeted_eclipse_succeeds_without_defense():
    m = run_single(_spec("random"))
    assert m.rows[-1].eclipse_rate > 0.0


def test_bucket_defense_prevents_targeted_eclipse():
    m = run_single(_spec("eclipse_resistant"))
    assert m.rows[-1].eclipse_rate == 0.0


if __name__ == "__main__":
    test_targets_are_deterministic()
    test_no_targets_means_broad_attack()
    test_targeted_eclipse_succeeds_without_defense()
    test_bucket_defense_prevents_targeted_eclipse()
    print("OK — ciljani Eclipse napad uspeva bez zastite, odbrana ga zaustavlja")
