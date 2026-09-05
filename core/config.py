from __future__ import annotations

import json
import os
from dataclasses import dataclass

from core.setup import malicious_counts as core_malicious_counts
from typing import Any, Dict, List, Tuple

from core.setup import malicious_counts as core_malicious_counts

DEFAULTS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "configs", "defaults.json")

SWEEP_KEYS = ("n_honest", "beta", "overlay", "aggregation", "seeds", "byzantine_profile")


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
    age_min: int = 3
    age_max: int = 20
    exchange_max: int = 20
    score_threshold: float = 0.5
    max_per_bucket: int = 2
    value_low: float = 50.0
    value_high: float = 150.0
    poison_honest_offers: int = 1
    extreme_offset: float = 1000.0
    random_low: float = -1000.0
    random_high: float = 1000.0
    low_bias: float = 5.0
    stale_value: float = 130.0
    eclipse_targets: int = 0

    def malicious_counts(self) -> Tuple[int, int]:
        return core_malicious_counts(self.n_honest, self.beta, self.byzantine_fraction)


def load_defaults(path: str = DEFAULTS_PATH) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def merged_config(path: str = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    cfg = load_defaults()
    override: Dict[str, Any] = {}
    if path:
        with open(path) as f:
            override = json.load(f)
        cfg.update(override)
    return cfg, override


def _activate_round(c: Dict[str, Any], override: Dict[str, Any]) -> int:
    if "activate_round" in override:
        return override["activate_round"]
    if "warmup" in override:
        return override["warmup"] + 1
    if "warmup" in c:
        return c["warmup"] + 1
    return c.get("activate_round", 1)


def _spec_fields(c, override=None):
    # jedno mesto koje preslikava ucitanu konfiguraciju u polja RunSpec-a;
    # koriste ga i load_matrix (puna matrica) i spec_from (pojedinacni RunSpec)
    return dict(
        n_honest=c["n_honest"][0], beta=c["beta"][0], overlay=c["overlay"][0],
        aggregation=c["aggregation"][0], seed=c["seeds"][0],
        byzantine_profile=c["byzantine_profile"][0],
        activate_round=_activate_round(c, override or {}),
        peer_set_size=c["peer_set_size"], num_rounds=c["num_rounds"],
        coordinated_value=c["coordinated_value"],
        pow_difficulty_bits=c["pow_difficulty_bits"], num_buckets=c["num_buckets"],
        byzantine_fraction=c["byzantine_fraction"], epsilon=c["epsilon"],
        conv_window_start=c["conv_window_start"], flooding=c["flooding"],
        churn_period=c["churn_period"], selective_p=c["selective_p"],
        timeout_rounds=c["timeout_rounds"], unresponsive_p=c["unresponsive_p"],
        trim_alpha=c["trim_alpha"], age_min=c["age_min"], age_max=c["age_max"],
        exchange_max=c["exchange_max"], score_threshold=c["score_threshold"],
        max_per_bucket=c["max_per_bucket"], value_low=c["value_low"],
        value_high=c["value_high"], poison_honest_offers=c["poison_honest_offers"],
        extreme_offset=c["extreme_offset"], random_low=c["random_low"],
        random_high=c["random_high"], low_bias=c["low_bias"],
        stale_value=c["stale_value"], eclipse_targets=c["eclipse_targets"],
    )


def load_matrix(path: str) -> List[RunSpec]:
    c, override = merged_config(path)
    base = _spec_fields(c, override)
    specs: List[RunSpec] = []
    for nh in c["n_honest"]:
        for beta in c["beta"]:
            for overlay in c["overlay"]:
                for aggregation in c["aggregation"]:
                    for profile in c["byzantine_profile"]:
                        for seed in c["seeds"]:
                            specs.append(RunSpec(**{**base, "n_honest": nh, "beta": beta,
                                                    "overlay": overlay,
                                                    "aggregation": aggregation,
                                                    "byzantine_profile": profile,
                                                    "seed": seed}))
    return specs


def spec_from(**overrides) -> RunSpec:
    # RunSpec od podrazumevanih vrednosti (configs/defaults.json) uz navedene izmene;
    # koriste ga testovi i distribuirani controller (jedan scenario iz env varijabli)
    fields = _spec_fields(load_defaults())
    fields.update(overrides)
    return RunSpec(**fields)
