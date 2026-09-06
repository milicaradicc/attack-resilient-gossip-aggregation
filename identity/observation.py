from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Observation:
    first_seen_round: int # prvi kontakt
    last_seen_round: int # poslednja aktivnost 
    successful_exchanges: int = 0 # broj uspesnih razmena 
    missed_heartbeats: int = 0 # uzastopni promasaji; resetuju se cim peer odgovori
    missed_total: int = 0 # ukupno promasenih otkucaja kroz ceo zivot peer-a
    timeout_count: int = 0 # koliko puta je peer izbacen zbog timeout-a