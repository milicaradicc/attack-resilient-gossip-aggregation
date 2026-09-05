from __future__ import annotations


# 4.4.3. Identity scoring 
# Za svakog peer kandidata računa se score: 
# 1/3 (age+exchange+pow)

# Score se koristi za: 
# • admission,  
# • eviction,  
# • i peer prioritizaciju.  

# Peer sa većim score-om smatra se stabilnijim i pouzdanijim. Ciljevi su favorizovanje dugotrajnih i stabilnih 
# peer-ova i ograničavanje uticaja novih identiteta.  

def score_age(round_now: int, first_seen_round: int, age_max: int) -> float:
    return max(0.0, min((round_now - first_seen_round) / age_max, 1.0))


def score_exchange(successful_exchanges: int, exchange_max: int) -> float:
    return max(0.0, min(successful_exchanges / exchange_max, 1.0))


def score_reliability(missed_total: int, exchange_max: int) -> float:
    # 5.1.7: peer koji ne odgovara postaje nestabilan i njegov skor opada.
    # Kazna je srazmerna ukupnom broju promasenih otkucaja, normalizovana istom
    # skalom kao razmene, pa potpuno cutljiv peer gubi ceo doprinos pouzdanosti.
    return max(0.0, 1.0 - missed_total / exchange_max) if exchange_max else 1.0


def identity_score(
    round_now: int,
    first_seen_round: int,
    successful_exchanges: int,
    pow_valid: bool,
    age_max: int,
    exchange_max: int,
    missed_total: int = 0,
) -> float:
    s_age = score_age(round_now, first_seen_round, age_max)
    s_exchange = score_exchange(successful_exchanges, exchange_max)
    s_pow = 1.0 if pow_valid else 0.0
    # osnovni skor iz specifikacije (4.4.3), umanjen za nepouzdanost peer-a
    base = (s_age + s_exchange + s_pow) / 3.0
    # ako peer ne odgovara skroz opada
    return base * score_reliability(missed_total, exchange_max)