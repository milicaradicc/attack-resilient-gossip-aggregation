from __future__ import annotations

import random
from typing import List

from attacks.base import AttackContext, BaseAttack


class PeerPoisoningAttack(BaseAttack):
    name = "peer_poisoning"

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.poisoning

    def offer_candidates(self, ctx: AttackContext, node, round_now: int,
                         rng: random.Random, offers: List[int]) -> List[int]:
        malicious = [m for m in sorted(ctx.malicious_ids) if m not in node.peers]
        return offers + malicious