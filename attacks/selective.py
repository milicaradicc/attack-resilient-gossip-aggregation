from __future__ import annotations

import random
from typing import Optional

from attacks.base import AttackContext, BaseAttack, module_rng
from attacks.base import NO_MESSAGE

class SelectiveForwardingAttack(BaseAttack):
    name = "selective_forwarding"

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.selective_p < 1.0 or ctx.params.unresponsive_p > 0.0

    def responds(self, ctx: AttackContext, identity: int, round_now: int,
                 target: Optional[int] = None) -> Optional[bool]:
        p = ctx.params
        if identity not in ctx.malicious_ids:
            return None
        if p.selective_p < 1.0 and target is not None:
            r = module_rng(ctx, identity, round_now, f"selective_{target}")
            if r.random() > p.selective_p:
                return False
        if p.unresponsive_p > 0.0:
            r = module_rng(ctx, identity, round_now, "unresponsive")
            if r.random() < p.unresponsive_p:
                return False
        return None