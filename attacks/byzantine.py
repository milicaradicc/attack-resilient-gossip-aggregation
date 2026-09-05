from __future__ import annotations

import random
from typing import Optional

from attacks.base import AttackContext, BaseAttack

# 3.7: Byzantine cvorovi salju proizvoljne ili koordinisane agregacione vrednosti.
# Tip manipulacije bira se profilom: coordinated (glavni), extreme, random,
# low_biased i stale (delay, tj. zastarela vrednost).


class ByzantineAttack(BaseAttack):
    name = "byzantine"

    def broadcast_value(self, ctx: AttackContext, identity: int, value: float,
                        round_now: int) -> Optional[float]:
        if identity not in ctx.malicious_ids:
            return None
        p = ctx.params
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