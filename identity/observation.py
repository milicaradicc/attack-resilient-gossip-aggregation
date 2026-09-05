from __future__ import annotations

from dataclasses import dataclass

# 4.4.2. Age tracking 
# Svaki čvor vodi evidenciju: 
# • kada je prvi put video određeni identitet, 
# • koliko dugo identitet postoji, 
# • i koliko dugo ostaje aktivan. 
# Definiše se: 
# • first_seen_round, 
# • last_seen_round, 
# • i broj uspešnih razmena. 
# Novi identitet ne može odmah ući u peer set već mora zadovoljiti minimalni age prag. Ciljevi su sprečavanje 
# flash Sybil ubacivanja i povećanje cene churn napada.  

@dataclass
class Observation:
    first_seen_round: int # prvi kontakt
    last_seen_round: int # poslednja aktivnost 
    successful_exchanges: int = 0 # broj uspesnih razmena 
    missed_heartbeats: int = 0 # uzastopni promasaji; resetuju se cim peer odgovori
    missed_total: int = 0 # 5.1.7: ukupno promasenih otkucaja kroz ceo zivot peer-a
    timeout_count: int = 0 # 5.1.7: koliko puta je peer izbacen zbog timeout-a