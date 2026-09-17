from __future__ import annotations

import random

from core.rng import make_rng
from typing import Dict, List, Optional, Protocol, Set, runtime_checkable


FLOOD_BASE = 10_000
NO_MESSAGE = object()


def module_rng(ctx, identity: int, round_now: int, purpose: str) -> random.Random:
    return make_rng(ctx.params.experiment_seed, purpose, identity, round_now)


class AttackContext:
    __slots__ = ("honest_ids", "byzantine_ids", "sybil_ids", "params",
                 "attacker_nodes", "all_sybil_ids", "nonces", "pow_difficulty_bits")

    def __init__(self, honest_ids: Set[int], byzantine_ids: Set[int],
                 sybil_ids: Set[int], params, attacker_nodes: Dict[int, object] = None,
                 all_sybil_ids: Set[int] = None, nonces: Dict[int, int] = None,
                 pow_difficulty_bits: int = 0):
        self.honest_ids = honest_ids
        self.byzantine_ids = byzantine_ids
        self.sybil_ids = sybil_ids
        self.all_sybil_ids = all_sybil_ids if all_sybil_ids is not None else sybil_ids
        self.nonces = nonces if nonces is not None else {}
        self.pow_difficulty_bits = pow_difficulty_bits
        self.params = params
        self.attacker_nodes = attacker_nodes if attacker_nodes is not None else {}

    def attacker_view(self, identity: int) -> Optional[float]:
        node = self.attacker_nodes.get(identity)
        return None if node is None else node.estimate

    @property
    def malicious_ids(self) -> Set[int]:
        return self.byzantine_ids | self.sybil_ids

    def targets(self) -> List[int]:
        k = self.params.eclipse_targets
        if k <= 0:
            return []
        honest = sorted(self.honest_ids)
        if 0 < k < 1:
            count = max(1, int(round(k * len(honest))))
        else:
            count = min(int(k), len(honest))
        rng = make_rng(self.params.experiment_seed, "eclipse_targets")
        return sorted(rng.sample(honest, count))


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

    def sends_value_to(self, ctx: AttackContext, identity: int, target: int,
                       round_now: int) -> Optional[bool]:
        return None

    def before_round(self, ctx: AttackContext, nodes: Dict[int, object],
                     round_now: int, trace=None) -> None:
        return None