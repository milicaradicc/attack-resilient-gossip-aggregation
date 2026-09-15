from __future__ import annotations

import random

from core.rng import make_rng
from typing import Dict, List, Optional, Protocol, Set, runtime_checkable


FLOOD_BASE = 10_000
NO_MESSAGE = object()


def module_rng(ctx, identity: int, round_now: int, purpose: str) -> random.Random:
    return make_rng(ctx.params.experiment_seed, purpose, identity, round_now)


class AttackContext:
    __slots__ = ("honest_ids", "byzantine_ids", "sybil_ids", "params", "attacker_nodes")

    def __init__(self, honest_ids: Set[int], byzantine_ids: Set[int],
                 sybil_ids: Set[int], params, attacker_nodes: Dict[int, object] = None):
        self.honest_ids = honest_ids
        self.byzantine_ids = byzantine_ids
        self.sybil_ids = sybil_ids
        self.params = params
        self.attacker_nodes = attacker_nodes if attacker_nodes is not None else {}

    def attacker_view(self, identity: int) -> Optional[float]:
        # trenutna procena koju napadacki cvor drzi (ono sto je stvarno cuo od
        # honest suseda) — koristi je delay napad za pravi stale information
        node = self.attacker_nodes.get(identity)
        return None if node is None else node.estimate

    @property
    def malicious_ids(self) -> Set[int]:
        return self.byzantine_ids | self.sybil_ids

    def targets(self) -> List[int]:
        k = self.params.eclipse_targets
        return sorted(self.honest_ids)[:k] if k > 0 else []


@runtime_checkable
class AttackModule(Protocol):
    name: str

    def enabled(self, ctx: AttackContext) -> bool:
        ...


class BaseAttack:
    name: str = "base"

    def enabled(self, ctx: AttackContext) -> bool:
        return True

    def offer_candidates(self, ctx: AttackContext, node, round_now: int,
                         rng: random.Random, offers: List[int]) -> List[int]:
        return offers

    def broadcast_value(self, ctx: AttackContext, identity: int, value: float,
                        round_now: int) -> Optional[float]:
        return None

    def responds(self, ctx: AttackContext, identity: int, round_now: int,
                 target: Optional[int] = None) -> Optional[bool]:
        return None

    def before_round(self, ctx: AttackContext, nodes: Dict[int, object],
                     round_now: int, trace=None) -> None:
        return None