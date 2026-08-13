from __future__ import annotations

import random
from typing import List, Optional

from core.node import Node
from identity.pow import verify_pow
from identity.registry import IdentityParams, IdentityRegistry
from identity.scoring import identity_score

# sybil-resistant strategija uvodi admission uslove: validan PoW, minimalnu starost identiteta i dovoljan identity score.
# 4.5.2. Sybil-resistant strategija 
# Sybil-resistant strategija uvodi tri admission uslova: 
# 1. validan PoW,  
# 2. minimalni age,  
# 3. minimalni identity score.  
# Peer kandidat se prihvata samo ako zadovoljava sve uslove i ima bolji score od postojećih slabih peer-ova. 
# Eviction preferira peer-ove sa najmanjim score-om ili peer-ove koji ne odgovaraju dovoljno dugo. Ciljevi 
# su ograničavanje Sybil penetracije i favorizovanje stabilnih peer-ova. 

class SybilResistantStrategy:
    name = "sybil_resistant"

    def __init__(self, max_peers: int, registry: IdentityRegistry, params: IdentityParams):
        self.max_peers = max_peers
        self.registry = registry
        self.params = params

    def pow_valid(self, candidate: int) -> bool:
        nonce = self.registry.nonce_of(candidate)
        if nonce is None:
            return False
        return verify_pow(str(candidate), nonce, self.params.pow_difficulty_bits)

    def score(self, node: Node, candidate: int, round_now: int) -> float:
        obs = node.observations.get(candidate)
        first_seen = round_now if obs is None else obs.first_seen_round
        exchanges = 0 if obs is None else obs.successful_exchanges
        return identity_score(round_now, first_seen, exchanges, self.pow_valid(candidate),
                              self.params.age_max, self.params.exchange_max)

    def reason(self, node: Node, candidate: int, round_now: int) -> Optional[str]:
        if candidate == node.node_id or candidate in node.peers:
            return "self_or_duplicate"
        if not self.pow_valid(candidate):
            return "invalid_pow"
        obs = node.observations.get(candidate)
        age = 0 if obs is None else round_now - obs.first_seen_round
        if age < self.params.age_min:
            return "too_young"
        if self.score(node, candidate, round_now) < self.params.score_threshold:
            return "low_score"
        return None

    def accept_peer(self, node: Node, candidate: int, round_now: int) -> bool:
        return self.reason(node, candidate, round_now) is None

    def evict_peer(self, node: Node, round_now: int, candidate: Optional[int] = None) -> Optional[int]:
        if len(node.peers) < self.max_peers:
            return None
        return min(node.peers, key=lambda p: self.score(node, p, round_now))

    def refresh_peers(self, node: Node, round_now: int, rng: random.Random) -> None:
        return None

    def select_gossip_peers(self, node: Node, rng: random.Random) -> List[int]:
        return list(node.peers)

    def choose_gossip_target(self, node: Node, rng: random.Random) -> Optional[int]:
        peers = self.select_gossip_peers(node, rng)
        return rng.choice(peers) if peers else None
