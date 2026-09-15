from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.node import Node
from identity.buckets import bucket_of
from identity.observation import Observation
from identity.pow import solve_pow
from identity.params import IdentityParams
from sampling.eclipse_resistant import EclipseResistantStrategy
from sampling.sybil_resistant import SybilResistantStrategy

PARAMS = IdentityParams(
    pow_difficulty_bits=8, age_min=3, age_max=20, exchange_max=20,
    score_threshold=0.5, num_buckets=8, max_per_bucket=2,
)


def _nonce(identity: int) -> int:
    return solve_pow(str(identity), PARAMS.pow_difficulty_bits)


def _node() -> Node:
    return Node.create(0, 1.0)


def test_valid_candidate_accepted():
    s = SybilResistantStrategy(7, PARAMS)
    n = _node()
    n.observations[5] = Observation(first_seen_round=0, last_seen_round=20, nonce=_nonce(5))
    assert s.accept_peer(n, 5, round_now=20) is True


def test_candidate_without_pow_rejected():
    s = SybilResistantStrategy(7, PARAMS)
    n = _node()
    n.observations[5] = Observation(first_seen_round=0, last_seen_round=20)
    assert s.accept_peer(n, 5, round_now=20) is False


def test_insufficient_age_rejected():
    s = SybilResistantStrategy(7, PARAMS)
    n = _node()
    n.observations[5] = Observation(first_seen_round=19, last_seen_round=20, nonce=_nonce(5))
    assert s.accept_peer(n, 5, round_now=20) is False


def test_low_score_rejected():
    s = SybilResistantStrategy(7, PARAMS)
    n = _node()
    n.observations[5] = Observation(first_seen_round=17, last_seen_round=20, nonce=_nonce(5))
    assert s.accept_peer(n, 5, round_now=20) is False


def test_eviction_removes_lowest_score():
    s = SybilResistantStrategy(2, PARAMS)
    n = _node()
    n.peers = [5, 6]
    n.observations[5] = Observation(first_seen_round=0, last_seen_round=20, nonce=_nonce(5))
    n.observations[6] = Observation(first_seen_round=18, last_seen_round=20, nonce=_nonce(6))
    assert s.evict_peer(n, round_now=20) == 6


def _same_bucket_ids(target_bucket: int, count: int, exclude: set) -> list:
    out = []
    i = 100
    while len(out) < count:
        if i not in exclude and bucket_of(str(i), PARAMS.num_buckets) == target_bucket:
            out.append(i)
        i += 1
    return out


def test_bucket_full_replaces_weaker():
    n = _node()
    n.observations[5] = Observation(first_seen_round=0, last_seen_round=20, nonce=_nonce(5))
    b = bucket_of(str(5), PARAMS.num_buckets)
    n.peers = _same_bucket_ids(b, PARAMS.max_per_bucket, exclude={5})

    eclipse = EclipseResistantStrategy(7, PARAMS)
    assert eclipse.accept_peer(n, 5, round_now=20) is True
    victim = eclipse.evict_peer(n, round_now=20, candidate=5)
    assert victim in n.peers and bucket_of(str(victim), PARAMS.num_buckets) == b


def test_bucket_full_rejects_weaker_candidate():
    members = _same_bucket_ids(bucket_of(str(5), PARAMS.num_buckets), PARAMS.max_per_bucket, exclude={5})
    n = _node()
    n.peers = list(members)
    for m in members:
        n.observations[m] = Observation(first_seen_round=0, last_seen_round=20,
                                        successful_exchanges=PARAMS.exchange_max, nonce=_nonce(m))
    n.observations[5] = Observation(first_seen_round=14, last_seen_round=20, nonce=_nonce(5))

    eclipse = EclipseResistantStrategy(7, PARAMS)
    assert eclipse.accept_peer(n, 5, round_now=20) is False


def test_peer_set_never_exceeds_limit():
    from core.config import spec_from
    from core.setup import build_world
    from in_process.engine import Engine
    from core.rng import make_rng
    from aggregation import get_aggregation
    from metrics.experiment_metrics import ExperimentMetrics
    from sampling import get_strategy
    for overlay in ("random", "sybil_resistant", "eclipse_resistant"):
        spec = spec_from(n_honest=20, beta=0.3, overlay=overlay,
                         aggregation="trimmed_mean", seed=1, num_rounds=50,
                         activate_round=1, pow_difficulty_bits=8)
        world = build_world(spec)
        metrics = ExperimentMetrics(x_star=world.x_star, num_buckets=spec.num_buckets)
        Engine(world.nodes, get_aggregation("trimmed_mean", alpha=spec.trim_alpha),
               get_strategy(overlay, spec.peer_set_size, world.id_params),
               world.scenario, spec.num_rounds, metrics,
               make_rng(spec.seed, "matrix", overlay, spec.aggregation),
               world.nonces, timeout_rounds=spec.timeout_rounds).run()
        for node_id, node in world.nodes.items():
            assert len(node.peers) <= spec.peer_set_size, (
                f"{overlay}: cvor {node_id} ima {len(node.peers)} suseda")


def test_eclipse_never_exceeds_bucket_limit():
    from collections import Counter
    from core.config import spec_from
    from in_process.engine import Engine
    from core.rng import make_rng
    from core.setup import build_world
    from aggregation import get_aggregation
    from metrics.experiment_metrics import ExperimentMetrics
    from sampling import get_strategy
    for n_honest in (10, 15, 20):
        spec = spec_from(n_honest=n_honest, beta=0.3, overlay="eclipse_resistant",
                         aggregation="trimmed_mean", seed=1, num_rounds=50,
                         activate_round=1, pow_difficulty_bits=8)
        world = build_world(spec)
        pocetno = max(max(Counter(bucket_of(str(p), spec.num_buckets)
                                  for p in nd.peers).values())
                      for nd in world.nodes.values())
        strategy = get_strategy("eclipse_resistant", spec.peer_set_size, world.id_params)
        metrics = ExperimentMetrics(x_star=world.x_star, num_buckets=spec.num_buckets)
        Engine(world.nodes, get_aggregation("trimmed_mean", alpha=spec.trim_alpha),
               strategy, world.scenario, spec.num_rounds, metrics,
               make_rng(spec.seed, "matrix", "eclipse_resistant", spec.aggregation),
               world.nonces, timeout_rounds=spec.timeout_rounds).run()
        for node_id, node in world.nodes.items():
            counts = Counter(strategy.bucket(p) for p in node.peers)
            worst = max(counts.values()) if counts else 0
            assert worst <= max(pocetno, world.id_params.max_per_bucket), (
                f"n={n_honest}, cvor {node_id}: {worst} peer-ova iz istog bucketa, "
                f"pocetna topologija imala {pocetno}")


def test_admission_decision_respects_bucket_limit():
    from collections import Counter
    from core import round_ops
    from core.config import spec_from
    from core.setup import build_world
    from sampling import get_strategy
    spec = spec_from(n_honest=20, beta=0.3, overlay="eclipse_resistant",
                     aggregation="trimmed_mean", seed=1, num_rounds=30,
                     activate_round=1, pow_difficulty_bits=8)
    world = build_world(spec)
    strategy = get_strategy("eclipse_resistant", spec.peer_set_size, world.id_params)
    limit = world.id_params.max_per_bucket
    candidates = [(i, world.nonces[i]) for i in sorted(world.byzantine | world.sybil)]
    for round_now in range(1, spec.num_rounds + 1):
        for node in world.nodes.values():
            before = Counter(strategy.bucket(p) for p in node.peers)
            round_ops.admit(node, strategy, round_now, offered=candidates)
            after = Counter(strategy.bucket(p) for p in node.peers)
            for bucket, count in after.items():
                assert count <= max(limit, before.get(bucket, 0)), (
                    f"runda {round_now}: bucket {bucket} narastao na {count}")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — testovi strategija zaštite prolaze")


def test_all_strategies_implement_spec_interface():
    from core.rng import make_rng
    from sampling import get_strategy

    for overlay in ("random", "sybil_resistant", "eclipse_resistant"):
        s = get_strategy(overlay, 7, PARAMS, seed=1)
        for metod in ("accept_peer", "evict_peer", "refresh_peers",
                      "choose_gossip_target", "select_gossip_peers"):
            assert callable(getattr(s, metod, None)), f"{overlay} nema {metod}"

        n = _node()
        n.peers = [1, 2, 3, 4, 5]
        rng = make_rng(1, "gossip_target")
        target = s.choose_gossip_target(n, rng)
        assert target in n.peers, f"{overlay}: izabran peer van peer set-a"

        prazan = _node()
        assert s.choose_gossip_target(prazan, rng) is None, (
            f"{overlay}: prazan peer set mora dati None")