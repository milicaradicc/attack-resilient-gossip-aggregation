from __future__ import annotations

import hashlib
import random

# 5.1.3. Deterministička seed propagacija 
# Jedan od glavnih zahteva rada jeste potpuna reproduktivnost eksperimenata. Zbog toga svi izvori 
# randomness-a koriste determinističku seed propagaciju. 
# Globalni eksperimentalni seed koristi se za generisanje: 
# • peer selection seed-ova,  
# • Byzantine vrednosti,  
# • Sybil identiteta,  
# • inicijalnih lokalnih metrika,  
# • timing parametara napada,  
# • i drugih pseudo-slučajnih događaja.  
# Za svaki podsistem seed se izvodi kroz: 
# �
# �𝑒𝑒𝑑
# = 𝑆𝐻𝐴256(𝑐𝑜𝑚𝑝𝑜𝑛𝑒𝑛𝑡_𝑛𝑎𝑚𝑒 ∥ 𝑒𝑥𝑝_𝑠𝑒𝑒𝑑) 
# Na ovaj način isti eksperiment proizvodi identičan trace, moguće je ponoviti eksperimente i rezultati postaju 
# proverljivi.  
# Bez determinističke randomizacije male razlike u peer selection procesu ili rasporedu poruka mogle bi 
# dovesti do različitih rezultata između pokretanja.  
# Deterministička reproduktivnost posebno je važna za poređenje overlay strategija, statističku obradu 
# rezultata i naučnu validnost evaluacije. 

def derive_seed(global_seed: int, *parts: object) -> int:
    h = hashlib.sha256()
    h.update(str(global_seed).encode())
    for p in parts:
        h.update(b"|")
        h.update(str(p).encode())
    return int.from_bytes(h.digest()[:8], "big")


def make_rng(global_seed: int, *parts: object) -> random.Random:
    return random.Random(derive_seed(global_seed, *parts))
