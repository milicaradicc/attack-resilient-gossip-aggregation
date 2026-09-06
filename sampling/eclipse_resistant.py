from __future__ import annotations

from typing import List, Optional

from core.node import Node
from identity.buckets import bucket_of
from sampling.sybil_resistant import SybilResistantStrategy
 

class EclipseResistantStrategy(SybilResistantStrategy):
    name = "eclipse_resistant"

    def bucket(self, identity: int) -> int:
        return bucket_of(str(identity), self.params.num_buckets)

    def _bucket_peers(self, node: Node, target: int) -> List[int]:
        return [p for p in node.peers if self.bucket(p) == target]

    def _weakest_in_bucket(self, node: Node, target: int, round_now: int) -> Optional[int]:
        members = self._bucket_peers(node, target)
        if not members:
            return None
        return min(members, key=lambda p: self.score(node, p, round_now))

    def reason(self, node: Node, candidate: int, round_now: int) -> Optional[str]:
        base = super().reason(node, candidate, round_now)
        if base is not None:
            return base
        target = self.bucket(candidate)
        if len(self._bucket_peers(node, target)) < self.params.max_per_bucket:
            return None
        weakest = self._weakest_in_bucket(node, target, round_now)
        if self.score(node, candidate, round_now) > self.score(node, weakest, round_now):
            return None
        return "bucket_full"

    def evict_peer(self, node: Node, round_now: int, candidate: Optional[int] = None) -> Optional[int]:
        if candidate is not None:
            target = self.bucket(candidate)
            if len(self._bucket_peers(node, target)) >= self.params.max_per_bucket:
                return self._weakest_in_bucket(node, target, round_now)
        if len(node.peers) < self.max_peers:
            return None
        return min(node.peers, key=lambda p: self.score(node, p, round_now))
