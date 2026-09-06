from __future__ import annotations

from typing import Sequence


class MeanAggregation:
    name: str = "mean"

    def aggregate(self, own: float, received: Sequence[float]) -> float:
        vals = [own, *received]
        return sum(vals) / len(vals)