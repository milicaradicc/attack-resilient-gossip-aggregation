from __future__ import annotations

from statistics import median
from typing import Sequence

# 4.6.2. Median 
# Medijana koristi centralni element sortiranog skupa. 
# Prednost je otpornost na ekstremne vrednosti.  
# Nedostaci su sporija stabilizacija i manja osetljivost na fine promene.  

class MedianAggregation:
    name = "median"

    def aggregate(self, own: float, received: Sequence[float]) -> float:
        return float(median([own, *received]))
