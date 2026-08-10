from __future__ import annotations

import hashlib
import random


def derive_seed(global_seed: int, *parts: object) -> int:
    h = hashlib.sha256()
    h.update(str(global_seed).encode())
    for p in parts:
        h.update(b"|")
        h.update(str(p).encode())
    return int.from_bytes(h.digest()[:8], "big")


def make_rng(global_seed: int, *parts: object) -> random.Random:
    return random.Random(derive_seed(global_seed, *parts))
