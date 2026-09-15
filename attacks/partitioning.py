from __future__ import annotations

import random
from typing import List, Optional

from attacks.base import AttackContext, BaseAttack


def group_of(identity: int, num_groups: int) -> int:
    return identity % num_groups if num_groups > 0 else 0


class PartitioningAttack(BaseAttack):
    name = "partitioning"

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.partition_groups > 1

    def responds(self, ctx: AttackContext, identity: int, round_now: int,
                 target: Optional[int] = None) -> Optional[bool]:
        p = ctx.params
        if p.partition_groups <= 1 or identity not in ctx.malicious_ids:
            return None
        if target is None:
            return None
        if group_of(identity, p.partition_groups) != group_of(target, p.partition_groups):
            return False
        return None

    def offer_candidates(self, ctx: AttackContext, node, round_now: int,
                         rng: random.Random, offers: List[int]) -> List[int]:
        p = ctx.params
        if p.partition_groups <= 1:
            return offers
        mine = group_of(node.node_id, p.partition_groups)
        same = [o for o in offers if group_of(o, p.partition_groups) == mine]
        return same if same else offers