from __future__ import annotations

import hashlib


# 4.4.1. Proof-of-Work validacija 
# Svaki identitet mora posedovati validan proof-of-work. Koristi se 𝑆𝐻𝐴256(𝑖𝑑 ∥ 𝑛𝑜𝑛𝑐𝑒) sa uslovom 
# “određeni broj vodećih nula bita”. Cilj PoW mehanizma nije jaka kriptografska zaštita, već povećanje cene 
# masovne proizvodnje identiteta i usporavanje Sybil flood napada. PoW se proverava prilikom peer 
# admission procesa i peer refresh-a.  


def pow_hash(identity: str, nonce: int) -> bytes:
    return hashlib.sha256(f"{identity}||{nonce}".encode()).digest()


def leading_zero_bits(digest: bytes) -> int:
    bits = 0
    for byte in digest:
        if byte == 0:
            bits += 8
            continue
        for i in range(7, -1, -1):
            if byte & (1 << i):
                return bits
            bits += 1
        break
    return bits


def verify_pow(identity: str, nonce: int, difficulty_bits: int) -> bool:
    return leading_zero_bits(pow_hash(identity, nonce)) >= difficulty_bits


def solve_pow(identity: str, difficulty_bits: int, max_iter: int = 5_000_000) -> int:
    for nonce in range(max_iter):
        if verify_pow(identity, nonce, difficulty_bits):
            return nonce
    raise RuntimeError("pow not found")
