from __future__ import annotations

import random

from core.rng import make_rng
from typing import Dict, List, Optional, Protocol, Set, runtime_checkable


FLOOD_BASE = 10_000
NO_MESSAGE = object()


def module_rng(ctx, identity: int, round_now: int, purpose: str) -> random.Random:
    return make_rng(ctx.params.experiment_seed, purpose, identity, round_now)


class AttackContext:
    __slots__ = ("honest_ids", "byzantine_ids", "sybil_ids", "params")

    def __init__(self, honest_ids: Set[int], byzantine_ids: Set[int],
                 sybil_ids: Set[int], params):
        self.honest_ids = honest_ids
        self.byzantine_ids = byzantine_ids
        self.sybil_ids = sybil_ids
        self.params = params

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

    def responds(self, ctx: AttackContext, identity: int, round_now: int) -> Optional[bool]:
        return None

    def before_round(self, ctx: AttackContext, nodes: Dict[int, object],
                     round_now: int, trace=None) -> None:
        return None