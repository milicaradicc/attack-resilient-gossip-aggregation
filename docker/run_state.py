from __future__ import annotations

import threading


from attacks.base import NO_MESSAGE
from core.rng import make_rng
from core.setup import build_world
from metrics.event_trace import EventTrace
from metrics.experiment_metrics import ExperimentMetrics, RoundCounters


class _Stub:
    __slots__ = ("peers", "estimate")

    def __init__(self, peers, estimate):
        self.peers = list(peers)
        self.estimate = estimate


def _row_to_event(row):
    from metrics.event_trace import TraceEvent
    return TraceEvent(row[0], row[1], row[2],
                      None if row[3] == "" else row[3],
                      row[4], None if row[5] == "" else row[5])


class _OfferView:
    __slots__ = ("node_id", "peers")

    def __init__(self, node_id, peers):
        self.node_id = node_id
        self.peers = list(peers)


class ControllerState:
    def __init__(self, spec, verbose=False, rng=None):
        self.spec = spec
        self.strategy_name = spec.overlay
        self.aggregation_name = spec.aggregation
        self.timeout_rounds = spec.timeout_rounds
        self.trim_alpha = spec.trim_alpha
        self.verbose = verbose

        world = build_world(spec)
        self.cfg = world.cfg
        self.id_params = world.id_params
        nodes = world.nodes
        self.n = len(nodes)
        self.assignments = {i: {"x_local": n.x_local, "peers": list(n.peers)}
                            for i, n in nodes.items()}
        self.honest, self.byzantine, self.sybil = world.honest, world.byzantine, world.sybil
        self.n_total = self.n + len(world.byzantine) + len(world.sybil)
        self.nonces = world.nonces
        self.x_star = world.x_star
        self.num_rounds = world.cfg.num_rounds
        self.scenario = world.scenario
        self.params = world.scenario.params

        self.rng = rng if rng is not None else make_rng(spec.seed, "attack")

        self.peers_in = {}
        self.offers = {} 
        self.offers_done = set()
        self.reports = {}
        self.recorded = {0} 
        self.stubs = {i: _Stub(a["peers"], a["x_local"]) for i, a in self.assignments.items()}
        self.metrics = ExperimentMetrics(x_star=self.x_star,
                                         num_buckets=world.id_params.num_buckets,
                                         per_node=spec.per_node_metrics)
        self.trace = EventTrace() if spec.trace_events else None
        self.metrics.record(0, self.stubs, self.scenario, RoundCounters()) 
        self.lock = threading.Lock()

    def config_payload(self):
        return {
            "num_rounds": self.num_rounds, "n_honest": self.n,
            "strategy": self.strategy_name, "aggregation": self.aggregation_name,
            "seed": self.spec.seed,
            "trim_alpha": self.trim_alpha, "timeout_rounds": self.timeout_rounds,
            "peer_set_size": self.cfg.peer_set_size,
            "trace_events": self.spec.trace_events,
            "honest": sorted(self.honest), "byzantine": sorted(self.byzantine),
            "sybil": sorted(self.sybil), "x_star": self.x_star,
            "nonces": {str(k): v for k, v in self.nonces.items()},
            "id_params": {
                "pow_difficulty_bits": self.id_params.pow_difficulty_bits,
                "age_min": self.id_params.age_min, 
                "age_max": self.id_params.age_max,
                "exchange_max": self.id_params.exchange_max,
                "reliability_max": self.id_params.reliability_max,
                "score_threshold": self.id_params.score_threshold,
                "num_buckets": self.id_params.num_buckets,
                "max_per_bucket": self.id_params.max_per_bucket,
                "timeout_rounds": self.id_params.timeout_rounds,
            },
            "attack": {
                "byzantine_profile": self.params.byzantine_profile,
                "coordinated_value": self.params.coordinated_value,
                "extreme_offset": self.params.extreme_offset,
                "random_low": self.params.random_low, 
                "random_high": self.params.random_high,
                "low_bias": self.params.low_bias, 
                "x_star": self.params.x_star,
                "experiment_seed": self.params.experiment_seed, 
                "activate_round": self.params.activate_round,
                "discovery_offers": self.params.discovery_offers,
                "flooding": self.params.flooding, 
                "churn_period": self.params.churn_period,
                "churn_offline": self.params.churn_offline,
                "selective_p": self.params.selective_p,
                "unresponsive_p": self.params.unresponsive_p,
                "eclipse_targets": self.params.eclipse_targets,
                "delay_rounds": self.params.delay_rounds,
            },
        }

    def maybe_build_offers(self, r):
        if r in self.offers_done or len(self.peers_in.get(r, {})) < self.n:
            return
        for i in range(self.n):
            view = _OfferView(i, self.peers_in[r][i])
            self.offers[(r, i)] = [[c, self.nonces.get(c)]
                                   for c in self.scenario.offer_candidates(view, r, self.rng)]
        self.offers_done.add(r)

    def maybe_record(self, r):
        if r in self.recorded or len(self.reports.get(r, {})) < self.n:
            return
        rep = self.reports[r]
        for i in range(self.n):
            self.stubs[i].peers = rep[i]["peers"]
            self.stubs[i].estimate = rep[i]["estimate"]
        agg = lambda key: sum(rep[i][key] for i in range(self.n))
        counters = RoundCounters(
            data_msgs=agg("data_msgs"), control_msgs=agg("control_msgs"),
            offered=agg("offered"), rejected=agg("rejected"),
            rej_invalid_pow=agg("rej_invalid_pow"), rej_too_young=agg("rej_too_young"),
            rej_low_score=agg("rej_low_score"), rej_bucket_full=agg("rej_bucket_full"),
            timeouts=agg("timeouts"))
        if self.trace is not None:
            if r == self.scenario.params.activate_round:
                self.trace.attack_activated(r, len(self.scenario.malicious_ids))
            returns = self.scenario.returning_count(r)
            if returns:
                self.trace.churn_reset(r, returns)
            if self.scenario.active(r):
                for m in sorted(self.scenario.malicious_ids):
                    value = self.scenario.broadcast_value(m, 0.0, r)
                    if value is not NO_MESSAGE:
                        self.trace.malicious_broadcast(
                            r, m, value, self.scenario.params.byzantine_profile)
            for i in range(self.n):
                for row in (rep[i].get("trace") or []):
                    self.trace.events.append(_row_to_event(row))
        m = self.metrics.record(r, self.stubs, self.scenario, counters)
        self.recorded.add(r)
        if self.verbose:
            print(f"  round {r:3d}/{self.num_rounds}: err={m.err_rel:.4e} "
                  f"sybil_pen={m.sybil_penetration:.3f} timeouts={counters.timeouts}", flush=True)

    def complete(self):
        return len(self.recorded) >= self.num_rounds + 1