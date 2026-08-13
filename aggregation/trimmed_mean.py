from __future__ import annotations

from typing import Sequence

# 4.6.3. Trimmed Mean 
# Trimmed mean: 
# 1. sortira vrednosti,  
# 2. uklanja 𝑘najmanjih i 𝑘najvećih,  
# 3. računa sredinu nad ostatkom.  

# Predstavlja kompromis između mean i median pristupa.  

# Cilj je otpornost na Byzantine vrednosti uz očuvanje relativno dobre konvergencije.  

class TrimmedMeanAggregation:
    name = "trimmed_mean"

    def __init__(self, alpha: float = 0.2):
        self.alpha = alpha

    def aggregate(self, own: float, received: Sequence[float]) -> float:
        vals = sorted([own, *received])
        n = len(vals)
        k = min(int(self.alpha * n), (n - 1) // 2)
        kept = vals[k:n - k] if k > 0 else vals
        return sum(kept) / len(kept)
