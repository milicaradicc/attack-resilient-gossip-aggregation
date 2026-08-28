from __future__ import annotations

from core import round_ops
from metrics.experiment_metrics import RoundCounters


class Engine:
    # in-process pokretac: hrani zajednicku per-cvor logiku (core/round_ops.py)
    # podacima iz memorije; distribuirana verzija (docker/node_service.py) hrani
    # iste te funkcije podacima preko HTTP-a
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

    def _discover(self, round_now):
        offered = 0
        reasons = round_ops.empty_reasons()
        for node in self.nodes.values():
            # za svaki cvor, scenario ponudi kandidate (napadaci se guraju)
            candidates = self.scenario.offer_candidates(node, round_now, self.rng)
            n_off, _, node_reasons = round_ops.admit(node, candidates, self.sampling, round_now)
            offered += n_off
            for k, v in node_reasons.items():
                reasons[k] += v
        return offered, sum(reasons.values()), reasons

    def _broadcast(self, round_now):
        return round_ops.broadcast_snapshot(self.nodes, self.scenario, round_now)

    def _heartbeat(self, node, peers, round_now):
        return round_ops.heartbeat(node, peers, self.scenario, round_now,
                                   self.rng, self.timeout_rounds)

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
