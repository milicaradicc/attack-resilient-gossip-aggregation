from __future__ import annotations


def score_age(round_now: int, first_seen_round: int, age_max: int) -> float:
    return max(0.0, min((round_now - first_seen_round) / age_max, 1.0))


def score_exchange(successful_exchanges: int, exchange_max: int) -> float:
    return max(0.0, min(successful_exchanges / exchange_max, 1.0))


def identity_score(
    round_now: int,
    first_seen_round: int,
    successful_exchanges: int,
    pow_valid: bool,
    age_max: int,
    exchange_max: int,
) -> float:
    s_age = score_age(round_now, first_seen_round, age_max)
    s_exchange = score_exchange(successful_exchanges, exchange_max)
    s_pow = 1.0 if pow_valid else 0.0
    return (s_age + s_exchange + s_pow) / 3.0
