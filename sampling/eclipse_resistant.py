from __future__ import annotations

from collections import Counter
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

    def _crowded_bucket(self, node: Node) -> Optional[int]:
        if not node.peers:
            return None
        counts = Counter(self.bucket(p) for p in node.peers)
        top = max(counts.values())
        return min(b for b, c in counts.items() if c == top)

    def _displaceable(self, node: Node, candidate: int, round_now: int) -> Optional[int]:
        # koga bi kandidat istisnuo. Ako je njegova grupa puna, zamena mora
        # ostati unutar nje da koncentracija ne bi porasla. U suprotnom se
        # istiskuje globalno najslabiji sused, isto kao kod Sybil-otporne
        # strategije: to je najcesce identitet primljen u prethodnom
        # osvezavanju, bez istorije razmena, pa se napadaci ne mogu
        # akumulirati. Istiskivanje iz najzastupljenije grupe bi umesto toga
        # cesto uklanjalo cestite susede i ostavljalo ranije primljene
        # napadace, koji bi se gomilali grupu po grupu.
        target = self.bucket(candidate)
        if len(self._bucket_peers(node, target)) >= self.params.max_per_bucket:
            return self._weakest_in_bucket(node, target, round_now)
        if not node.peers:
            return None
        return min(node.peers, key=lambda p: self.score(node, p, round_now))

    def reason(self, node: Node, candidate: int, round_now: int) -> Optional[str]:
        base = super().reason(node, candidate, round_now)
        if base is not None:
            return base
        if len(node.peers) < self.max_peers:
            target = self.bucket(candidate)
            if len(self._bucket_peers(node, target)) < self.params.max_per_bucket:
                return None
            weakest = self._weakest_in_bucket(node, target, round_now)
            if weakest is not None and \
                    self.score(node, candidate, round_now) > self.score(node, weakest, round_now):
                return None
            return "bucket_full"

        victim = self._displaceable(node, candidate, round_now)
        if victim is None:
            return "bucket_full"
        # u prozoru osvezavanja kandidat sme da udje i kada nije bolji od
        # zrtve, jer bi se peer set inace zamrznuo (nov kandidat nema istoriju
        # razmena i retko nadmasuje starije susede). Olaksica vazi samo ako
        # kandidatova grupa ima mesta: kada je puna, zamena bi istisnula
        # cestitog suseda iz te grupe, cime bi se kod zrtve Eclipse napada
        # napadaci gomilali grupu po grupu.
        if self._open.get(node.node_id) == round_now:
            target = self.bucket(candidate)
            if len(self._bucket_peers(node, target)) < self.params.max_per_bucket:
                return None
        if self.score(node, candidate, round_now) > self.score(node, victim, round_now):
            return None
        return "bucket_full"

    def evict_peer(self, node: Node, round_now: int, candidate: Optional[int] = None) -> Optional[int]:
        if self._open.get(node.node_id) == round_now:
            self._open.pop(node.node_id, None)
        if candidate is not None:
            target = self.bucket(candidate)
            if len(self._bucket_peers(node, target)) >= self.params.max_per_bucket:
                return self._weakest_in_bucket(node, target, round_now)
        if len(node.peers) < self.max_peers:
            return None
        if candidate is None:
            return min(node.peers, key=lambda p: self.score(node, p, round_now))
        return self._displaceable(node, candidate, round_now)