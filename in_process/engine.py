from __future__ import annotations

from core import messages, round_ops
from core.transport import Transport
from metrics.experiment_metrics import RoundCounters


class Engine:
    # in-process pokretac: hrani zajednicku per-cvor logiku (core/round_ops.py)
    # podacima iz memorije; distribuirana verzija (docker/node_service.py) hrani
    # iste te funkcije podacima preko HTTP-a
    def __init__(self, nodes, aggregation, sampling, scenario, num_rounds, metrics, rng,
                 nonces, timeout_rounds: int = 0, trace=None):
        self.nodes = nodes
        self.aggregation = aggregation
        self.sampling = sampling
        self.scenario = scenario
        self.num_rounds = num_rounds
        self.metrics = metrics
        self.rng = rng
        # nonces: svaki identitet je vec sam resio svoj PoW (World.nonces);
        # ovde sluzi samo da se sastavi peer_exchange poruka koju candidate
        # "salje" — admission (sampling) ovo nikad ne cita, samo ono sto
        # stigne u poruci (videti core/round_ops.py)
        self.nonces = nonces
        self.timeout_rounds = timeout_rounds
        self.trace = trace # 5.1.8: opcioni zapis dogadjaja

    def _discover(self, round_now, transport=None):
        offered = 0
        reasons = round_ops.empty_reasons()
        # 5.1.5: discovery je razmena — prvo svi cvorovi posalju zahtev i prime
        # ponude, pa tek onda svi odlucuju. Time isporuka ponuda ne zavisi od
        # redosleda obrade, isto kao kod vrednosti.
        for node in self.nodes.values():
            candidates = self.scenario.offer_candidates(node, round_now, self.rng)
            round_ops.request_peers(node, candidates, round_now, transport=transport,
                                    nonces=self.nonces)
        for node in self.nodes.values():
            n_off, _, node_reasons = round_ops.admit(node, self.sampling, round_now,
                                                     trace=self.trace,
                                                     transport=transport)
            offered += n_off
            for k, v in node_reasons.items():
                reasons[k] += v
        return offered, sum(reasons.values()), reasons

    def _emit(self, round_now):
        # vrednosti se zamrzavaju pre isporuke (tick barrier)
        return round_ops.emitted_values(self.nodes, self.scenario, round_now,
                                        trace=self.trace)

    def _heartbeat(self, node, peers, round_now, transport=None):
        return round_ops.heartbeat(node, peers, self.scenario, round_now,
                                   self.rng, self.timeout_rounds, trace=self.trace,
                                   transport=transport)

    def run(self):
        # sacuvaj prvu rundu
        self.metrics.record(0, self.nodes, self.scenario, RoundCounters())

        for r in range(1, self.num_rounds + 1):
            # churn
            self.scenario.before_round(self.nodes, r)
            if (self.trace is not None and self.scenario.params.churn_period > 0
                    and r > 0 and r % self.scenario.params.churn_period == 0):
                self.trace.churn_reset(r, len(self.scenario.malicious_ids))
            if self.trace is not None and r == self.scenario.params.activate_round:
                self.trace.attack_activated(r, len(self.scenario.malicious_ids))
            # discover + admission
            # 5.1.5: sve poruke runde prolaze kroz transportni sloj
            transport = Transport()
            offered, rejected, reasons = self._discover(r, transport=transport)
            # na pocetku runce snimak
            emitted = self._emit(r) # vrednosti svih ucesnika, i napadaca
            own = {hid: n.estimate for hid, n in self.nodes.items()}

            data_msgs = 0
            timeouts = 0
            for hid, node in self.nodes.items():
                peers = self.sampling.select_gossip_peers(node, self.rng) # uzmi peerove za razmenu
                responders, t = self._heartbeat(node, peers, r, transport=transport)
                timeouts += t
                # svaki sused salje svoju vrednost kao zasebnu poruku ovom cvoru;
                # primalac je preuzima iz sanduceta i iz nje vadi vrednost
                round_ops.deliver(node, responders, emitted, r, transport=transport)
                incoming = transport.receive(hid, messages.AGGREGATE)
                received = [m.payload for m in incoming]
                data_msgs += len(received)
                node.estimate = self.aggregation.aggregate(own[hid], received) # nova procena
                if self.trace is not None:
                    self.trace.estimate(r, hid, node.estimate)

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