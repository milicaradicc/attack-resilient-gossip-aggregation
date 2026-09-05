from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import run_benign as run


def test_benign_convergence():
    rows = run(n_honest=10, peer_set_size=7, num_rounds=50, seed=42)
    last = rows[-1]
    assert last.spread < 1e-6, f"nema konsenzusa, spread={last.spread}"
    assert last.err_rel < 1e-2, f"greška prevelika, err_rel={last.err_rel}"


def test_determinism():
    a = run(seed=1234)
    b = run(seed=1234)
    assert len(a) == len(b)
    for ra, rb in zip(a, b):
        assert ra.round == rb.round
        assert ra.err_rel == rb.err_rel
        assert ra.spread == rb.spread


def test_different_seed_differs():
    a = run(seed=1)
    b = run(seed=2)
    assert a[0].spread != b[0].spread


if __name__ == "__main__":
    test_benign_convergence()
    test_determinism()
    test_different_seed_differs()
    print("OK — svi testovi Faze 0 prolaze")
