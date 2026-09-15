from __future__ import annotations

import random
from typing import List, Optional

from core.node import Node
from identity.pow import verify_pow
from identity.params import IdentityParams
from identity.scoring import identity_score
from sampling.base import choose_one, select_fanout


class SybilResistantStrategy:
    name = "sybil_resistant"

    def __init__(self, max_peers: int, params: IdentityParams, fanout: int = 0):
        self.max_peers = max_peers
        self.params = params
        # B8: broj peer-ova po rundi; 0 = ceo peer set, 1 = doslovno po spec 3.2
        self.fanout = fanout
        # B5: cvorovi cijem je peer set-u refresh otvorio mesto za jednu zamenu
        # u tekucoj rundi: {node_id: runda}
        self._open = {}

    def pow_valid(self, node: Node, candidate: int) -> bool:
        # nema registra: nonce je ono sto je kandidat sam predstavio u svojoj
        # peer_exchange ponudi i sto je observe() zabelezio uz njega (videti
        # core/round_ops.py) — ovde se samo lokalno verifikuje javnom funkcijom
        obs = node.observations.get(candidate)
        nonce = obs.nonce if obs is not None else None
        if nonce is None:
            return False
        return verify_pow(str(candidate), nonce, self.params.pow_difficulty_bits)

    def score(self, node: Node, candidate: int, round_now: int) -> float:
        obs = node.observations.get(candidate)
        first_seen = round_now if obs is None else obs.first_seen_round
        exchanges = 0 if obs is None else obs.successful_exchanges
        missed = 0 if obs is None else obs.missed_total
        return identity_score(round_now, first_seen, exchanges, self.pow_valid(node, candidate),
                              self.params.age_max, self.params.exchange_max,
                              self.params.reliability_max, missed_total=missed)

    def reason(self, node: Node, candidate: int, round_now: int) -> Optional[str]:
        if candidate == node.node_id or candidate in node.peers:
            return "self_or_duplicate"
        if not self.pow_valid(node, candidate):
            return "invalid_pow"
        obs = node.observations.get(candidate)
        age = 0 if obs is None else round_now - obs.first_seen_round
        if age < self.params.age_min:
            return "too_young"
        cand_score = self.score(node, candidate, round_now)
        if cand_score < self.params.score_threshold:
            return "low_score"
        if len(node.peers) >= self.max_peers:
            if self._open.get(node.node_id) == round_now:
                return None
            weakest = min(node.peers, key=lambda p: self.score(node, p, round_now))
            if self.score(node, weakest, round_now) >= cand_score:
                return "low_score"
        return None

    def accept_peer(self, node: Node, candidate: int, round_now: int) -> bool:
        return self.reason(node, candidate, round_now) is None

    def evict_peer(self, node: Node, round_now: int, candidate: Optional[int] = None) -> Optional[int]:
        if len(node.peers) < self.max_peers:
            return None
        if self._open.get(node.node_id) == round_now:
            self._open.pop(node.node_id, None)
        return min(node.peers, key=lambda p: self.score(node, p, round_now))

    def refresh_peers(self, node: Node, round_now: int, rng: random.Random) -> None:
        period = self.params.refresh_period
        if period <= 0:
            return None

        for peer in list(node.peers):
            if not self.pow_valid(node, peer):
                node.peers.remove(peer)

        if round_now % period == 0:
            self._open[node.node_id] = round_now
        return None

    def choose_gossip_target(self, node: Node, rng: random.Random) -> Optional[int]:
        return choose_one(node, rng)

    def select_gossip_peers(self, node: Node, rng: random.Random) -> List[int]:
        return select_fanout(node, rng, self.fanout)