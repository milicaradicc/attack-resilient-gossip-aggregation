from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from identity.scoring import identity_score, score_age, score_exchange

AGE_MAX = 20
EXCHANGE_MAX = 20


def test_score_in_range():
    for r in range(0, 40, 3):
        for ex in range(0, 40, 5):
            for pw in (True, False):
                s = identity_score(r, 0, ex, pw, AGE_MAX, EXCHANGE_MAX)
                assert 0.0 <= s <= 1.0


def test_age_saturates():
    assert score_age(100, 0, AGE_MAX) == 1.0


def test_exchange_saturates():
    assert score_exchange(1000, EXCHANGE_MAX) == 1.0


def test_minimum_is_zero():
    assert identity_score(0, 0, 0, False, AGE_MAX, EXCHANGE_MAX) == 0.0


def test_maximum_is_one():
    assert identity_score(AGE_MAX, 0, EXCHANGE_MAX, True, AGE_MAX, EXCHANGE_MAX) == 1.0


def test_invalid_pow_contributes_zero():
    with_pow = identity_score(AGE_MAX, 0, EXCHANGE_MAX, True, AGE_MAX, EXCHANGE_MAX)
    without_pow = identity_score(AGE_MAX, 0, EXCHANGE_MAX, False, AGE_MAX, EXCHANGE_MAX)
    assert abs((with_pow - without_pow) - (1.0 / 3.0)) < 1e-9


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — scoring testovi prolaze")
