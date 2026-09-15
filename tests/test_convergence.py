from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import spec_from
from in_process.engine import Engine
from core.rng import make_rng
from core.setup import build_world
from aggregation import get_aggregation
from metrics.experiment_metrics import ExperimentMetrics
from sampling import get_strategy
from tests.helpers import run_benign as run


def _run_world(spec):
    world = build_world(spec)
    metrics = ExperimentMetrics(x_star=world.x_star, num_buckets=spec.num_buckets)
    agg = get_aggregation(spec.aggregation)
    sampling = get_strategy(spec.overlay, spec.peer_set_size, world.id_params)
    rng = make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation)
    Engine(world.nodes, agg, sampling, world.scenario, spec.num_rounds, metrics, rng,
           world.nonces, timeout_rounds=spec.timeout_rounds).run()
    return world, metrics


def test_benign_convergence():
    spec = spec_from(n_honest=10, beta=0.0, overlay="sybil_resistant",
                     aggregation="mean", seed=42, num_rounds=50)
    _, metrics = _run_world(spec)
    last = metrics.rows[-1]
    assert last.spread < 1e-6, f"no consensus, spread={last.spread}"
    assert last.err_rel < 1e-2, f"error too large, err_rel={last.err_rel}"


def test_every_node_reaches_consensus():
    spec = spec_from(n_honest=10, beta=0.0, overlay="sybil_resistant",
                     aggregation="mean", seed=42, num_rounds=50)
    world, _ = _run_world(spec)
    for node_id, node in world.nodes.items():
        assert abs(node.estimate - world.x_star) < 0.01, (
            f"node {node_id} did not converge: {node.estimate} vs {world.x_star}")


def test_defenses_do_not_break_benign_convergence():
    results = {}
    for overlay in ("sybil_resistant", "eclipse_resistant"):
        spec = spec_from(n_honest=10, beta=0.0, overlay=overlay, aggregation="mean",
                         seed=42, num_rounds=50)
        world, _ = _run_world(spec)
        for node_id, node in world.nodes.items():
            assert abs(node.estimate - world.x_star) < 0.01, (
                f"{overlay}: node {node_id} did not converge")
        results[overlay] = world.nodes[0].estimate
    values = list(results.values())
    assert max(values) - min(values) < 1e-6, (
        f"strategies converge to different values: {results}")


def test_initial_values_are_random_but_reproducible():
    spec = spec_from(n_honest=10, beta=0.0, seed=42)
    first, _ = _run_world(spec)
    second, _ = _run_world(spec)
    values = [n.x_local for n in first.nodes.values()]
    assert len(set(values)) > 1, "initial values are not distinct"
    assert all(spec.value_low <= v <= spec.value_high for v in values)
    assert values == [n.x_local for n in second.nodes.values()]


def test_convergence_limited_by_irregular_topology():
    worst_cases = []
    for seed in (1, 2, 3, 42):
        spec = spec_from(n_honest=15, beta=0.0, overlay="sybil_resistant",
                         aggregation="mean", seed=seed, num_rounds=50)
        world, _ = _run_world(spec)
        worst_cases.append(max(abs(n.estimate - world.x_star)
                               for n in world.nodes.values()))
    assert max(worst_cases) < 1.0, (
        f"deviation {max(worst_cases)} is outside the expected order of magnitude")

    spec = spec_from(n_honest=16, beta=0.0, overlay="sybil_resistant",
                     aggregation="mean", seed=42, num_rounds=50)
    world, _ = _run_world(spec)
    regular = max(abs(n.estimate - world.x_star) for n in world.nodes.values())
    assert regular < 1e-6, (
        f"a regular topology must converge exactly, but the deviation is {regular}")


def test_without_admission_benign_convergence_degrades():
    without = spec_from(n_honest=10, beta=0.0, overlay="random", aggregation="mean",
                        seed=42, num_rounds=50)
    with_admission = spec_from(n_honest=10, beta=0.0, overlay="sybil_resistant",
                               aggregation="mean", seed=42, num_rounds=50)
    world_without, _ = _run_world(without)
    world_with, _ = _run_world(with_admission)
    deviation_without = max(abs(n.estimate - world_without.x_star)
                            for n in world_without.nodes.values())
    deviation_with = max(abs(n.estimate - world_with.x_star)
                         for n in world_with.nodes.values())
    assert deviation_with < 0.01, "admission control preserves exact convergence"
    assert deviation_without > deviation_with, (
        "without admission control a larger deviation is expected")


def test_topology_is_regular():
    from core.overlay import build_random_overlay
    from core.rng import make_rng
    for n in (10, 20):
        graph = build_random_overlay(n, 7, make_rng(1, "topology"))
        assert {len(v) for v in graph.values()} == {7}
    graph = build_random_overlay(15, 7, make_rng(1, "topology"))
    degrees = sorted(len(v) for v in graph.values())
    assert degrees[0] == 6 and degrees[1:] == [7] * 14


def test_replay_reproduces_peer_sets():
    spec = spec_from(n_honest=12, beta=0.3, overlay="eclipse_resistant",
                     aggregation="trimmed_mean", seed=7, num_rounds=20,
                     activate_round=1, pow_difficulty_bits=8)
    a, ma = _run_world(spec)
    b, mb = _run_world(spec)
    for node_id in a.nodes:
        assert a.nodes[node_id].peers == b.nodes[node_id].peers, (
            f"peer set of node {node_id} was not reproduced")
        assert a.nodes[node_id].estimate == b.nodes[node_id].estimate
    assert [r.err_rel for r in ma.rows] == [r.err_rel for r in mb.rows]


def test_determinism():
    a = run(seed=1234)
    b = run(seed=1234)
    assert len(a) == len(b)
    for ra, rb in zip(a, b):
        assert ra.round == rb.round
        assert ra.err_rel == rb.err_rel
        assert ra.spread == rb.spread


def test_different_seed_differs():
    a = run(seed=1)
    b = run(seed=2)
    assert a[0].spread != b[0].spread


if __name__ == "__main__":
    test_benign_convergence()
    test_every_node_reaches_consensus()
    test_defenses_do_not_break_benign_convergence()
    test_initial_values_are_random_but_reproducible()
    test_convergence_limited_by_irregular_topology()
    test_topology_is_regular()
    test_replay_reproduces_peer_sets()
    test_determinism()
    test_different_seed_differs()
    print("OK — all Phase 0 tests pass")