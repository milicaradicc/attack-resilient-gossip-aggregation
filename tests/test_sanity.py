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
    # peer sampling radi neprekidno, pa napadac ulazi i izlazi iz peer set-ova;
    # meri se da li je uopste probio, a ne stanje u poslednjoj rundi
    assert max(r.sybil_penetration for r in metrics.rows) > 0.0


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
                  eclipse_targets=1, discovery_offers=0)
    plain = run_single(spec_from(overlay="random", **common))
    guarded = run_single(spec_from(overlay="eclipse_resistant", **common))
    assert plain.rows[-1].eclipse_rate > 0.0
    assert guarded.rows[-1].eclipse_rate == 0.0


def test_single_churn_peer():
    # 3.8: churn kao napustanje mreze — napadac tokom odsustva ne odgovara i ne
    # emituje, a po povratku mu se brise dnevnik kod svih cvorova
    from core.setup import build_world
    spec = _one_attacker(overlay="sybil_resistant", aggregation="mean",
                         churn_period=4, churn_offline=1)
    world = build_world(spec)
    napadac = sorted(world.byzantine | world.sybil)[0]
    odsutan = [r for r in range(1, 9) if not world.scenario.responds(napadac, r, None)]
    assert odsutan, "napadac mora izostati bar jednu rundu"
    assert all(r % 4 == 0 for r in odsutan), "izostanak prati zadati ciklus"
    metrics = run_single(spec)
    assert metrics.rows[-1].sybil_penetration <= 0.2


def test_churn_clears_observation_log():
    # po povratku identitet krece cist: starost, razmene i kazna se brisu
    from core.setup import build_world
    from core import round_ops
    spec = _one_attacker(overlay="sybil_resistant", aggregation="mean",
                         churn_period=4, churn_offline=1)
    world = build_world(spec)
    napadac = sorted(world.byzantine | world.sybil)[0]
    cvor = world.nodes[0]
    round_ops.observe(cvor, napadac, 1, exchanged=True)
    cvor.observations[napadac].missed_total = 5
    world.scenario.before_round(world.nodes, 5)
    obs = cvor.observations[napadac]
    assert obs.first_seen_round == 5
    assert obs.successful_exchanges == 0
    assert obs.missed_total == 0


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
    test_churn_clears_observation_log()
    test_random_overlay_shows_higher_penetration()
    test_eclipse_overlay_keeps_higher_diversity()
    print("OK — sanity check scenariji napada (5.2.8) prolaze")