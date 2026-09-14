from __future__ import annotations

import random
from typing import Optional

from attacks.base import AttackContext, BaseAttack, module_rng
from attacks.base import NO_MESSAGE

class SelectiveForwardingAttack(BaseAttack):
    name = "selective_forwarding"

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.selective_p < 1.0 or ctx.params.unresponsive_p > 0.0

    def broadcast_value(self, ctx: AttackContext, identity: int, value: float,
                        round_now: int) -> Optional[float]:
        p = ctx.params
        if p.selective_p >= 1.0 or identity not in ctx.malicious_ids:
            return None
        r = module_rng(ctx, identity, round_now, "selective")
        return None if r.random() > p.selective_p else NO_MESSAGE

    def responds(self, ctx: AttackContext, identity: int, round_now: int) -> Optional[bool]:
        p = ctx.params
        if p.unresponsive_p <= 0.0 or identity not in ctx.malicious_ids:
            return None
        r = module_rng(ctx, identity, round_now, "unresponsive")
        return r.random() >= p.unresponsive_p