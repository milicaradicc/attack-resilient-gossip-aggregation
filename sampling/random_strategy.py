from __future__ import annotations

import random
from typing import List, Optional

from core.node import Node
from core.rng import make_rng


class RandomStrategy:
    name = "random"

    def __init__(self, max_peers: int, seed: int = 0):
        self.max_peers = max_peers
        self.seed = seed

    def reason(self, node: Node, candidate: int, round_now: int) -> Optional[str]:
        if candidate == node.node_id or candidate in node.peers:
            return "self_or_duplicate"
        return None

    def accept_peer(self, node: Node, candidate: int, round_now: int) -> bool:
        return self.reason(node, candidate, round_now) is None

    def evict_peer(self, node: Node, round_now: int, candidate: Optional[int] = None) -> Optional[int]:
        if len(node.peers) < self.max_peers:
            return None
        if not node.peers:
            return None
        rng = make_rng(self.seed, "random_eviction", node.node_id, round_now)
        return rng.choice(list(node.peers))

    def refresh_peers(self, node: Node, round_now: int, rng: random.Random) -> None:
        return None

    def select_gossip_peers(self, node: Node, rng: random.Random) -> List[int]:
        return list(node.peers)