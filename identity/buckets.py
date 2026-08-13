from __future__ import annotations

import hashlib

# 4.4.4. Bucket diverzifikacija 
# Da bi se smanjila mogućnost Eclipse napada, peer set mora biti raspoređen kroz više identity bucket-a. 
# Bucket indeks definiše se kao 𝑏(𝑖𝑑) = 𝑆𝐻𝐴256(𝑖𝑑) 𝑚𝑜𝑑 𝑘, gde je 	𝑘broj bucket-a.  
# Peer Manager ograničava maksimalan broj peer-ova iz istog bucket-a. 
# Time se: 
# • smanjuje koncentracija napadačkih identiteta,  
# • povećava peer diversity,  
# • i otežava potpuna izolacija honest čvora.  
# Bucket diverzifikacija emulira (u kontrolisanom Docker okruženju) IP-prefix, ASN ili geografsku 
# diverzifikaciju. 

def bucket_of(identity: str, num_buckets: int) -> int:
    digest = hashlib.sha256(identity.encode()).digest()
    return int.from_bytes(digest, "big") % num_buckets
