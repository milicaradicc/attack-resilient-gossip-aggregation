from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import List, Optional


TRACE_FIELDS = ["round", "event", "node_id", "peer_id", "detail", "value"]

ACCEPT = "accept"
REJECT = "reject"
EVICT = "evict"
ATTACK = "attack_activated"
ESTIMATE = "estimate"
BROADCAST = "malicious_broadcast"
CHURN = "churn_reset"
CHURN_LEAVE = "churn_leave"
FLOOD = "flooding"


@dataclass
class TraceEvent:
    round: int
    event: str
    node_id: int
    peer_id: Optional[int]
    detail: str
    value: Optional[float]


@dataclass
class EventTrace:
    events: List[TraceEvent] = field(default_factory=list)

    def accept(self, round_now, node_id, peer_id):
        # kandidat je primljen u peer set
        self.events.append(TraceEvent(round_now, ACCEPT, node_id, peer_id, "", None))

    def reject(self, round_now, node_id, peer_id, reason):
        # kandidat odbijen; detail nosi razlog (invalid_pow, too_young,
        # low_score, bucket_full)
        self.events.append(TraceEvent(round_now, REJECT, node_id, peer_id, reason, None))

    def evict(self, round_now, node_id, peer_id, reason, replacement):
        # peer je uklonjen iz peer set-a. Razlog je jedan od:
        #   replaced_by:<id> - zamenio ga je bolji kandidat (admission)
        #   timeout          - predugo je cutao, odbrana ga je uklonila
        #   churn_leave      - identitet je napustio mrezu (3.8), nije odluka cvora
        # Bez trece vrednosti zapis ne bi bio konzistentan: posle churn promene
        # peer bi nestao iz peer set-a bez ijednog dogadjaja, pa bi se u zapisu
        # video drugi 'accept' istog identiteta bez 'evict' izmedju.
        detail = reason if replacement is None else f"{reason}:{replacement}"
        self.events.append(TraceEvent(round_now, EVICT, node_id, peer_id, detail, None))

    def attack_activated(self, round_now, malicious_count):
        # trenutak u kome napad postaje aktivan
        self.events.append(
            TraceEvent(round_now, ATTACK, -1, None, "activated", float(malicious_count)))

    def estimate(self, round_now, node_id, value):
        # agregaciona vrednost cvora na kraju runde
        self.events.append(TraceEvent(round_now, ESTIMATE, node_id, None, "", value))

    def malicious_broadcast(self, round_now, node_id, value, profile):
        # vrednost koju je napadacki cvor emitovao te runde, uz profil ponasanja
        self.events.append(TraceEvent(round_now, BROADCAST, node_id, None, profile, value))

    def churn_reset(self, round_now, count):
        # identiteti koji se vracaju i cija je starost resetovana kod svih ostalih cvorova
        self.events.append(TraceEvent(round_now, CHURN, -1, None, "reset", float(count)))

    def flooding(self, round_now, node_id, count):
        # broj laznih kandidata ubacenih kod ovog cvora u toj rundi
        self.events.append(TraceEvent(round_now, FLOOD, node_id, None, "candidates", float(count)))

    def csv_rows(self):
        return [[e.round, e.event, e.node_id,
                 "" if e.peer_id is None else e.peer_id,
                 e.detail, "" if e.value is None else e.value]
                for e in self.events]

    def write_csv(self, path):
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(TRACE_FIELDS)
            for row in self.csv_rows():
                writer.writerow(row)