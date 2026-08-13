from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.node import Node
from sampling.random_strategy import RandomStrategy

RNG = random.Random(0)


def _node():
    n = Node.create(0, 1.0)
    n.peers = [1, 2, 3]
    return n


def test_accept_new_candidate():
    assert RandomStrategy(7).accept_peer(_node(), 9, round_now=0) is True


def test_reject_self():
    assert RandomStrategy(7).accept_peer(_node(), 0, round_now=0) is False


def test_reject_duplicate():
    assert RandomStrategy(7).accept_peer(_node(), 2, round_now=0) is False


def test_evict_returns_existing_peer():
    n = _node()
    assert RandomStrategy(len(n.peers)).evict_peer(n, round_now=0) in n.peers


def test_evict_empty_returns_none():
    n = Node.create(0, 1.0)
    assert RandomStrategy(7).evict_peer(n, round_now=0) is None


def test_select_returns_peer_set():
    n = _node()
    assert RandomStrategy(7).select_gossip_peers(n, RNG) == n.peers


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — testovi sampling strategije prolaze")
