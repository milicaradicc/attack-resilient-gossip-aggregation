from __future__ import annotations

import random
from typing import List

from attacks.base import AttackContext, BaseAttack


class PeerPoisoningAttack(BaseAttack):
    name = "peer_poisoning"

    def offer_candidates(self, ctx: AttackContext, node, round_now: int,
                         rng: random.Random, offers: List[int]) -> List[int]:
        targets = ctx.targets()
        if targets and node.node_id not in targets:
            malicious = []
        else:
            malicious = [m for m in sorted(ctx.malicious_ids) if m not in node.peers]
        # honest kandidati kao "sum", da ponuda ne bude ocigledno zlonamerna
        honest_pool = [h for h in sorted(ctx.honest_ids)
                       if h != node.node_id and h not in node.peers]
        rng.shuffle(honest_pool)
        return offers + malicious + honest_pool[: ctx.params.poison_honest_offers]