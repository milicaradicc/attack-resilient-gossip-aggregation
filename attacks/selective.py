from __future__ import annotations

import random
from typing import Optional

from attacks.base import AttackContext, BaseAttack

# 3.9: selective forwarding i unresponsive ponasanje.
# Napadac povremeno prosledjuje korektnu vrednost (da izbegne detekciju)
# ili uopste ne odgovara na heartbeat.


class SelectiveForwardingAttack(BaseAttack):
    name = "selective_forwarding"

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.selective_p < 1.0 or ctx.params.unresponsive_p > 0.0

    def broadcast_value(self, ctx: AttackContext, identity: int, value: float,
                        round_now: int) -> Optional[float]:
        p = ctx.params
        if p.selective_p >= 1.0 or identity not in ctx.malicious_ids:
            return None
        r = random.Random(hash((identity, round_now, "sel")))
        # sa verovatnocom (1 - selective_p) napadac emituje korektnu vrednost
        return p.x_star if r.random() > p.selective_p else None

    def responds(self, ctx: AttackContext, identity: int, round_now: int) -> Optional[bool]:
        p = ctx.params
        if p.unresponsive_p <= 0.0 or identity not in ctx.malicious_ids:
            return None
        r = random.Random(hash((identity, round_now, "resp")))
        return r.random() >= p.unresponsive_p