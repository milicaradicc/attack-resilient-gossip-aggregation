from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set

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


def build_nodes(cfg: RunConfig) -> Dict[int, Node]:
    # iz jednog globalnog seeda izvode se dva generatora -> biranje komsija i biranje vrednosti nezavisno
    val_rng = make_rng(cfg.global_seed, "initial_metrics")
    top_rng = make_rng(cfg.global_seed, "overlay_topology")
    nodes = {
        i: Node.create(i, val_rng.uniform(cfg.value_low, cfg.value_high))
        for i in range(cfg.n_honest)
    }
    for i, peers in build_random_overlay(cfg.n_honest, cfg.peer_set_size, top_rng).items():
        nodes[i].peers = peers
    return nodes # {0: Node, 1: Node, ...}


def seed_observations(nodes: Dict[int, Node]) -> None:
    for node in nodes.values():
        for peer in node.peers:
            node.observations[peer] = Observation(first_seen_round=0, last_seen_round=0)


def register_all(ids: Set[int], params: IdentityParams) -> IdentityRegistry:
    registry = IdentityRegistry()
    for i in ids:
        registry.register(i, solve_pow(str(i), params.pow_difficulty_bits))
    return registry
