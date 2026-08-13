from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Set

from core.node import Node

FLOOD_BASE = 10_000


@dataclass
class AttackParams:
    byzantine_profile: str = "coordinated"
    coordinated_value: float = 1000.0
    extreme_offset: float = 1000.0
    random_low: float = -1000.0
    random_high: float = 1000.0
    low_bias: float = 5.0
    stale_value: float = 130.0
    x_star: float = 100.0
    activate_round: int = 1
    poison_honest_offers: int = 1
    flooding: int = 0
    churn_period: int = 0
    selective_p: float = 1.0
    unresponsive_p: float = 0.0


@dataclass
class Scenario:
    honest_ids: Set[int]
    byzantine_ids: Set[int]
    sybil_ids: Set[int]
    params: AttackParams = field(default_factory=AttackParams)

    @classmethod
    def benign(cls, honest_ids: Set[int]) -> "Scenario":
        return cls(set(honest_ids), set(), set(),
                   AttackParams(activate_round=10 ** 9, poison_honest_offers=0))

    @property
    def malicious_ids(self) -> Set[int]:
        return self.byzantine_ids | self.sybil_ids

    def active(self, round_now: int) -> bool:
        return round_now >= self.params.activate_round

    def responds(self, identity: int, round_now: int, rng: random.Random) -> bool:
        if not self.active(round_now) or identity not in self.malicious_ids:
            return True
        if self.params.unresponsive_p <= 0.0:
            return True
        r = random.Random(hash((identity, round_now, "resp")))
        return r.random() >= self.params.unresponsive_p

    def broadcast_value(self, identity: int, honest_value: float, round_now: int) -> float:
        if not self.active(round_now) or identity not in self.malicious_ids:
            return honest_value
        p = self.params
        if p.selective_p < 1.0:
            r = random.Random(hash((identity, round_now, "sel")))
            if r.random() > p.selective_p:
                return p.x_star
        prof = p.byzantine_profile
        if prof == "extreme":
            return p.x_star + p.extreme_offset
        if prof == "random":
            r = random.Random(hash((identity, round_now, "rnd")))
            return r.uniform(p.random_low, p.random_high)
        if prof == "low_biased":
            return p.x_star + p.low_bias
        if prof == "stale":
            return p.stale_value
        return p.coordinated_value

    def offer_candidates(self, node: Node, round_now: int, rng: random.Random) -> List[int]:
        if not self.active(round_now):
            return []
        # POISONING!!!!!!!!!!!!!!!!!
        # za svaki honest čvor, u listu kandidata se stave svi napadači (koji već nisu njegove komšije)
        # to modeluje situaciju gde napadač (ili kompromitovan peer) preporučuje druge napadače
        offers = [m for m in sorted(self.malicious_ids) if m not in node.peers]
        # u pravom sistemu čvor bi otkrivao i honest i napadačke kandidate, ne samo napadače
        # ovo je „šum" da poisoning ne bude previše očigledan (da nije samo napadači u ponudi)
        honest_pool = [
            h for h in sorted(self.honest_ids)
            if h != node.node_id and h not in node.peers
        ]
        rng.shuffle(honest_pool)
        offers.extend(honest_pool[: self.params.poison_honest_offers])
        if self.params.flooding > 0: # FLOODING!!!!!!!!!!!!!!!!!
            offers.extend(FLOOD_BASE + i for i in range(self.params.flooding))
        return offers

    def churn_reset(self, nodes: Dict[int, Node], round_now: int) -> None:
        p = self.params
        if p.churn_period <= 0 or round_now == 0 or round_now % p.churn_period != 0:
            return
        for node in nodes.values():
            for mid in self.malicious_ids:
                obs = node.observations.get(mid)
                if obs is not None:
                    obs.first_seen_round = round_now
                    obs.successful_exchanges = 0
