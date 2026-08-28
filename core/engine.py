from __future__ import annotations

import random
from typing import Dict, List

from aggregation.base import AggregationStrategy
from attacks.scenario import Scenario
from core.node import Node
from identity.observation import Observation
from metrics.experiment_metrics import ExperimentMetrics, RoundCounters
from sampling.base import SamplingStrategy


class Engine:
    def __init__(self, nodes, aggregation, sampling, scenario, num_rounds, metrics, rng,
                 timeout_rounds: int = 0):
        self.nodes = nodes
        self.aggregation = aggregation
        self.sampling = sampling
        self.scenario = scenario
        self.num_rounds = num_rounds
        self.metrics = metrics
        self.rng = rng
        self.timeout_rounds = timeout_rounds

    def _observe(self, node, other, round_now, exchanged):
        obs = node.observations.get(other)
        # ako peer nije vidjen ranije dodaj observation
        if obs is None:
            node.observations[other] = Observation(
                first_seen_round=round_now, last_seen_round=round_now,
                successful_exchanges=1 if exchanged else 0)
        # ako jeste ziv je i osvezava se
        else:
            obs.last_seen_round = round_now
            if exchanged:
                obs.successful_exchanges += 1
                obs.missed_heartbeats = 0

    def _discover(self, round_now):
        offered = 0
        reasons = {"invalid_pow": 0, "too_young": 0, "low_score": 0,
                   "bucket_full": 0, "self_or_duplicate": 0}
        for node in self.nodes.values():
            # za svaki cvor, scenario ponudi kandidate (napadaci se guraju)
            # za svakog: broji ga i zabelezi u dnevnik (vidjanje, ne razmena)
            # time mu starost pocinje da tece
            for candidate in self.scenario.offer_candidates(node, round_now, self.rng):
                offered += 1
                self._observe(node, candidate, round_now, exchanged=False)
                # ako je kandidat komsija skip
                if candidate in node.peers:
                    continue
                # admission !!!!!!!!!!!! -> proverava PoW/starost/skor/bucket
                if self.sampling.accept_peer(node, candidate, round_now):
                    # ako je komsiluk pun izbaci najslabiji, ubaci novi
                    # TODO sta ako je novi losiji od starog?
                    if len(node.peers) >= self.sampling.max_peers:
                        victim = self.sampling.evict_peer(node, round_now, candidate)
                        if victim is None:
                            continue
                        node.peers.remove(victim)
                    node.peers.append(candidate)
                else:
                    #  povecaj brojace
                    why = self.sampling.reason(node, candidate, round_now) or "self_or_duplicate"
                    reasons[why] = reasons.get(why, 0) + 1
        return offered, sum(reasons.values()), reasons

    def _broadcast(self, round_now):
        # napravi snapshot svih cvorova i malicijusa
        out = {}
        for hid, node in self.nodes.items():
            out[hid] = self.scenario.broadcast_value(hid, node.estimate, round_now)
        for m in self.scenario.malicious_ids:
            # vrati placeholder svakako se ne koristi ta vrednost
            out[m] = self.scenario.broadcast_value(m, 0.0, round_now)
        return out

    def _heartbeat(self, node, peers, round_now):
        responders = []
        for p in peers:
            if self.scenario.responds(p, round_now, self.rng):
                self._observe(node, p, round_now, exchanged=True)
                responders.append(p)
            else:
                obs = node.observations.get(p)
                if obs is not None:
                    obs.missed_heartbeats += 1
        timeouts = 0
        if self.timeout_rounds > 0:
            for p in list(node.peers):
                obs = node.observations.get(p)
                if obs is not None and obs.missed_heartbeats > self.timeout_rounds:
                    node.peers.remove(p)
                    timeouts += 1
                    if p in responders:
                        responders.remove(p)
        return responders, timeouts

    def run(self):
        # sacuvaj prvu rundu
        self.metrics.record(0, self.nodes, self.scenario, RoundCounters())

        for r in range(1, self.num_rounds + 1):
            # churn
            self.scenario.churn_reset(self.nodes, r)
            # discover + admission
            offered, rejected, reasons = self._discover(r)
            # na pocetku runce snimak
            broadcast = self._broadcast(r) # ovde su i napadaci, own samo honest
            own = {hid: n.estimate for hid, n in self.nodes.items()}

            data_msgs = 0
            timeouts = 0
            for hid, node in self.nodes.items():
                peers = self.sampling.select_gossip_peers(node, self.rng) # uzmi peerove za razmenu
                responders, t = self._heartbeat(node, peers, r)
                timeouts += t
                received = [broadcast[p] for p in responders] # pokupi vrednosti onih koji su odgovorili
                data_msgs += len(received)
                node.estimate = self.aggregation.aggregate(own[hid], received) # nova procena

            counters = RoundCounters(
                data_msgs=data_msgs, control_msgs=offered + rejected,
                offered=offered, rejected=rejected,
                rej_invalid_pow=reasons["invalid_pow"], rej_too_young=reasons["too_young"],
                rej_low_score=reasons["low_score"], rej_bucket_full=reasons["bucket_full"],
                timeouts=timeouts)
            self.metrics.record(r, self.nodes, self.scenario, counters)

        return self.metrics.rows

    @staticmethod
    def true_mean(nodes):
        return sum(n.x_local for n in nodes.values()) / len(nodes)
