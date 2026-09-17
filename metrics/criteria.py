from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

BETA_MAX = 0.30


@dataclass(frozen=True)
class Criterion:
    key: str     # polje u redu sazetka
    label: str   # naziv u izvestaju
    limit: float # gornja granica
    spec: str    # oznaka kriterijuma u specifikaciji


CRITERIA = (
    Criterion("final_sybil_penetration", "Sybil penetracija", 0.20, "3.10.1"),
    Criterion("final_eclipse_rate", "Eclipse success rate", 0.10, "3.10.2"),
    Criterion("final_err_rel", "relativna greska agregacije", 0.05, "3.10.3"),
    Criterion("stability", "stabilnost procene", 0.01, "3.10.4"),
    Criterion("convergence_time", "vreme konvergencije", 20, "3.10.5"),
)


def evaluate_row(row: Dict) -> Dict[str, Optional[bool]]:
    # ocena jednog pokretanja: {oznaka kriterijuma: True/False/None}.
    # None znaci da kriterijum nije primenljiv (polje nedostaje u redu).
    #
    # Vreme konvergencije:-1 znaci da sistem nikada nije trajno dostigao prag
    ocene = {}
    for c in CRITERIA:
        v = row.get(c.key)
        if not isinstance(v, (int, float)):
            ocene[c.spec] = None
        elif c.key == "convergence_time" and v < 0:
            ocene[c.spec] = False
        else:
            ocene[c.spec] = v <= c.limit
    return ocene


def applicable(rows: List[Dict]) -> List[Dict]:
    # kriterijumi iz 3.10 vaze za beta <= 0.30; ostali redovi se izostavljaju
    return [r for r in rows if isinstance(r.get("beta"), (int, float))
            and r["beta"] <= BETA_MAX]


def summarize(rows: List[Dict]) -> Dict[str, Dict[str, int]]:
    # koliko pokretanja zadovoljava svaki kriterijum
    ukupno = {c.spec: {"prolaz": 0, "pad": 0} for c in CRITERIA}
    for row in applicable(rows):
        for spec, ok in evaluate_row(row).items():
            if ok is True:
                ukupno[spec]["prolaz"] += 1
            elif ok is False:
                ukupno[spec]["pad"] += 1
    return ukupno


def failures(rows: List[Dict]) -> List[Dict]:
    # pokretanja koja obaraju bar jedan kriterijum, sa spiskom palih
    lose = []
    for row in applicable(rows):
        pali = [spec for spec, ok in evaluate_row(row).items() if ok is False]
        if pali:
            lose.append({"row": row, "failed": pali})
    return lose