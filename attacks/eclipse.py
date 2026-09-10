from __future__ import annotations

import random
from typing import List

from attacks.base import AttackContext, BaseAttack


class EclipseAttack(BaseAttack):
    name = "eclipse"

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.eclipse_targets > 0

    def offer_candidates(self, ctx: AttackContext, node, round_now: int,
                         rng: random.Random, offers: List[int]) -> List[int]:
        if node.node_id not in ctx.targets():
            return offers
        # zrtvi se nude samo napadacki identiteti: honest kandidati bi joj
        # popunili mesto koje napadac cilja, pa se iz ponude izostavljaju
        return [o for o in offers if o in ctx.malicious_ids]