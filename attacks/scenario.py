from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Set

from attacks.base import FLOOD_BASE, AttackContext
from attacks.byzantine import ByzantineAttack
from attacks.churn import ChurnAttack
from attacks.flooding import PeerFloodingAttack
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
    stale_value: float = 130.0
    x_star: float = 100.0
    activate_round: int = 1
    poison_honest_offers: int = 1
    flooding: int = 0
    churn_period: int = 0
    selective_p: float = 1.0
    unresponsive_p: float = 0.0
    eclipse_targets: int = 0 # 0 = napad je „širok" (svi cvorovi); >0 = ciljani Eclipse na N zrtava


# 5.1.6: redosled modula je fiksan zbog determinizma — poisoning pre flooding-a,
# selective pre byzantine (jer selektivno cutanje ima prednost nad profilom).
DEFAULT_MODULES = (
    ChurnAttack(),
    PeerPoisoningAttack(),
    PeerFloodingAttack(),
    SelectiveForwardingAttack(),
    ByzantineAttack(),
)


@dataclass
class Scenario:
    # Scenario je koordinator: drzi ucesnike i parametre, a same napade
    # izvrsavaju nezavisni moduli (attacks/*.py) iza zajednickog interfejsa
    honest_ids: Set[int]
    byzantine_ids: Set[int]
    sybil_ids: Set[int]
    params: AttackParams = field(default_factory=AttackParams)
    modules: tuple = DEFAULT_MODULES

    @classmethod
    def benign(cls, honest_ids: Set[int]) -> "Scenario":
        return cls(set(honest_ids), set(), set(),
                   AttackParams(activate_round=10 ** 9, poison_honest_offers=0))

    @property
    def malicious_ids(self) -> Set[int]:
        return self.byzantine_ids | self.sybil_ids

    @property
    def ctx(self) -> AttackContext:
        return AttackContext(self.honest_ids, self.byzantine_ids, self.sybil_ids, self.params)

    def active_modules(self) -> List:
        # nezavisno ukljucivanje: modul ucestvuje samo ako je ukljucen parametrima
        ctx = self.ctx
        return [m for m in self.modules if m.enabled(ctx)]

    def active(self, round_now: int) -> bool:
        return round_now >= self.params.activate_round

    def targets(self) -> List[int]:
        return self.ctx.targets()

    def responds(self, identity: int, round_now: int, rng: random.Random) -> bool:
        if not self.active(round_now) or identity not in self.malicious_ids:
            return True
        ctx = self.ctx
        for module in self.active_modules():
            decision = module.responds(ctx, identity, round_now)
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
        if not self.active(round_now):
            return []
        ctx = self.ctx
        offers: List[int] = []
        for module in self.active_modules():
            offers = module.offer_candidates(ctx, node, round_now, rng, offers)
        return offers

    def churn_reset(self, nodes: Dict[int, Node], round_now: int) -> None:
        ctx = self.ctx
        for module in self.active_modules():
            module.before_round(ctx, nodes, round_now)