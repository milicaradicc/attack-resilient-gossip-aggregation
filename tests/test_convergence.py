from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import spec_from
from core.engine import Engine
from core.rng import make_rng
from core.setup import build_world
from aggregation import get_aggregation
from metrics.experiment_metrics import ExperimentMetrics
from sampling import get_strategy
from tests.helpers import run_benign as run


def _run_world(spec):
    # pokretanje koje zadrzava pristup samim cvorovima (procene i peer set-ovi),
    # potrebno za proveru konvergencije po cvoru i za replay peer set-ova
    world = build_world(spec)
    metrics = ExperimentMetrics(x_star=world.x_star, num_buckets=spec.num_buckets)
    agg = get_aggregation(spec.aggregation)
    sampling = get_strategy(spec.overlay, spec.peer_set_size, world.registry, world.id_params)
    rng = make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation)
    Engine(world.nodes, agg, sampling, world.scenario, spec.num_rounds, metrics, rng,
           timeout_rounds=spec.timeout_rounds).run()
    return world, metrics


def test_benign_convergence():
    rows = run(n_honest=10, peer_set_size=7, num_rounds=50, seed=42)
    last = rows[-1]
    assert last.spread < 1e-6, f"nema konsenzusa, spread={last.spread}"
    assert last.err_rel < 1e-2, f"greška prevelika, err_rel={last.err_rel}"


def test_every_node_reaches_consensus():
    # 5.2.6: uslov iz specifikacije je po cvoru, |x_i - x*| < 0.01 za SVAKI honest cvor.
    # Ispunjen je jer je topologija regularna (svi cvorovi imaju isti broj suseda),
    # pa gossip usrednjavanje konvergira tacno ka aritmetickoj sredini.
    spec = spec_from(n_honest=10, beta=0.0, overlay="random", aggregation="mean",
                     seed=42, num_rounds=50)
    world, _ = _run_world(spec)
    for node_id, node in world.nodes.items():
        assert abs(node.estimate - world.x_star) < 0.01, (
            f"cvor {node_id} nije konvergirao: {node.estimate} vs {world.x_star}")


def test_topology_is_regular():
    # svaki cvor bira tacno k suseda; k-regularan graf postoji samo kada je n*k paran,
    # pa je za neparno n (npr. 15) jedan cvor sa k-1 suseda neizbezan
    from core.overlay import build_random_overlay
    from core.rng import make_rng
    for n in (10, 20):
        graph = build_random_overlay(n, 7, make_rng(1, "topology"))
        assert {len(v) for v in graph.values()} == {7}
    graph = build_random_overlay(15, 7, make_rng(1, "topology"))
    degrees = sorted(len(v) for v in graph.values())
    assert degrees[0] == 6 and degrees[1:] == [7] * 14


def test_replay_reproduces_peer_sets():
    # 5.2.7: replay mora reprodukovati i peer set-ove, ne samo agregacione vrednosti
    spec = spec_from(n_honest=12, beta=0.3, overlay="eclipse_resistant",
                     aggregation="trimmed_mean", seed=7, num_rounds=20,
                     activate_round=1, pow_difficulty_bits=8)
    a, ma = _run_world(spec)
    b, mb = _run_world(spec)
    for node_id in a.nodes:
        assert a.nodes[node_id].peers == b.nodes[node_id].peers, (
            f"peer set cvora {node_id} nije reprodukovan")
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
    test_topology_is_regular()
    test_replay_reproduces_peer_sets()
    test_determinism()
    test_different_seed_differs()
    print("OK — svi testovi Faze 0 prolaze")