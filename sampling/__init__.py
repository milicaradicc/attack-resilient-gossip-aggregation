from typing import Optional

from identity.registry import IdentityParams, IdentityRegistry
from sampling.base import SamplingStrategy
from sampling.eclipse_resistant import EclipseResistantStrategy
from sampling.random_strategy import RandomStrategy
from sampling.sybil_resistant import SybilResistantStrategy


def get_strategy(
    name: str,
    max_peers: int,
    registry: Optional[IdentityRegistry] = None,
    params: Optional[IdentityParams] = None,
) -> SamplingStrategy:
    if name == "random":
        return RandomStrategy(max_peers)
    if name == "sybil_resistant":
        return SybilResistantStrategy(max_peers, registry, params)
    if name == "eclipse_resistant":
        return EclipseResistantStrategy(max_peers, registry, params)
    raise ValueError(f"unknown strategy: {name}")
