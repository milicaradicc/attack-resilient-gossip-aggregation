from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.node import Node
from identity.buckets import bucket_of
from identity.observation import Observation
from identity.pow import solve_pow
from identity.registry import IdentityParams, IdentityRegistry
from sampling.eclipse_resistant import EclipseResistantStrategy
from sampling.sybil_resistant import SybilResistantStrategy

PARAMS = IdentityParams(
    pow_difficulty_bits=8, age_min=3, age_max=20, exchange_max=20,
    score_threshold=0.5, num_buckets=8, max_per_bucket=2,
)


def _registry(*ids: int) -> IdentityRegistry:
    reg = IdentityRegistry()
    for i in ids:
        reg.register(i, solve_pow(str(i), PARAMS.pow_difficulty_bits))
    return reg


def _node() -> Node:
    return Node.create(0, 1.0)


def test_valid_candidate_accepted():
    reg = _registry(5)
    s = SybilResistantStrategy(7, reg, PARAMS)
    n = _node()
    n.observations[5] = Observation(first_seen_round=0, last_seen_round=20)
    assert s.accept_peer(n, 5, round_now=20) is True


def test_candidate_without_pow_rejected():
    reg = _registry()
    s = SybilResistantStrategy(7, reg, PARAMS)
    n = _node()
    n.observations[5] = Observation(first_seen_round=0, last_seen_round=20)
    assert s.accept_peer(n, 5, round_now=20) is False


def test_insufficient_age_rejected():
    reg = _registry(5)
    s = SybilResistantStrategy(7, reg, PARAMS)
    n = _node()
    n.observations[5] = Observation(first_seen_round=19, last_seen_round=20)
    assert s.accept_peer(n, 5, round_now=20) is False


def test_low_score_rejected():
    reg = _registry(5)
    s = SybilResistantStrategy(7, reg, PARAMS)
    n = _node()
    n.observations[5] = Observation(first_seen_round=17, last_seen_round=20)
    assert s.accept_peer(n, 5, round_now=20) is False


def test_eviction_removes_lowest_score():
    reg = _registry(5, 6)
    s = SybilResistantStrategy(2, reg, PARAMS)
    n = _node()
    n.peers = [5, 6]
    n.observations[5] = Observation(first_seen_round=0, last_seen_round=20)
    n.observations[6] = Observation(first_seen_round=18, last_seen_round=20)
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
    reg = _registry(5)
    n = _node()
    n.observations[5] = Observation(first_seen_round=0, last_seen_round=20)
    b = bucket_of(str(5), PARAMS.num_buckets)
    n.peers = _same_bucket_ids(b, PARAMS.max_per_bucket, exclude={5})

    eclipse = EclipseResistantStrategy(7, reg, PARAMS)
    assert eclipse.accept_peer(n, 5, round_now=20) is True
    victim = eclipse.evict_peer(n, round_now=20, candidate=5)
    assert victim in n.peers and bucket_of(str(victim), PARAMS.num_buckets) == b


def test_bucket_full_rejects_weaker_candidate():
    members = _same_bucket_ids(bucket_of(str(5), PARAMS.num_buckets), PARAMS.max_per_bucket, exclude={5})
    reg = _registry(5, *members)
    n = _node()
    n.peers = list(members)
    for m in members:
        n.observations[m] = Observation(first_seen_round=0, last_seen_round=20,
                                        successful_exchanges=PARAMS.exchange_max)
    n.observations[5] = Observation(first_seen_round=14, last_seen_round=20)

    eclipse = EclipseResistantStrategy(7, reg, PARAMS)
    assert eclipse.accept_peer(n, 5, round_now=20) is False


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — testovi strategija zaštite prolaze")
