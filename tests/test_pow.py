from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from identity.pow import solve_pow, verify_pow

# 5.2.2. Validacija proof-of-work mehanizma 
# Proof-of-work validacija proverava: 
# • da li generator proizvodi validne nonce vrednosti, 
# • i da li verifier ispravno odbacuje nevalidne identitete. 
# Testovi proveravaju: 
# 1. validne identitete, 
# 2. korumpirane nonce vrednosti, 
# 3. slučajeve bez nonce-a, 
# 4. i granične slučajeve. 
# Za svaki identitet proverava se 𝑣𝑒𝑟𝑖𝑓𝑦_𝑝𝑜𝑤(𝑖𝑑,𝑛𝑜𝑛𝑐𝑒) = 𝑇𝑟𝑢𝑒, samo ako hash zadovoljava definisani 
# prag. 

BITS = 12


def test_solve_then_verify():
    nonce = solve_pow("node-1", BITS)
    assert verify_pow("node-1", nonce, BITS)


def test_corrupt_nonce_fails():
    nonce = solve_pow("node-2", BITS)
    assert not verify_pow("node-2", nonce + 1, BITS)


def test_wrong_identity_fails():
    nonce = solve_pow("node-3", BITS)
    assert not verify_pow("node-999", nonce, BITS)


def test_valid_for_lower_difficulty():
    nonce = solve_pow("node-4", BITS)
    assert verify_pow("node-4", nonce, BITS - 4)


def test_missing_nonce_rejected():
    from identity.registry import IdentityRegistry
    registry = IdentityRegistry()
    assert registry.nonce_of(42) is None


def test_zero_difficulty_accepts_any_nonce():
    assert verify_pow("node-6", 0, 0)


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — PoW testovi prolaze")
