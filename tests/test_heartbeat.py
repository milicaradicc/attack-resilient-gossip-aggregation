from __future__ import annotations

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from attacks.scenario import AttackParams, Scenario
from core.config import RunSpec
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


def _spec(unresponsive_p, timeout_rounds, overlay="random"):
    # referentna strategija se koristi da bi cutljivi napadaci uopste usli u peer set;
    # tek tada heartbeat ima koga da izbaci
    from core.config import spec_from
    return spec_from(n_honest=10, beta=0.3, overlay=overlay, aggregation="mean",
                     seed=1, num_rounds=50, activate_round=1, pow_difficulty_bits=8,
                     timeout_rounds=timeout_rounds, unresponsive_p=unresponsive_p)


def test_timeout_evicts_silent_peers():
    m = run_single(_spec(unresponsive_p=0.9, timeout_rounds=2))
    assert sum(r.timeouts for r in m.rows) > 0


def test_no_timeouts_when_all_respond():
    m = run_single(_spec(unresponsive_p=0.0, timeout_rounds=2))
    assert sum(r.timeouts for r in m.rows) == 0


def test_observation_counts_total_misses_and_timeouts():
    from core.setup import build_world
    from core.engine import Engine
    from core.rng import make_rng
    from aggregation import get_aggregation
    from metrics.experiment_metrics import ExperimentMetrics
    from sampling import get_strategy
    spec = _spec(unresponsive_p=0.9, timeout_rounds=2)
    world = build_world(spec)
    metrics = ExperimentMetrics(x_star=world.x_star, num_buckets=spec.num_buckets)
    Engine(world.nodes, get_aggregation("mean"),
           get_strategy(spec.overlay, spec.peer_set_size, world.registry, world.id_params),
           world.scenario, spec.num_rounds, metrics, make_rng(spec.seed, "x"),
           timeout_rounds=spec.timeout_rounds).run()
    obs = [o for node in world.nodes.values() for o in node.observations.values()]
    assert any(o.missed_total > 0 for o in obs)
    assert any(o.timeout_count > 0 for o in obs)


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    test_observation_counts_total_misses_and_timeouts()
    print("OK — testovi heartbeat/timeout prolaze")