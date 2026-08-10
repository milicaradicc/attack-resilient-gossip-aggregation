from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set, Tuple

from aggregation import get_aggregation
from attacks.scenario import AttackParams, Scenario
from core.rng import make_rng
from experiments.engine import Engine
from core.setup import RunConfig, build_nodes, register_all, seed_observations
from identity.registry import IdentityParams
from metrics.experiment_metrics import ExperimentMetrics
from sampling import get_strategy
from sampling.random_strategy import RandomStrategy


def run_benign(cfg: RunConfig, aggregation_name: str = "mean", **agg_kwargs) -> List:
    nodes = build_nodes(cfg)
    scenario = Scenario.benign(set(nodes.keys()))
    x_star = Engine.true_mean(nodes)
    metrics = ExperimentMetrics(x_star=x_star, num_buckets=8)
    aggregation = get_aggregation(aggregation_name, **agg_kwargs)
    sampling = RandomStrategy(cfg.peer_set_size)
    rng = make_rng(cfg.global_seed, "gossip")
    return Engine(nodes, aggregation, sampling, scenario, cfg.num_rounds, metrics, rng).run()


@dataclass
class AttackConfig:
    base: RunConfig = field(default_factory=lambda: RunConfig(n_honest=20))
    n_sybil: int = 6
    n_byzantine: int = 3
    coordinated_value: float = 1000.0
    activate_round: int = 1


def scenario_ids(cfg: AttackConfig) -> Tuple[Set[int], Set[int], Set[int]]:
    honest = set(range(cfg.base.n_honest))
    b0 = cfg.base.n_honest
    byzantine = set(range(b0, b0 + cfg.n_byzantine))
    s0 = b0 + cfg.n_byzantine
    sybil = set(range(s0, s0 + cfg.n_sybil))
    return honest, byzantine, sybil


def run_attack(cfg: AttackConfig, strategy_name: str, aggregation_name: str,
               params: IdentityParams, **agg_kwargs) -> List:
    nodes = build_nodes(cfg.base)
    seed_observations(nodes)
    honest, byzantine, sybil = scenario_ids(cfg)
    registry = register_all(honest | byzantine | sybil, params)
    x_star = Engine.true_mean(nodes)
    scenario = Scenario(honest, byzantine, sybil,
                        AttackParams(coordinated_value=cfg.coordinated_value,
                                     activate_round=cfg.activate_round))
    metrics = ExperimentMetrics(x_star=x_star, num_buckets=params.num_buckets)
    aggregation = get_aggregation(aggregation_name, **agg_kwargs)
    sampling = get_strategy(strategy_name, cfg.base.peer_set_size, registry, params)
    rng = make_rng(cfg.base.global_seed, "attack")
    return Engine(nodes, aggregation, sampling, scenario, cfg.base.num_rounds, metrics, rng).run()
