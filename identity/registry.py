from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class IdentityParams:
    pow_difficulty_bits: int = 12
    age_min: int = 3
    age_max: int = 20
    exchange_max: int = 20
    score_threshold: float = 0.5
    num_buckets: int = 8
    max_per_bucket: int = 2
    timeout_rounds: int = 3


@dataclass
class IdentityRegistry:
    nonces: Dict[int, int] = field(default_factory=dict)

    def register(self, identity: int, nonce: int) -> None:
        self.nonces[identity] = nonce

    def nonce_of(self, identity: int) -> Optional[int]:
        return self.nonces.get(identity)
