from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import spec_from
from in_process.matrix import run_single

MINIMAL = dict(n_honest=12, num_rounds=30, seed=1, activate_round=1,
               pow_difficulty_bits=8)


def _one_attacker(**overrides):
    spec = spec_from(beta=1 / 13, **MINIMAL, **overrides)
    assert sum(spec.malicious_counts()) == 1, spec.malicious_counts()
    return spec


def test_single_sybil_node():
    spec = _one_attacker(overlay="random", aggregation="mean",
                         byzantine_fraction=0.0)
    metrics = run_single(spec)
    assert sum(spec.malicious_counts()) == 1
    assert max(r.sybil_penetration for r in metrics.rows) > 0.0


def test_single_byzantine_outlier():
    spec = _one_attacker(overlay="random", aggregation="mean",
                         byzantine_fraction=1.0, byzantine_profile="extreme")
    assert spec.malicious_counts()[0] == 1
    benign = run_single(spec_from(beta=0.0, overlay="random",
                                  aggregation="mean", **MINIMAL))
    attacked = run_single(spec)
    assert attacked.rows[-1].err_rel > benign.rows[-1].err_rel


def test_single_eclipse_attempt():
    common = dict(n_honest=20, beta=0.4, aggregation="trimmed_mean", seed=1,
                  num_rounds=50, activate_round=1, pow_difficulty_bits=8,
                  eclipse_targets=1, discovery_offers=0)
    plain = run_single(spec_from(overlay="random", **common))
    guarded = run_single(spec_from(overlay="eclipse_resistant", **common))
    assert plain.rows[-1].eclipse_rate > 0.0
    assert guarded.rows[-1].eclipse_rate == 0.0


def test_single_churn_peer():
    from core.setup import build_world
    spec = _one_attacker(overlay="sybil_resistant", aggregation="mean",
                         churn_period=4, churn_offline=1, byzantine_fraction=0.0)
    world = build_world(spec)
    for r in range(1, 9):
        world.scenario.before_round(world.nodes, r)
    attacker = sorted(world.sybil)[0]
    absent = [r for r in range(1, 9)
              if not world.scenario.responds(attacker, r, None)]
    assert absent, "the attacker must be away for at least one round"
    for start in range(1, 6):
        window = [r for r in absent if start <= r < start + 4]
        assert len(window) == 1, f"window {start}..{start + 3}: {window}"
    metrics = run_single(spec)
    assert metrics.rows[-1].sybil_penetration <= 0.2


def test_churn_clears_observation_log():
    from core.setup import build_world
    from core import round_ops
    spec = _one_attacker(overlay="sybil_resistant", aggregation="mean",
                         churn_period=4, churn_offline=1, byzantine_fraction=0.0)
    world = build_world(spec)
    for r in range(1, 9):
        world.scenario.before_round(world.nodes, r)
    attacker = sorted(world.sybil)[0]
    node = world.nodes[0]
    round_ops.observe(node, attacker, 1, exchanged=True)
    node.observations[attacker].missed_total = 5
    churn = world.scenario._churn()
    comeback = next(r for r in range(2, 2 + 4)
                    if attacker in churn.returning_ids(world.scenario.ctx, r))
    world.scenario.before_round(world.nodes, comeback)
    obs = node.observations[attacker]
    assert obs.first_seen_round == comeback
    assert obs.successful_exchanges == 0
    assert obs.missed_total == 0


def test_random_overlay_shows_higher_penetration():
    common = dict(n_honest=20, beta=0.3, aggregation="trimmed_mean", seed=1,
                  num_rounds=50, activate_round=1, pow_difficulty_bits=8)
    plain = run_single(spec_from(overlay="random", **common))
    guarded = run_single(spec_from(overlay="sybil_resistant", **common))
    assert plain.rows[-1].sybil_penetration > guarded.rows[-1].sybil_penetration


def test_eclipse_overlay_keeps_higher_diversity():
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
    print("OK - attack sanity check scenarios (5.2.8) pass")

def test_sybil_identities_appear_gradually():
    from core.setup import build_world
    from core import round_ops
    spec = spec_from(n_honest=20, beta=0.3, overlay="random", aggregation="mean",
                     seed=1, num_rounds=30, activate_round=5,
                     pow_difficulty_bits=8, sybil_rate=0.5)
    world = build_world(spec)
    sc = world.scenario
    zivi = []
    for r in range(1, 20):
        sc.before_round({}, r)
        zivi.append(len(sc.ctx.sybil_ids))
        emit = round_ops.emitted_values(world.nodes, sc, r)
        for s_id in world.sybil - sc.ctx.sybil_ids:
            assert s_id not in emit, f"runda {r}: nestvoreni Sybil {s_id} emituje"
    assert zivi[0] == 0, "pre aktivacije nema Sybil identiteta"
    assert zivi == sorted(zivi), "broj Sybil identiteta ne opada"
    assert zivi[-1] == len(world.sybil), "do kraja nastaju svi"