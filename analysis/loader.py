from __future__ import annotations

import csv
from statistics import mean, pstdev
from typing import Dict, List, Tuple


def load(path: str) -> List[Dict]:
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            try:
                r[k] = int(v)
            except (ValueError, TypeError):
                try:
                    r[k] = float(v)
                except (ValueError, TypeError):
                    pass
    return rows


def group_stats(rows: List[Dict], by: Tuple[str, ...], value: str) -> Dict[Tuple, Tuple[float, float]]:
    groups: Dict[Tuple, List[float]] = {}
    for r in rows:
        key = tuple(r[k] for k in by)
        groups.setdefault(key, []).append(r[value])
    return {k: (mean(v), pstdev(v)) for k, v in groups.items()}


def group_values(rows: List[Dict], by: Tuple[str, ...], value: str) -> Dict[Tuple, List[float]]:
    groups: Dict[Tuple, List[float]] = {}
    for r in rows:
        key = tuple(r[k] for k in by)
        groups.setdefault(key, []).append(r[value])
    return groups


def filter_rows(rows: List[Dict], **eq) -> List[Dict]:
    out = rows
    for k, v in eq.items():
        out = [r for r in out if r[k] == v]
    return out
