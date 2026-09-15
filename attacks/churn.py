from __future__ import annotations

from typing import Dict, List, Optional

from attacks.base import NO_MESSAGE, AttackContext, BaseAttack, module_rng
from metrics.event_trace import CHURN_LEAVE


class ChurnAttack(BaseAttack):
    name = "churn"

    def enabled(self, ctx: AttackContext) -> bool:
        return ctx.params.churn_period > 0

    def cycle(self, ctx: AttackContext, identity: int) -> tuple:
        p = ctx.params
        if identity not in ctx.malicious_ids or p.churn_period <= 0:
            return 0, 0
        return p.churn_period, max(1, min(p.churn_offline, p.churn_period - 1))

    def phase(self, ctx: AttackContext, identity: int) -> int:
        period, _ = self.cycle(ctx, identity)
        if period <= 0:
            return 0
        return module_rng(ctx, identity, 0, "churn_phase").randrange(period)

    def offline(self, ctx: AttackContext, identity: int, round_now: int) -> bool:
        period, absent = self.cycle(ctx, identity)
        if period <= 0 or round_now <= 0:
            return False
        return ((round_now + self.phase(ctx, identity)) % period) < absent

    def returning(self, ctx: AttackContext, identity: int, round_now: int) -> bool:
        period, absent = self.cycle(ctx, identity)
        if period <= 0 or round_now <= 0:
            return False
        return ((round_now + self.phase(ctx, identity)) % period) == absent

    def returning_ids(self, ctx: AttackContext, round_now: int) -> List[int]:
        return [i for i in sorted(ctx.malicious_ids)
                if self.returning(ctx, i, round_now)]

    def offline_ids(self, ctx: AttackContext, round_now: int) -> List[int]:
        return [i for i in sorted(ctx.malicious_ids)
                if self.offline(ctx, i, round_now)]

    def responds(self, ctx: AttackContext, identity: int, round_now: int,
                 target: Optional[int] = None) -> Optional[bool]:
        if identity not in ctx.malicious_ids:
            return None
        return False if self.offline(ctx, identity, round_now) else None

    def broadcast_value(self, ctx: AttackContext, identity: int, value: float,
                        round_now: int) -> Optional[float]:
        if identity not in ctx.malicious_ids:
            return None
        return NO_MESSAGE if self.offline(ctx, identity, round_now) else None

    def before_round(self, ctx: AttackContext, nodes: Dict[int, object],
                     round_now: int, trace=None) -> None:
        away = self.offline_ids(ctx, round_now)
        for node in nodes.values():
            for mid in away:
                if mid in node.peers:
                    node.peers.remove(mid)
                    if trace is not None:
                        trace.evict(round_now, node.node_id, mid, CHURN_LEAVE, None)

        returners = self.returning_ids(ctx, round_now)
        if not returners:
            return
        for node in nodes.values():
            for mid in returners:
                obs = node.observations.get(mid)
                if obs is not None:
                    obs.first_seen_round = round_now
                    obs.successful_exchanges = 0
                    obs.missed_heartbeats = 0
                    obs.missed_total = 0