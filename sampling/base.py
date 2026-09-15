from __future__ import annotations

import random
from typing import List, Optional, Protocol, runtime_checkable

from core.node import Node


@runtime_checkable
class SamplingStrategy(Protocol):
    name: str
    max_peers: int

    def accept_peer(self, node: Node, candidate: int, round_now: int) -> bool: ...

    def evict_peer(self, node: Node, round_now: int, candidate: Optional[int] = None) -> Optional[int]: ...

    def refresh_peers(self, node: Node, round_now: int, rng: random.Random) -> None: ...

    def choose_gossip_target(self, node: Node, rng: random.Random) -> Optional[int]: ...

    def select_gossip_peers(self, node: Node, rng: random.Random) -> List[int]: ...


def select_fanout(node: Node, rng: random.Random, fanout: int) -> List[int]:
    peers = list(node.peers)
    if fanout <= 0 or fanout >= len(peers):
        return peers
    return rng.sample(peers, fanout)


def choose_one(node: Node, rng: random.Random) -> Optional[int]:
    peers = select_fanout(node, rng, 1)
    return peers[0] if peers else None