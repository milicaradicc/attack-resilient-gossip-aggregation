from __future__ import annotations

from typing import Dict, Optional

from attacks.base import NO_MESSAGE, AttackContext, BaseAttack


class DelayAttack(BaseAttack):
    name = "delay"

    def __init__(self):
        self.history: Dict[int, Dict[int, float]] = {}

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.delay_rounds > 0

    def broadcast_value(self, ctx: AttackContext, identity: int, value: float,
                        round_now: int) -> Optional[float]:
        p = ctx.params
        if p.delay_rounds <= 0 or identity not in ctx.malicious_ids:
            return None

        current = ctx.attacker_view(identity)
        log = self.history.setdefault(identity, {})
        if current is not None:
            log[round_now] = current

        stale_round = round_now - p.delay_rounds
        if stale_round in log:
            return log[stale_round]
        return NO_MESSAGE