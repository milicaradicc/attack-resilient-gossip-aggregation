from __future__ import annotations

import random
from typing import List, Optional, Protocol, runtime_checkable

from core.node import Node


@runtime_checkable
class SamplingStrategy(Protocol):
    name: str
    max_peers: int

    def accept_peer(self, node: Node, candidate: int, round_now: int) -> bool: ...

    def evict_peer(self, node: Node, round_now: int) -> Optional[int]: ...

    def refresh_peers(self, node: Node, round_now: int, rng: random.Random) -> None: ...

    def select_gossip_peers(self, node: Node, rng: random.Random) -> List[int]: ...
