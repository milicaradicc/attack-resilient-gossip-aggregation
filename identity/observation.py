from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Observation:
    first_seen_round: int
    last_seen_round: int
    successful_exchanges: int = 0
    missed_heartbeats: int = 0
