from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from identity.observation import Observation


@dataclass
class Node:
    node_id: int # identitet
    x_local: float
    estimate: float = field(default=0.0) # lokalna agregaciona procena 
    peers: List[int] = field(default_factory=list) # lokalni peer set
    observations: Dict[int, Observation] = field(default_factory=dict) # observation log
    nonce: int = 0 # sopstveni resen PoW nonce; cvor ga sam cuva, nema centralnog registra

    @classmethod
    def create(cls, node_id: int, x_local: float) -> "Node":
        return cls(node_id=node_id, x_local=x_local, estimate=x_local)
