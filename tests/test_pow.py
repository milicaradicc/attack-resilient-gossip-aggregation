from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from identity.pow import solve_pow, verify_pow

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


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — PoW testovi prolaze")
