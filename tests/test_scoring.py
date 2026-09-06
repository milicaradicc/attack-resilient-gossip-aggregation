from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from identity.scoring import (identity_score, score_age, score_exchange,
                              score_reliability)

# 5.2.3. Validacija identity score formule
# Score mora da zadovolji ogranicenje opsega, pravilnu saturaciju i
# deterministicko ponasanje. Testiraju se minimalne i maksimalne vrednosti,
# kombinacije age i exchange parametara i granicni slucajevi saturacije.
# Potvrdjuje se da vazi 0 <= score <= 1 za svaki moguci ulaz.

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


def test_score_falls_with_missed_heartbeats():
    full = identity_score(AGE_MAX, 0, EXCHANGE_MAX, True, AGE_MAX, EXCHANGE_MAX)
    half = identity_score(AGE_MAX, 0, EXCHANGE_MAX, True, AGE_MAX, EXCHANGE_MAX,
                          missed_total=EXCHANGE_MAX // 2)
    none = identity_score(AGE_MAX, 0, EXCHANGE_MAX, True, AGE_MAX, EXCHANGE_MAX,
                          missed_total=EXCHANGE_MAX)
    assert full > half > none
    assert none == 0.0


def test_score_in_range_with_misses():
    for r in range(0, 40, 5):
        for ex in range(0, 40, 10):
            for missed in range(0, 40, 10):
                for pw in (True, False):
                    s = identity_score(r, 0, ex, pw, AGE_MAX, EXCHANGE_MAX,
                                       missed_total=missed)
                    assert 0.0 <= s <= 1.0


def test_score_is_deterministic():
    args = (7, 0, 4, True, AGE_MAX, EXCHANGE_MAX)
    assert identity_score(*args) == identity_score(*args)


def test_age_and_exchange_combinations_are_monotone():
    base = identity_score(5, 0, 5, True, AGE_MAX, EXCHANGE_MAX)
    older = identity_score(10, 0, 5, True, AGE_MAX, EXCHANGE_MAX)
    busier = identity_score(5, 0, 10, True, AGE_MAX, EXCHANGE_MAX)
    assert older > base and busier > base


def test_saturation_boundary():
    assert score_age(AGE_MAX, 0, AGE_MAX) == 1.0
    assert score_age(AGE_MAX + 50, 0, AGE_MAX) == 1.0
    assert score_exchange(EXCHANGE_MAX, EXCHANGE_MAX) == 1.0
    assert score_exchange(EXCHANGE_MAX + 50, EXCHANGE_MAX) == 1.0


def test_reliability_in_range():
    for missed in range(0, 2 * EXCHANGE_MAX):
        assert 0.0 <= score_reliability(missed, EXCHANGE_MAX) <= 1.0


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — scoring testovi prolaze")