from __future__ import annotations

from typing import Optional

from core.node import Node
from identity.buckets import bucket_of
from sampling.sybil_resistant import SybilResistantStrategy


class EclipseResistantStrategy(SybilResistantStrategy):
    name = "eclipse_resistant"

    def bucket(self, identity: int) -> int:
        return bucket_of(str(identity), self.params.num_buckets)

    def reason(self, node: Node, candidate: int, round_now: int) -> Optional[str]:
        base = super().reason(node, candidate, round_now)
        if base is not None:
            return base
        target = self.bucket(candidate)
        occupancy = sum(1 for p in node.peers if self.bucket(p) == target)
        if occupancy >= self.params.max_per_bucket:
            return "bucket_full"
        return None
