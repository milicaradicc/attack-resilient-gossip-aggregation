from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Set

from attacks.base import FLOOD_BASE, NO_MESSAGE, AttackContext
from attacks.byzantine import ByzantineAttack
from attacks.churn import ChurnAttack
from attacks.delay import DelayAttack
from attacks.eclipse import EclipseAttack
from attacks.flooding import PeerFloodingAttack
from attacks.partitioning import PartitioningAttack
from attacks.poisoning import PeerPoisoningAttack
from attacks.selective import SelectiveForwardingAttack
from core.node import Node


@dataclass
class AttackParams:
    byzantine_profile: str = "coordinated"
    coordinated_value: float = 1000.0
    extreme_offset: float = 1000.0
    random_low: float = -1000.0
    random_high: float = 1000.0
    low_bias: float = 5.0
    x_star: float = 100.0
    value_low: float = 50.0
    value_high: float = 150.0
    experiment_seed: int = 0
    activate_round: int = 1
    discovery_offers: int = 2 
    flooding: int = 0
    churn_period: int = 0
    churn_offline: int = 1 
    selective_p: float = 1.0
    unresponsive_p: float = 0.0
    delay_rounds: int = 0 
    eclipse_targets: int = 0 
    partition_groups: int = 0


def default_modules() -> tuple:
    return (
        ChurnAttack(),
        PeerPoisoningAttack(),
        EclipseAttack(),      
        PeerFloodingAttack(),
        PartitioningAttack(),
        DelayAttack(),        
        SelectiveForwardingAttack(),
        ByzantineAttack(),
    )


@dataclass
class Scenario:
    honest_ids: Set[int]
    byzantine_ids: Set[int]
    sybil_ids: Set[int]
    params: AttackParams = field(default_factory=AttackParams)
    modules: tuple = field(default_factory=default_modules)
    attacker_nodes: Dict[int, Node] = field(default_factory=dict)

    @classmethod
    def benign(cls, honest_ids: Set[int]) -> "Scenario":
        return cls(set(honest_ids), set(), set(),
                   AttackParams(activate_round=10 ** 9))

    @property
    def malicious_ids(self) -> Set[int]:
        return self.byzantine_ids | self.sybil_ids

    @property
    def ctx(self) -> AttackContext:
        return AttackContext(self.honest_ids, self.byzantine_ids, self.sybil_ids,
                             self.params, self.attacker_nodes)

    def active_modules(self) -> List:
        ctx = self.ctx
        return [m for m in self.modules if m.enabled(ctx)]

    def active(self, round_now: int) -> bool:
        return round_now >= self.params.activate_round

    def targets(self) -> List[int]:
        return self.ctx.targets()

    def _churn(self):
        for module in self.modules:
            if getattr(module, "name", "") == "churn":
                return module
        return None

    def offline_ids(self, round_now: int) -> Set[int]:
        module = self._churn()
        if module is None or not module.enabled(self.ctx) or not self.active(round_now):
            return set()
        return set(module.offline_ids(self.ctx, round_now))

    def returning_count(self, round_now: int) -> int:
        module = self._churn()
        if module is None or not module.enabled(self.ctx) or not self.active(round_now):
            return 0
        return len(module.returning_ids(self.ctx, round_now))

    def responds(self, identity: int, round_now: int, rng: random.Random,
                 target: int = None) -> bool:
        if identity >= FLOOD_BASE:
            return False
        if not self.active(round_now) or identity not in self.malicious_ids:
            return True
        ctx = self.ctx
        for module in self.active_modules():
            decision = module.responds(ctx, identity, round_now, target)
            if decision is not None:
                return decision
        return True

    def broadcast_value(self, identity: int, honest_value: float, round_now: int) -> float:
        if not self.active(round_now) or identity not in self.malicious_ids:
            return honest_value
        ctx = self.ctx
        for module in self.active_modules():
            value = module.broadcast_value(ctx, identity, honest_value, round_now)
            if value is not None:
                return value
        return honest_value

    def offer_candidates(self, node: Node, round_now: int, rng: random.Random) -> List[int]:
        ctx = self.ctx
        offers = self._discovery(node, rng)
        if not self.active(round_now):
            return offers
        for module in self.active_modules():
            offers = module.offer_candidates(ctx, node, round_now, rng, offers)
        away = self.offline_ids(round_now)
        if away:
            offers = [c for c in offers if c not in away]
        rng.shuffle(offers)
        return offers

    def _discovery(self, node: Node, rng: random.Random) -> List[int]:
        count = self.params.discovery_offers
        if count <= 0:
            return []
        pool = [h for h in sorted(self.honest_ids)
                if h != node.node_id and h not in node.peers]
        rng.shuffle(pool)
        return pool[:count]

    def before_round(self, nodes: Dict[int, Node], round_now: int, trace=None) -> None:
        if not self.active(round_now):
            return
        ctx = self.ctx
        for module in self.active_modules():
            module.before_round(ctx, nodes, round_now, trace=trace)