from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from statistics import mean, pvariance
from typing import Dict, List

from attacks.scenario import Scenario
from core.node import Node
from identity.buckets import bucket_of

FIELDS = [
    "round", "err_rel", "spread", "sybil_penetration", "eclipse_rate",
    "peer_diversity", "bucket_occupancy", "avg_estimate",
    "control_msgs", "data_msgs", "offered", "rejected",
    "rej_invalid_pow", "rej_too_young", "rej_low_score", "rej_bucket_full", "timeouts",
]


@dataclass
class RoundCounters:
    data_msgs: int = 0
    control_msgs: int = 0
    offered: int = 0
    rejected: int = 0
    rej_invalid_pow: int = 0
    rej_too_young: int = 0
    rej_low_score: int = 0
    rej_bucket_full: int = 0
    timeouts: int = 0


@dataclass
class RoundMetrics:
    round: int
    err_rel: float
    spread: float
    sybil_penetration: float
    eclipse_rate: float
    peer_diversity: float
    bucket_occupancy: float
    avg_estimate: float
    control_msgs: int
    data_msgs: int
    offered: int
    rejected: int
    rej_invalid_pow: int
    rej_too_young: int
    rej_low_score: int
    rej_bucket_full: int
    timeouts: int


@dataclass
class ExperimentMetrics:
    x_star: float
    num_buckets: int
    rows: List[RoundMetrics] = field(default_factory=list)

    def record(self, round_no, nodes, scenario, counters=None) -> RoundMetrics:
        c = counters or RoundCounters()
        estimates = [n.estimate for n in nodes.values()]
        avg = mean(estimates)
        err = abs(avg - self.x_star) / abs(self.x_star) if self.x_star else abs(avg)
        spread = max(estimates) - min(estimates)
        pen = mean(self._sybil_share(n, scenario) for n in nodes.values())
        eclipsed = sum(1 for n in nodes.values() if not self._has_honest_peer(n, scenario))
        eclipse_rate = eclipsed / len(nodes)
        diversity = mean(self._diversity(n) for n in nodes.values())
        occupancy = mean(self._bucket_occupancy(n) for n in nodes.values())
        rm = RoundMetrics(
            round_no, err, spread, pen, eclipse_rate, diversity, occupancy, avg,
            c.control_msgs, c.data_msgs, c.offered, c.rejected,
            c.rej_invalid_pow, c.rej_too_young, c.rej_low_score, c.rej_bucket_full, c.timeouts,
        )
        self.rows.append(rm)
        return rm

    def _sybil_share(self, node, scenario):
        if not node.peers:
            return 0.0
        return sum(1 for p in node.peers if p in scenario.sybil_ids) / len(node.peers)

    def _has_honest_peer(self, node, scenario):
        return any(p in scenario.honest_ids for p in node.peers)

    def _bucket_counts(self, node):
        counts: Dict[int, int] = {}
        for p in node.peers:
            b = bucket_of(str(p), self.num_buckets)
            counts[b] = counts.get(b, 0) + 1
        return counts

    def _diversity(self, node):
        if not node.peers:
            return 0.0
        total = len(node.peers)
        return -sum((c / total) * math.log(c / total) for c in self._bucket_counts(node).values())

    def _bucket_occupancy(self, node):
        if not node.peers:
            return 0.0
        return max(self._bucket_counts(node).values()) / len(node.peers)

    def convergence_time(self, epsilon):
        for r in self.rows:
            if r.round >= 1 and r.err_rel < epsilon:
                return r.round
        return -1

    def stability(self, window_start):
        vals = [r.avg_estimate for r in self.rows if r.round >= window_start]
        return pvariance(vals) if len(vals) >= 2 else 0.0

    def data_overhead(self, n_honest):
        vals = [r.data_msgs for r in self.rows if r.round >= 1]
        return mean(vals) / n_honest if vals else 0.0

    def control_overhead(self, n_honest):
        vals = [r.control_msgs for r in self.rows if r.round >= 1]
        return mean(vals) / n_honest if vals else 0.0

    def rejected_ratio(self):
        offered = sum(r.offered for r in self.rows)
        rejected = sum(r.rejected for r in self.rows)
        return rejected / offered if offered else 0.0

    def mean_bucket_occupancy(self):
        vals = [r.bucket_occupancy for r in self.rows if r.round >= 1]
        return mean(vals) if vals else 0.0

    def rejection_breakdown(self):
        total = sum(r.rejected for r in self.rows) or 1
        return {
            "pow": sum(r.rej_invalid_pow for r in self.rows) / total,
            "age": sum(r.rej_too_young for r in self.rows) / total,
            "score": sum(r.rej_low_score for r in self.rows) / total,
            "bucket": sum(r.rej_bucket_full for r in self.rows) / total,
        }

    def to_csv_rows(self):
        return [[r.round, r.err_rel, r.spread, r.sybil_penetration, r.eclipse_rate,
                 r.peer_diversity, r.bucket_occupancy, r.avg_estimate,
                 r.control_msgs, r.data_msgs, r.offered, r.rejected,
                 r.rej_invalid_pow, r.rej_too_young, r.rej_low_score, r.rej_bucket_full, r.timeouts]
                for r in self.rows]

    def write_csv(self, path):
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(FIELDS)
            for row in self.to_csv_rows():
                w.writerow(row)
