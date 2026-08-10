from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class RunSpec:
    n_honest: int
    beta: float
    overlay: str
    aggregation: str
    seed: int
    peer_set_size: int
    num_rounds: int
    coordinated_value: float
    activate_round: int
    pow_difficulty_bits: int
    num_buckets: int
    byzantine_fraction: float
    epsilon: float
    conv_window_start: int
    byzantine_profile: str
    flooding: int
    churn_period: int
    selective_p: float
    timeout_rounds: int
    unresponsive_p: float
    trim_alpha: float = 0.2

    def malicious_counts(self) -> Tuple[int, int]:
        if self.beta <= 0.0:
            return 0, 0
        n_mal = round(self.n_honest * self.beta / (1.0 - self.beta))
        n_byzantine = round(n_mal * self.byzantine_fraction)
        return n_byzantine, n_mal - n_byzantine


def load_matrix(path: str) -> List[RunSpec]:
    with open(path) as f:
        c = json.load(f)
    fixed = dict(
        peer_set_size=c.get("peer_set_size", 7),
        num_rounds=c.get("num_rounds", 50),
        coordinated_value=c.get("coordinated_value", 1000.0),
        activate_round=(c["warmup"] + 1) if "warmup" in c else c.get("activate_round", 1),
        pow_difficulty_bits=c.get("pow_difficulty_bits", 12),
        num_buckets=c.get("num_buckets", 8),
        byzantine_fraction=c.get("byzantine_fraction", 0.34),
        epsilon=c.get("epsilon", 0.05),
        conv_window_start=c.get("conv_window_start", 20),
        flooding=c.get("flooding", 0),
        churn_period=c.get("churn_period", 0),
        selective_p=c.get("selective_p", 1.0),
        timeout_rounds=c.get("timeout_rounds", 3),
        unresponsive_p=c.get("unresponsive_p", 0.0),
        trim_alpha=c.get("trim_alpha", 0.2),
    )
    profiles = c.get("byzantine_profile", ["coordinated"])
    specs: List[RunSpec] = []
    for nh in c["n_honest"]:
        for beta in c["beta"]:
            for overlay in c["overlay"]:
                for aggregation in c["aggregation"]:
                    for profile in profiles:
                        for seed in c["seeds"]:
                            specs.append(RunSpec(nh, beta, overlay, aggregation, seed,
                                                 byzantine_profile=profile, **fixed))
    return specs
