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
        targets = ctx.targets()
        if not targets or node.node_id in targets:
            return offers
        # cvor nije meta: napadacki identiteti mu se ne nude, ostaju samo
        # honest kandidati koje je poisoning dodao kao "sum"
        return [o for o in offers if o not in ctx.malicious_ids]