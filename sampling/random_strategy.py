from __future__ import annotations

import random
from typing import List, Optional

from core.node import Node


class RandomStrategy:
    name = "random"

    def __init__(self, max_peers: int):
        self.max_peers = max_peers

    def reason(self, node: Node, candidate: int, round_now: int) -> Optional[str]:
        if candidate == node.node_id or candidate in node.peers:
            return "self_or_duplicate"
        return None

    def accept_peer(self, node: Node, candidate: int, round_now: int) -> bool:
        return self.reason(node, candidate, round_now) is None

    def evict_peer(self, node: Node, round_now: int, candidate: Optional[int] = None) -> Optional[int]:
        if len(node.peers) < self.max_peers:
            return None
        return node.peers[0] if node.peers else None

    def refresh_peers(self, node: Node, round_now: int, rng: random.Random) -> None:
        return None

    def select_gossip_peers(self, node: Node, rng: random.Random) -> List[int]:
        return list(node.peers)

    def choose_gossip_target(self, node: Node, rng: random.Random) -> Optional[int]:
        peers = self.select_gossip_peers(node, rng)
        return rng.choice(peers) if peers else None
