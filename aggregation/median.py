from __future__ import annotations

from statistics import median
from typing import Sequence


class MedianAggregation:
    name = "median"

    def aggregate(self, own: float, received: Sequence[float]) -> float:
        return float(median([own, *received]))
