from __future__ import annotations

from typing import List

from core.config import spec_from
from experiments.matrix import run_single

# Pomocni pokretaci za testove: sklapaju RunSpec i pustaju istu putanju
# (run_single -> build_world -> Engine) koju koristi i puna matrica.
# Priprema sveta nije duplirana — nalazi se samo u core/setup.py::build_world.


def run_benign(n_honest: int = 10, aggregation: str = "mean", seed: int = 42,
               peer_set_size: int = 7, num_rounds: int = 50, **overrides) -> List:
    # bez napadaca: beta=0 -> build_world pravi benigni scenario
    spec = spec_from(n_honest=n_honest, beta=0.0, overlay="random",
                     aggregation=aggregation, seed=seed, peer_set_size=peer_set_size,
                     num_rounds=num_rounds, **overrides)
    return run_single(spec).rows


def run_attack(overlay: str, aggregation: str, n_honest: int = 8, beta: float = 0.3,
               seed: int = 42, num_rounds: int = 20, activate_round: int = 1,
               pow_difficulty_bits: int = 8, **overrides) -> List:
    # napad aktivan od prve runde; broj napadaca se izvodi iz beta
    spec = spec_from(n_honest=n_honest, beta=beta, overlay=overlay,
                     aggregation=aggregation, seed=seed, num_rounds=num_rounds,
                     activate_round=activate_round,
                     pow_difficulty_bits=pow_difficulty_bits, **overrides)
    return run_single(spec).rows
