from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import spec_from
from in_process.matrix import run_single

# 5.2.8. Attack sanity check scenarios
# Before the full experimental matrix, the simplest scenarios with a single
# attacker are checked, to confirm that the attack injectors work correctly and
# that the system reacts as expected.

MINIMAL = dict(n_honest=12, num_rounds=30, seed=1, activate_round=1,
               pow_difficulty_bits=8)


def _one_attacker(**overrides):
    # beta chosen so that malicious_counts() yields exactly one attacker
    spec = spec_from(beta=1 / 13, **MINIMAL, **overrides)
    assert sum(spec.malicious_counts()) == 1, spec.malicious_counts()
    return spec


def test_single_sybil_node():
    # a single Sybil node: the injector advertises it, the baseline strategy lets it in
    spec = _one_attacker(overlay="random", aggregation="mean",
                         byzantine_fraction=0.0)
    metrics = run_single(spec)
    assert sum(spec.malicious_counts()) == 1
    # peer sampling runs continuously, so the attacker enters and leaves peer sets;
    # what is measured is whether it ever broke in, not the state in the last round
    assert max(r.sybil_penetration for r in metrics.rows) > 0.0


def test_single_byzantine_outlier():
    # a single Byzantine node with an extreme value must shift the mean
    spec = _one_attacker(overlay="random", aggregation="mean",
                         byzantine_fraction=1.0, byzantine_profile="extreme")
    assert spec.malicious_counts()[0] == 1
    benign = run_single(spec_from(beta=0.0, overlay="random",
                                  aggregation="mean", **MINIMAL))
    attacked = run_single(spec)
    assert attacked.rows[-1].err_rel > benign.rows[-1].err_rel


def test_single_eclipse_attempt():
    # a single targeted isolation attempt: without protection the victim loses its
    # honest neighbours, with bucket diversification it keeps them
    common = dict(n_honest=20, beta=0.4, aggregation="trimmed_mean", seed=1,
                  num_rounds=50, activate_round=1, pow_difficulty_bits=8,
                  eclipse_targets=1, discovery_offers=0)
    plain = run_single(spec_from(overlay="random", **common))
    guarded = run_single(spec_from(overlay="eclipse_resistant", **common))
    assert plain.rows[-1].eclipse_rate > 0.0
    assert guarded.rows[-1].eclipse_rate == 0.0


def test_single_churn_peer():
    # 3.8: churn as leaving the network - while away the attacker neither responds
    # nor broadcasts, and on return its log is wiped at every node
    from core.setup import build_world
    spec = _one_attacker(overlay="sybil_resistant", aggregation="mean",
                         churn_period=4, churn_offline=1)
    world = build_world(spec)
    attacker = sorted(world.byzantine | world.sybil)[0]
    absent = [r for r in range(1, 9)
              if not world.scenario.responds(attacker, r, None)]
    assert absent, "the attacker must be away for at least one round"
    # the schedule is not checked against absolute rounds: every identity has its
    # own phase (so that they do not all leave at the same time), so what is
    # checked is the property of the cycle - exactly churn_offline absences in
    # every window of length churn_period
    for start in range(1, 6):
        window = [r for r in absent if start <= r < start + 4]
        assert len(window) == 1, f"window {start}..{start + 3}: {window}"
    metrics = run_single(spec)
    assert metrics.rows[-1].sybil_penetration <= 0.2


def test_churn_clears_observation_log():
    # after returning the identity starts clean: age, exchanges and the penalty are wiped
    from core.setup import build_world
    from core import round_ops
    spec = _one_attacker(overlay="sybil_resistant", aggregation="mean",
                         churn_period=4, churn_offline=1)
    world = build_world(spec)
    attacker = sorted(world.byzantine | world.sybil)[0]
    node = world.nodes[0]
    round_ops.observe(node, attacker, 1, exchanged=True)
    node.observations[attacker].missed_total = 5
    # the round of return depends on that identity's phase, so it is asked of the module
    churn = world.scenario._churn()
    comeback = next(r for r in range(2, 2 + 4)
                    if attacker in churn.returning_ids(world.scenario.ctx, r))
    world.scenario.before_round(world.nodes, comeback)
    obs = node.observations[attacker]
    assert obs.first_seen_round == comeback
    assert obs.successful_exchanges == 0
    assert obs.missed_total == 0


def test_random_overlay_shows_higher_penetration():
    # 5.2.8: the baseline strategy must show higher Sybil penetration
    common = dict(n_honest=20, beta=0.3, aggregation="trimmed_mean", seed=1,
                  num_rounds=50, activate_round=1, pow_difficulty_bits=8)
    plain = run_single(spec_from(overlay="random", **common))
    guarded = run_single(spec_from(overlay="sybil_resistant", **common))
    assert plain.rows[-1].sybil_penetration > guarded.rows[-1].sybil_penetration


def test_eclipse_overlay_keeps_higher_diversity():
    # 5.2.8: the Eclipse-resistant overlay must maintain higher peer diversity
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