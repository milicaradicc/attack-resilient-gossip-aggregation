from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class AggregationStrategy(Protocol):
    name: str

    def aggregate(self, own: float, received: Sequence[float]) -> float: ...


class MeanAggregation:
    name = "mean"

    def aggregate(self, own: float, received: Sequence[float]) -> float:
        vals = [own, *received]
        return sum(vals) / len(vals)
