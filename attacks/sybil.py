from __future__ import annotations

from typing import Dict, List

from attacks.base import AttackContext, BaseAttack
from identity.pow import solve_pow


class SybilAttack(BaseAttack):
    name = "sybil"

    def __init__(self):
        # {identitet: runda u kojoj je resen njegov PoW}
        self.created: Dict[int, int] = {}

    def enabled(self, ctx: AttackContext) -> bool:
        return bool(ctx.all_sybil_ids)

    def _due(self, ctx: AttackContext, round_now: int) -> List[int]:
        rate = ctx.params.sybil_rate
        redosled = sorted(ctx.all_sybil_ids)
        if rate <= 0:
            return redosled
        proteklo = round_now - ctx.params.activate_round
        if proteklo < 0:
            return []
        return redosled[:int(proteklo * rate) + 1]

    def before_round(self, ctx: AttackContext, nodes, round_now: int, trace=None) -> None:
        for identity in self._due(ctx, round_now):
            if identity in ctx.nonces:
                continue
            ctx.nonces[identity] = solve_pow(str(identity), ctx.pow_difficulty_bits)
            self.created[identity] = round_now