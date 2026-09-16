from __future__ import annotations

from typing import Optional

from attacks.base import AttackContext, BaseAttack, module_rng


class SelectiveForwardingAttack(BaseAttack):
    name = "selective_forwarding"

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.selective_p < 1.0 or ctx.params.unresponsive_p > 0.0

    def sends_value_to(self, ctx: AttackContext, identity: int, target: int,
                       round_now: int) -> Optional[bool]:
        p = ctx.params
        if p.selective_p >= 1.0 or identity not in ctx.malicious_ids:
            return None
        r = module_rng(ctx, identity, round_now, f"selective_{target}")
        return r.random() <= p.selective_p

    def responds(self, ctx: AttackContext, identity: int, round_now: int,
                 target: Optional[int] = None) -> Optional[bool]:
        p = ctx.params
        if p.unresponsive_p <= 0.0 or identity not in ctx.malicious_ids:
            return None
        r = module_rng(ctx, identity, round_now, "unresponsive")
        return False if r.random() < p.unresponsive_p else None