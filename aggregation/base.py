from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class AggregationStrategy(Protocol):
    name: str

    def aggregate(self, own: float, received: Sequence[float]) -> float:
        ...