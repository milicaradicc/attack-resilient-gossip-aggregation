from __future__ import annotations

import random
from typing import List

from attacks.base import FLOOD_BASE, AttackContext, BaseAttack

# 3.8: peer flooding — masovno reklamiranje neregistrovanih identiteta.
# Cilj nije ulazak u peer set (kandidati nemaju validan PoW) nego opterecenje
# admission mehanizma i porast kontrolnog overhead-a.


class PeerFloodingAttack(BaseAttack):
    name = "peer_flooding"

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.flooding > 0

    def offer_candidates(self, ctx: AttackContext, node, round_now: int,
                         rng: random.Random, offers: List[int]) -> List[int]:
        if ctx.params.flooding <= 0:
            return offers
        return offers + [FLOOD_BASE + i for i in range(ctx.params.flooding)]