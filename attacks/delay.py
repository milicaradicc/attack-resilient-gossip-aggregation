from __future__ import annotations

from typing import Dict, Optional

from attacks.base import NO_MESSAGE, AttackContext, BaseAttack
from attacks.byzantine import ByzantineAttack


class DelayAttack(BaseAttack):
    name = "delay"

    def __init__(self):
        self.queue: Dict[int, Dict[int, float]] = {}
        self._profil = ByzantineAttack()

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.delay_rounds > 0

    def broadcast_value(self, ctx: AttackContext, identity: int, value: float,
                        round_now: int) -> Optional[float]:
        if ctx.params.delay_rounds <= 0 or identity not in ctx.malicious_ids:
            return None

        due = self.queue.get(round_now, {})
        held = due.pop(identity, None)
        if not due:
            self.queue.pop(round_now, None)

        # tekuca vrednost se odlaze za kasnije
        delivery = round_now + ctx.params.delay_rounds
        now = self._profil.broadcast_value(ctx, identity, value, round_now)
        self.queue.setdefault(delivery, {})[identity] = now

        # dok nista nije dospelo, cvor od ovog suseda ne dobija poruku
        return held if held is not None else NO_MESSAGE