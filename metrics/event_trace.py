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
CHURN_LEAVE = "churn_leave" # evict reason used when an identity leaves the network
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
        # the candidate was admitted into the peer set
        self.events.append(TraceEvent(round_now, ACCEPT, node_id, peer_id, "", None))

    def reject(self, round_now, node_id, peer_id, reason):
        # candidate rejected; detail carries the reason (invalid_pow, too_young,
        # low_score, bucket_full)
        self.events.append(TraceEvent(round_now, REJECT, node_id, peer_id, reason, None))

    def evict(self, round_now, node_id, peer_id, reason, replacement):
        # a peer was removed from the peer set. The reason is one of:
        #   replaced_by:<id> - replaced by a better candidate (admission)
        #   timeout          - stayed silent too long, the defence dropped it
        #   churn_leave      - the identity left the network (3.8), not the node's decision
        # Without the third value the log would not be consistent: after the churn
        # change a peer would vanish from the peer set with no event at all, so the
        # record would show a second 'accept' of the same identity with no 'evict'
        # in between.
        detail = reason if replacement is None else f"{reason}:{replacement}"
        self.events.append(TraceEvent(round_now, EVICT, node_id, peer_id, detail, None))

    def attack_activated(self, round_now, malicious_count):
        # the moment the attack becomes active
        self.events.append(
            TraceEvent(round_now, ATTACK, -1, None, "activated", float(malicious_count)))

    def estimate(self, round_now, node_id, value):
        # the node's aggregation value at the end of the round
        self.events.append(TraceEvent(round_now, ESTIMATE, node_id, None, "", value))

    def malicious_broadcast(self, round_now, node_id, value, profile):
        # the value a malicious node emitted that round, together with its behaviour profile
        self.events.append(TraceEvent(round_now, BROADCAST, node_id, None, profile, value))

    def churn_reset(self, round_now, count):
        # returning identities whose age was reset at every other node
        self.events.append(TraceEvent(round_now, CHURN, -1, None, "reset", float(count)))

    def flooding(self, round_now, node_id, count):
        # number of fake candidates injected at this node in that round
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