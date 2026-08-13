from __future__ import annotations

from typing import Optional

from core.node import Node
from identity.buckets import bucket_of
from sampling.sybil_resistant import SybilResistantStrategy

# Eclipse-resistant strategija dodatno uvodi bucket diverzifikaciju, čime se ograničava koncentracija peer-ova iz iste identitetske grupe
# 4.5.3. Eclipse-resistant strategija 
# Eclipse-resistant strategija proširuje Sybil-resistant pristup bucket diverzifikacijom. 
# Peer set mora imati približno ravnomernu raspodelu po bucket-ima. Ako je bucket popunjen novi peer može 
# zameniti samo slabiji peer iz istog bucket-a. Ciljevi su sprečavanje koncentracije napadačkih identiteta i 
# povećanje peer diversity metrike. Ova strategija predstavlja glavnu odbranu od Eclipse i peer poisoning 
# napada i delimično ublažava posledice selective forwarding napada kroz veću peer diversity.  

class EclipseResistantStrategy(SybilResistantStrategy):
    name = "eclipse_resistant"

    def bucket(self, identity: int) -> int:
        return bucket_of(str(identity), self.params.num_buckets)

    def reason(self, node: Node, candidate: int, round_now: int) -> Optional[str]:
        base = super().reason(node, candidate, round_now)
        if base is not None:
            return base
        target = self.bucket(candidate)
        occupancy = sum(1 for p in node.peers if self.bucket(p) == target)
        if occupancy >= self.params.max_per_bucket:
            return "bucket_full"
        return None
