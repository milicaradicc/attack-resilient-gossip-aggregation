from __future__ import annotations

import random
from typing import Optional

from attacks.base import AttackContext, BaseAttack, module_rng


class ByzantineAttack(BaseAttack):
    name = "byzantine"

    def broadcast_value(self, ctx: AttackContext, identity: int, value: float,
                        round_now: int) -> Optional[float]:
        if identity in ctx.sybil_ids:
            r = module_rng(ctx, identity, round_now, "sybil_value")
            return r.uniform(ctx.params.value_low, ctx.params.value_high)
        if identity not in ctx.byzantine_ids:
            return None
        p = ctx.params
        prof = p.byzantine_profile
        if prof == "extreme":
            return p.x_star + p.extreme_offset
        if prof == "random":
            r = module_rng(ctx, identity, round_now, "byzantine_random")
            return r.uniform(p.random_low, p.random_high)
        if prof == "low_biased":
            return p.x_star + p.low_bias
        return p.coordinated_value