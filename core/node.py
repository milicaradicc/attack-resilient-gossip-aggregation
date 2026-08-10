from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from identity.observation import Observation


@dataclass
class Node:
    node_id: int
    x_local: float
    estimate: float = field(default=0.0)
    peers: List[int] = field(default_factory=list)
    nonce: int = 0
    observations: Dict[int, Observation] = field(default_factory=dict)

    @classmethod
    def create(cls, node_id: int, x_local: float) -> "Node":
        return cls(node_id=node_id, x_local=x_local, estimate=x_local)
