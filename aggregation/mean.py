from __future__ import annotations

from typing import Sequence

# 4.6.1. Mean 
# Aritmetička sredina
# Prednosti su brza konvergencija i jednostavna implementacija.  
# Nedostatak je ekstremna osetljivost na Byzantine outlier-e.  

class MeanAggregation:
    name: str = "mean"

    def aggregate(self, own: float, received: Sequence[float]) -> float:
        vals = [own, *received]
        return sum(vals) / len(vals)