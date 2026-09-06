from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import spec_from
from in_process.matrix import run_single

# 5.2.8. Sanity check scenariji napada
# Pre pune eksperimentalne matrice proveravaju se najjednostavniji scenariji sa
# po jednim napadacem, da bi se potvrdilo da attack injectori rade ispravno i da
# sistem reaguje ocekivano.

MINIMAL = dict(n_honest=12, num_rounds=30, seed=1, activate_round=1,
               pow_difficulty_bits=8)


def _one_attacker(**overrides):
    # beta biran tako da malicious_counts() da tacno jednog napadaca
    spec = spec_from(beta=1 / 13, **MINIMAL, **overrides)
    assert sum(spec.malicious_counts()) == 1, spec.malicious_counts()
    return spec


def test_single_sybil_node():
    # jedan Sybil cvor: injector ga nudi, referentna strategija ga pusta unutra
    spec = _one_attacker(overlay="random", aggregation="mean",
                         byzantine_fraction=0.0)
    metrics = run_single(spec)
    assert sum(spec.malicious_counts()) == 1
    assert metrics.rows[-1].sybil_penetration > 0.0


def test_single_byzantine_outlier():
    # jedan Byzantine cvor sa ekstremnom vrednoscu mora pomeriti mean
    spec = _one_attacker(overlay="random", aggregation="mean",
                         byzantine_fraction=1.0, byzantine_profile="extreme")
    assert spec.malicious_counts()[0] == 1
    benign = run_single(spec_from(beta=0.0, overlay="random",
                                  aggregation="mean", **MINIMAL))
    attacked = run_single(spec)
    assert attacked.rows[-1].err_rel > benign.rows[-1].err_rel


def test_single_eclipse_attempt():
    # jedan ciljani pokusaj izolacije: bez zastite zrtva gubi honest susede,
    # sa bucket diverzifikacijom ih zadrzava
    common = dict(n_honest=20, beta=0.4, aggregation="trimmed_mean", seed=1,
                  num_rounds=50, activate_round=1, pow_difficulty_bits=8,
                  eclipse_targets=1, poison_honest_offers=0)
    plain = run_single(spec_from(overlay="random", **common))
    guarded = run_single(spec_from(overlay="eclipse_resistant", **common))
    assert plain.rows[-1].eclipse_rate > 0.0
    assert guarded.rows[-1].eclipse_rate == 0.0


def test_single_churn_peer():
    # churn resetuje starost napadaca; uz age-gating to mu otezava ulazak,
    # pa penetracija ne sme biti veca nego bez churn-a
    base = dict(overlay="sybil_resistant", aggregation="mean", **MINIMAL)
    without = run_single(spec_from(beta=1 / 13, churn_period=0, **base))
    with_churn = run_single(spec_from(beta=1 / 13, churn_period=3, **base))
    assert with_churn.rows[-1].sybil_penetration <= without.rows[-1].sybil_penetration


def test_random_overlay_shows_higher_penetration():
    # 5.2.8: referentna strategija mora pokazati vecu Sybil penetraciju
    common = dict(n_honest=20, beta=0.3, aggregation="trimmed_mean", seed=1,
                  num_rounds=50, activate_round=1, pow_difficulty_bits=8)
    plain = run_single(spec_from(overlay="random", **common))
    guarded = run_single(spec_from(overlay="sybil_resistant", **common))
    assert plain.rows[-1].sybil_penetration > guarded.rows[-1].sybil_penetration


def test_eclipse_overlay_keeps_higher_diversity():
    # 5.2.8: Eclipse-resistant overlay mora odrzati vecu peer diversity
    common = dict(n_honest=20, beta=0.3, aggregation="trimmed_mean", seed=1,
                  num_rounds=50, activate_round=1, pow_difficulty_bits=8)
    plain = run_single(spec_from(overlay="random", **common))
    guarded = run_single(spec_from(overlay="eclipse_resistant", **common))
    assert guarded.rows[-1].peer_diversity > plain.rows[-1].peer_diversity


if __name__ == "__main__":
    test_single_sybil_node()
    test_single_byzantine_outlier()
    test_single_eclipse_attempt()
    test_single_churn_peer()
    test_random_overlay_shows_higher_penetration()
    test_eclipse_overlay_keeps_higher_diversity()
    print("OK — sanity check scenariji napada (5.2.8) prolaze")