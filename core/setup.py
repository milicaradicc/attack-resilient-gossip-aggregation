from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Dict, Set

from attacks.scenario import AttackParams, Scenario
from core.node import Node
from core.overlay import build_random_overlay
from core.rng import make_rng
from identity.observation import Observation
from identity.pow import solve_pow
from identity.registry import IdentityParams, IdentityRegistry


@dataclass
class RunConfig:
    n_honest: int = 10 # broj honest cvorova
    peer_set_size: int = 7 # broj komsija
    num_rounds: int = 50 # broj rundi
    global_seed: int = 42 # seed za reproduktivnost
    value_low: float = 50.0 # opseg vrednosti 50-150
    value_high: float = 150.0
    num_buckets: int = 0 # >0 ukljucuje bucket-svesnu topologiju
    max_per_bucket: int = 0


def build_nodes(cfg: RunConfig) -> Dict[int, Node]:
    # iz jednog globalnog seeda izvode se dva generatora -> biranje komsija i biranje vrednosti nezavisno
    val_rng = make_rng(cfg.global_seed, "initial_metrics")
    top_rng = make_rng(cfg.global_seed, "overlay_topology")
    nodes = {
        i: Node.create(i, val_rng.uniform(cfg.value_low, cfg.value_high))
        for i in range(cfg.n_honest)
    }
    # svakon cvoru se dodeljuju komsije, pravi se topologija
    for i, peers in build_random_overlay(cfg.n_honest, cfg.peer_set_size, top_rng,
                                        num_buckets=cfg.num_buckets,
                                        max_per_bucket=cfg.max_per_bucket).items():
        nodes[i].peers = peers
    return nodes # {0: Node, 1: Node, ...}


def seed_observations(nodes: Dict[int, Node]) -> None:
    # za svaki cvor za svaki peer se belezi starost, od runde 0
    # starost identiteta se računa kao (trenutna_runda - first_seen)
    # TODO proveriti ostala polja jel se update kako treba
    for node in nodes.values():
        for peer in node.peers:
            node.observations[peer] = Observation(first_seen_round=0, last_seen_round=0)


def register_all(ids: Set[int], params: IdentityParams) -> IdentityRegistry:
    # resavanje pow da bi se registrovali
    registry = IdentityRegistry()
    for i in ids:
        registry.register(i, solve_pow(str(i), params.pow_difficulty_bits))
    return registry


def malicious_counts(n_honest: int, beta: float, byzantine_fraction: float):
    # beta je udeo zlonamernih u CELOJ mrezi: beta = n_mal / (n_honest + n_mal)
    # resavanjem po n_mal dobija se n_mal = n_honest * beta / (1 - beta)
    # jedno mesto za ovu formulu; koriste je i config, i gen_compose, i controller
    if beta <= 0.0:
        return 0, 0
    n_mal = round(n_honest * beta / (1.0 - beta))
    n_byzantine = round(n_mal * byzantine_fraction)
    return n_byzantine, n_mal - n_byzantine


@dataclass
class World:
    # sve sto cini jedan eksperiment pre nego sto krene izvrsavanje
    cfg: RunConfig
    nodes: Dict[int, Node]
    honest: Set[int]
    byzantine: Set[int]
    sybil: Set[int]
    registry: IdentityRegistry
    id_params: IdentityParams
    scenario: Scenario
    x_star: float


def build_world(spec) -> World:
    # jedno mesto na kome se sklapa svet: cvorovi, identiteti, PoW registar i scenario napada
    # koriste ga i in-process matrica (in_process/matrix.py) i distribuirani controller,
    # da se priprema eksperimenta ne bi duplirala i vremenom razisla
    cfg = RunConfig(
        n_honest=spec.n_honest,
        peer_set_size=spec.peer_set_size,
        num_rounds=spec.num_rounds,
        global_seed=spec.seed,
        value_low=spec.value_low,
        value_high=spec.value_high,
        num_buckets=spec.num_buckets,
        max_per_bucket=spec.max_per_bucket,
    )
    nodes = build_nodes(cfg)
    seed_observations(nodes)

    honest = set(nodes.keys())
    n_byzantine, n_sybil = spec.malicious_counts()
    b0 = spec.n_honest
    byzantine = set(range(b0, b0 + n_byzantine))
    sybil = set(range(b0 + n_byzantine, b0 + n_byzantine + n_sybil))

    id_params = IdentityParams(
        pow_difficulty_bits=spec.pow_difficulty_bits,
        age_min=spec.age_min,
        age_max=spec.age_max,
        exchange_max=spec.exchange_max,
        score_threshold=spec.score_threshold,
        num_buckets=spec.num_buckets,
        max_per_bucket=spec.max_per_bucket,
        timeout_rounds=spec.timeout_rounds,
    )
    registry = register_all(honest | byzantine | sybil, id_params)
    x_star = mean(n.x_local for n in nodes.values())

    if n_byzantine + n_sybil == 0:
        scenario = Scenario.benign(honest)
    else:
        scenario = Scenario(honest, byzantine, sybil, AttackParams(
            byzantine_profile=spec.byzantine_profile,
            coordinated_value=spec.coordinated_value,
            extreme_offset=spec.extreme_offset,
            random_low=spec.random_low,
            random_high=spec.random_high,
            low_bias=spec.low_bias,
            stale_value=spec.stale_value,
            poison_honest_offers=spec.poison_honest_offers,
            x_star=x_star,
            experiment_seed=spec.seed, # 4.10: randomness napada se izvodi iz istog seed-a
            activate_round=spec.activate_round,
            flooding=spec.flooding,
            churn_period=spec.churn_period,
            selective_p=spec.selective_p,
            unresponsive_p=spec.unresponsive_p,
            eclipse_targets=spec.eclipse_targets,
        ))

    return World(cfg, nodes, honest, byzantine, sybil, registry, id_params, scenario, x_star)