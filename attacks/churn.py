from __future__ import annotations

from typing import Dict

from attacks.base import AttackContext, BaseAttack

# 3.8: churn — napadac periodicno "obnavlja" identitete kako bi izbegao
# reputaciju. U kombinaciji sa age-gating politikom to podize cenu napada,
# jer resetovan identitet ponovo ne zadovoljava minimalnu starost.


class ChurnAttack(BaseAttack):
    name = "churn"

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.churn_period > 0

    def before_round(self, ctx: AttackContext, nodes: Dict[int, object],
                     round_now: int) -> None:
        period = ctx.params.churn_period
        if period <= 0 or round_now == 0 or round_now % period != 0:
            return
        for node in nodes.values():
            for mid in ctx.malicious_ids:
                obs = node.observations.get(mid)
                if obs is not None:
                    obs.first_seen_round = round_now
                    obs.successful_exchanges = 0