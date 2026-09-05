from __future__ import annotations

import random

from core.rng import make_rng
from typing import Dict, List, Optional, Protocol, Set, runtime_checkable

# 5.1.6: svaki napad je nezavisan modul iza zajednickog interfejsa.
# Modul definise trenutak aktivacije, ciljne cvorove, parametre ponasanja
# i tip manipulacije. Scenario ih drzi i poziva redom, cime se napadi mogu
# ukljucivati nezavisno i kombinovati u istom eksperimentu.

FLOOD_BASE = 10_000


def module_rng(ctx, identity: int, round_now: int, purpose: str) -> random.Random:
    # 4.10: svaki izvor randomness-a izvodi se iz globalnog eksperimentalnog seed-a.
    # Ugradjeni hash() se NE koristi jer je nasumican po procesu (PYTHONHASHSEED),
    # pa bi isti eksperiment davao razlicite rezultate izmedju pokretanja.
    return make_rng(ctx.params.experiment_seed, purpose, identity, round_now)


class AttackContext:
    # zajednicki pogled koji svaki modul dobija: ko su ucesnici i koji je parametar
    __slots__ = ("honest_ids", "byzantine_ids", "sybil_ids", "params")

    def __init__(self, honest_ids: Set[int], byzantine_ids: Set[int],
                 sybil_ids: Set[int], params):
        self.honest_ids = honest_ids
        self.byzantine_ids = byzantine_ids
        self.sybil_ids = sybil_ids
        self.params = params

    @property
    def malicious_ids(self) -> Set[int]:
        return self.byzantine_ids | self.sybil_ids

    def targets(self) -> List[int]:
        # ciljni cvorovi: prazna lista znaci da je napad "sirok" (svi cvorovi)
        k = self.params.eclipse_targets
        return sorted(self.honest_ids)[:k] if k > 0 else []


@runtime_checkable
class AttackModule(Protocol):
    name: str

    def enabled(self, ctx: AttackContext) -> bool:
        # da li je napad ukljucen u ovoj konfiguraciji
        ...


class BaseAttack:
    # podrazumevano ponasanje: modul ne dira nijednu fazu runde dok ga
    # konkretna implementacija ne prepise
    name: str = "base"

    def enabled(self, ctx: AttackContext) -> bool:
        return True

    def offer_candidates(self, ctx: AttackContext, node, round_now: int,
                         rng: random.Random, offers: List[int]) -> List[int]:
        # faza discovery: modul moze da doda ili ukloni kandidate
        return offers

    def broadcast_value(self, ctx: AttackContext, identity: int, value: float,
                        round_now: int) -> Optional[float]:
        # faza emitovanja: vrati vrednost ili None ako modul ne menja emisiju
        return None

    def responds(self, ctx: AttackContext, identity: int, round_now: int) -> Optional[bool]:
        # faza heartbeat: vrati False za cutanje ili None ako modul ne odlucuje
        return None

    def before_round(self, ctx: AttackContext, nodes: Dict[int, object],
                     round_now: int) -> None:
        # pre runde: churn i slicne manipulacije stanja
        return None