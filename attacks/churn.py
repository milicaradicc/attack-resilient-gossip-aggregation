from __future__ import annotations

from typing import Dict, Optional

from attacks.base import NO_MESSAGE, AttackContext, BaseAttack


class ChurnAttack(BaseAttack):
    name = "churn"

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.churn_period > 0

    def _offline(self, ctx: AttackContext, round_now: int) -> bool:
        # ciklus duzine churn_period: prvih churn_offline rundi napadac je odsutan
        period = ctx.params.churn_period
        if period <= 0 or round_now == 0:
            return False
        return (round_now % period) < ctx.params.churn_offline

    def responds(self, ctx: AttackContext, identity: int, round_now: int) -> Optional[bool]:
        if identity not in ctx.malicious_ids:
            return None
        return False if self._offline(ctx, round_now) else None

    def broadcast_value(self, ctx: AttackContext, identity: int, value: float,
                        round_now: int) -> Optional[float]:
        if identity not in ctx.malicious_ids:
            return None
        return NO_MESSAGE if self._offline(ctx, round_now) else None

    def before_round(self, ctx: AttackContext, nodes: Dict[int, object],
                     round_now: int) -> None:
        # trenutak povratka: dnevnik se brise, identitet krece kao nov
        period = ctx.params.churn_period
        if period <= 0 or round_now == 0:
            return
        if (round_now % period) != ctx.params.churn_offline:
            return
        for node in nodes.values():
            for mid in sorted(ctx.malicious_ids):
                obs = node.observations.get(mid)
                if obs is not None:
                    obs.first_seen_round = round_now
                    obs.successful_exchanges = 0
                    obs.missed_heartbeats = 0
                    obs.missed_total = 0