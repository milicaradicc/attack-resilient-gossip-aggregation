from __future__ import annotations

from attacks.base import NO_MESSAGE
from core import messages, round_ops
from core.transport import Transport
from metrics.experiment_metrics import RoundCounters


class Engine:
    def __init__(self, nodes, aggregation, sampling, scenario, num_rounds, metrics, rng,
                 nonces, timeout_rounds: int = 0, trace=None):
        self.nodes = nodes
        self.aggregation = aggregation
        self.sampling = sampling
        self.scenario = scenario
        self.num_rounds = num_rounds
        self.metrics = metrics
        self.rng = rng
        self.nonces = nonces
        self.timeout_rounds = timeout_rounds
        self.trace = trace # 5.1.8: opcioni zapis dogadjaja

    def _discover(self, round_now, transport=None):
        offered = 0
        reasons = round_ops.empty_reasons()
        for node in self.nodes.values():
            self.sampling.refresh_peers(node, round_now, self.rng)
        for node in self.nodes.values():
            round_ops.send_peer_request(node, round_now, transport=transport)
        for node in self.nodes.values():
            candidates = self.scenario.offer_candidates(node, round_now, self.rng)
            offers = [(c, self.nonces.get(c)) for c in candidates]
            round_ops.receive_offers(node, offers, round_now, transport=transport)
        for node in self.nodes.values():
            n_off, _, node_reasons = round_ops.admit(node, self.sampling, round_now,
                                                     trace=self.trace,
                                                     transport=transport)
            offered += n_off
            for k, v in node_reasons.items():
                reasons[k] += v
        return offered, sum(reasons.values()), reasons

    def _emit(self, round_now):
        # H9: ista logika koju koristi i distribuirana putanja — drzi se na
        # jednom mestu (core/round_ops), da se dve putanje ne raziđu
        return round_ops.emitted_values(self.nodes, self.scenario, round_now,
                                        trace=self.trace)

    def _heartbeat(self, node, peers, round_now, transport=None):
        return round_ops.heartbeat(node, peers, round_now, self.timeout_rounds,
                                   lambda p: self.scenario.responds(p, round_now, self.rng,
                                                                    target=node.node_id),
                                   trace=self.trace, transport=transport)

    def _update_attackers(self, round_now):
        attackers = self.scenario.attacker_nodes
        if not attackers:
            return
        for aid, att in attackers.items():
            att.peers = sorted(hid for hid, n in self.nodes.items() if aid in n.peers)
            for h in att.peers:
                round_ops.observe(att, h, round_now, exchanged=True)
            heard = [n.estimate for n in self.nodes.values()]
            if heard:
                att.estimate = sum(heard) / len(heard)

    def run(self):
        self.metrics.record(0, self.nodes, self.scenario, RoundCounters())

        for r in range(1, self.num_rounds + 1):
            self.scenario.before_round(self.nodes, r, trace=self.trace)
            if self.trace is not None:
                comebacks = self.scenario.returning_count(r)
                if comebacks:
                    self.trace.churn_reset(r, comebacks)
            if self.trace is not None and r == self.scenario.params.activate_round:
                self.trace.attack_activated(r, len(self.scenario.malicious_ids))
            transport = Transport()

            self._update_attackers(r)
            emitted = self._emit(r) 
            own = {hid: n.estimate for hid, n in self.nodes.items()}

            data_msgs = 0
            timeouts = 0
            for hid, node in self.nodes.items():
                peers = self.sampling.select_gossip_peers(node, self.rng) # peer-ovi za ovu razmenu
                responders, t = self._heartbeat(node, peers, r, transport=transport)
                timeouts += t
                round_ops.deliver(node, responders, emitted, r, transport=transport,
                                  scenario=self.scenario)
                incoming = transport.receive(hid, messages.AGGREGATE)
                received = [m.payload for m in incoming]
                data_msgs += len(received)
                node.estimate = self.aggregation.aggregate(own[hid], received) # nova procena
                if self.trace is not None:
                    self.trace.estimate(r, hid, node.estimate)

            offered, rejected, reasons = self._discover(r, transport=transport)

            counters = RoundCounters(
                data_msgs=transport.data, control_msgs=transport.control,
                offered=offered, rejected=rejected,
                rej_invalid_pow=reasons["invalid_pow"], rej_too_young=reasons["too_young"],
                rej_low_score=reasons["low_score"], rej_bucket_full=reasons["bucket_full"],
                timeouts=timeouts)
            self.metrics.record(r, self.nodes, self.scenario, counters)

        return self.metrics.rows

    @staticmethod
    def true_mean(nodes):
        return sum(n.x_local for n in nodes.values()) / len(nodes)