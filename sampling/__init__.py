from typing import Optional

from identity.params import IdentityParams
from sampling.base import SamplingStrategy
from sampling.eclipse_resistant import EclipseResistantStrategy
from sampling.random_strategy import RandomStrategy
from sampling.sybil_resistant import SybilResistantStrategy


def get_strategy(
    name: str,
    max_peers: int,
    params: Optional[IdentityParams] = None,
    seed: int = 0,
) -> SamplingStrategy:
    if name == "random":
        return RandomStrategy(max_peers, seed)
    if name == "sybil_resistant":
        return SybilResistantStrategy(max_peers, params)
    if name == "eclipse_resistant":
        return EclipseResistantStrategy(max_peers, params)
    raise ValueError(f"unknown strategy: {name}")