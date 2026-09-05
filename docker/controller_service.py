from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.rng import make_rng
from core.setup import build_world
from core.config import load_defaults, spec_from
from metrics.event_trace import EventTrace
from metrics.experiment_metrics import ExperimentMetrics, RoundCounters


# TODO: zasto kontroler nema prave node objekte pa pravi zamene
class _Stub:
    __slots__ = ("peers", "estimate")

    def __init__(self, peers, estimate):
        self.peers = list(peers) # kopija liste
        self.estimate = estimate # procena


def _row_to_event(row):
    # red iz izvestaja cvora nazad u dogadjaj (redosled polja: TRACE_FIELDS)
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
        # spec je RunSpec (experiments/config.py) — ista definicija konfiguracije
        # koju koristi i in-process matrica
        self.spec = spec
        self.strategy_name = spec.overlay
        self.aggregation_name = spec.aggregation
        self.timeout_rounds = spec.timeout_rounds
        self.trim_alpha = spec.trim_alpha
        self.verbose = verbose

        # svet se sklapa istom funkcijom kao u in-process matrici (core/setup.py)
        world = build_world(spec)
        self.cfg = world.cfg
        self.id_params = world.id_params
        nodes = world.nodes
        self.n = len(nodes)
        self.assignments = {i: {"x_local": n.x_local, "peers": list(n.peers)}
                            for i, n in nodes.items()}
        self.honest, self.byzantine, self.sybil = world.honest, world.byzantine, world.sybil
        self.n_total = self.n + len(world.byzantine) + len(world.sybil)
        self.registry = world.registry
        self.x_star = world.x_star
        self.num_rounds = world.cfg.num_rounds
        self.scenario = world.scenario
        self.params = world.scenario.params

        self.rng = rng if rng is not None else make_rng(spec.seed, "attack")

        self.peers_in = {}
        self.offers = {} # kes kandidata 
        self.offers_done = set()
        self.broadcasts = {}
        self.reports = {}
        self.recorded = {0} # runda 0 se belezi ispod, mora da udje da bi complete() bio tacan
        self.stubs = {i: _Stub(a["peers"], a["x_local"]) for i, a in self.assignments.items()}
        self.metrics = ExperimentMetrics(x_star=self.x_star,
                                         num_buckets=world.id_params.num_buckets,
                                         per_node=spec.per_node_metrics)
        self.trace = EventTrace() if spec.trace_events else None
        self.metrics.record(0, self.stubs, self.scenario, RoundCounters()) # ubelezi rundu 0 (pocetno stanje, prazni brojaci)
        self.lock = threading.Lock()

    def config_payload(self):
        return {
            "num_rounds": self.num_rounds, "n_honest": self.n,
            "strategy": self.strategy_name, "aggregation": self.aggregation_name,
            "trim_alpha": self.trim_alpha, "timeout_rounds": self.timeout_rounds,
            "peer_set_size": self.cfg.peer_set_size,
            "trace_events": self.spec.trace_events,
            "honest": sorted(self.honest), "byzantine": sorted(self.byzantine),
            "sybil": sorted(self.sybil), "x_star": self.x_star,
            "registry": {str(k): v for k, v in self.registry.nonces.items()},
            "id_params": {
                "pow_difficulty_bits": self.id_params.pow_difficulty_bits,
                "age_min": self.id_params.age_min, 
                "age_max": self.id_params.age_max,
                "exchange_max": self.id_params.exchange_max,
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
                "stale_value": self.params.stale_value,
                "x_star": self.params.x_star, 
                "activate_round": self.params.activate_round,
                "poison_honest_offers": self.params.poison_honest_offers,
                "flooding": self.params.flooding, 
                "churn_period": self.params.churn_period,
                "selective_p": self.params.selective_p,
                "unresponsive_p": self.params.unresponsive_p,
                "eclipse_targets": self.params.eclipse_targets,
            },
        }

    def maybe_build_offers(self, r):
        # ako su kandidati za ovu rundu vec napravljeni, ili jos nisu svi cvorovi prijavili komsije — izadji
        if r in self.offers_done or len(self.peers_in.get(r, {})) < self.n:
            return
        for i in range(self.n):
            view = _OfferView(i, self.peers_in[r][i])
            self.offers[(r, i)] = self.scenario.offer_candidates(view, r, self.rng)
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
            data_msgs=agg("data_msgs"), control_msgs=agg("offered") + agg("rejected"),
            offered=agg("offered"), rejected=agg("rejected"),
            rej_invalid_pow=agg("rej_invalid_pow"), rej_too_young=agg("rej_too_young"),
            rej_low_score=agg("rej_low_score"), rej_bucket_full=agg("rej_bucket_full"),
            timeouts=agg("timeouts"))
        if self.trace is not None:
            # aktivacija napada je dogadjaj sistema, belezi je controller jednom
            if r == self.scenario.params.activate_round:
                self.trace.attack_activated(r, len(self.scenario.malicious_ids))
            cp = self.scenario.params.churn_period
            if cp > 0 and r % cp == 0:
                self.trace.churn_reset(r, len(self.scenario.malicious_ids))
            # napadacke emisije zna controller (njemu stizu), pa ih on i belezi
            if self.scenario.active(r):
                sent = self.broadcasts.get(r, {})
                for m in sorted(self.scenario.malicious_ids):
                    if m in sent:
                        self.trace.malicious_broadcast(
                            r, m, sent[m], self.scenario.params.byzantine_profile)
            # dogadjaji stizu od cvorova; redosled je po id-u radi determinizma
            for i in range(self.n):
                for row in (rep[i].get("trace") or []):
                    self.trace.events.append(_row_to_event(row))
        m = self.metrics.record(r, self.stubs, self.scenario, counters)
        self.recorded.add(r)
        if self.verbose:
            print(f"  runda {r:3d}/{self.num_rounds}: err={m.err_rel:.4e} "
                  f"sybil_pen={m.sybil_penetration:.3f} timeouts={counters.timeouts}", flush=True)

    def complete(self):
        return len(self.recorded) >= self.num_rounds + 1


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            parts = self.path.strip("/").split("/")
            if parts[0] == "config":
                self._send(200, state.config_payload())
            elif parts[0] == "assignment":
                i = int(parts[1])
                self._send(200, {"node_id": i, **state.assignments[i]})
            elif parts[0] == "offers":
                i, r = int(parts[1]), int(parts[2])
                with state.lock:
                    state.maybe_build_offers(r)
                    ready = (r, i) in state.offers
                    offers = state.offers.get((r, i))
                self._send(200 if ready else 425, {"offers": offers} if ready else {"ready": False})
            else:
                self._send(404, {})

        def do_POST(self):
            parts = self.path.strip("/").split("/")
            data = self._body()
            if parts[0] == "peers":
                with state.lock:
                    state.peers_in.setdefault(data["round"], {})[data["node_id"]] = data["peers"]
                self._send(200, {"ok": True})
            elif parts[0] == "broadcast":
                with state.lock:
                    state.broadcasts.setdefault(data["round"], {})[data["node_id"]] = data["value"]
                self._send(200, {"ok": True})
            elif parts[0] == "values":
                r = data["round"]
                with state.lock:
                    ready = len(state.broadcasts.get(r, {})) == state.n_total
                    b = state.broadcasts.get(r, {})
                    out = {str(p): b[p] for p in data["peers"] if p in b} if ready else None
                self._send(200 if ready else 425, {"values": out} if ready else {"ready": False})
            elif parts[0] == "report":
                with state.lock:
                    state.reports.setdefault(data["round"], {})[data["node_id"]] = data
                    state.maybe_record(data["round"])
                self._send(200, {"ok": True})
            else:
                self._send(404, {})

    return Handler


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 256


def serve(state, host, port):
    return _Server((host, port), make_handler(state))


def _write_results(state, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    state.metrics.write_csv(path)


def main():
    # jedan scenario: env varijable su samo izmene u odnosu na configs/defaults.json
    d = load_defaults()
    env = lambda k, default: os.environ.get(k, str(default))
    spec = spec_from(
        n_honest=int(env("N_HONEST", d["n_honest"][0])),
        beta=float(env("BETA", d["beta"][0])),
        overlay=env("STRATEGY", d["overlay"][0]),
        aggregation=env("AGGREGATION", d["aggregation"][0]),
        seed=int(env("SEED", d["seeds"][0])),
        peer_set_size=int(env("PEER_SET_SIZE", d["peer_set_size"])),
        num_rounds=int(env("ROUNDS", d["num_rounds"])),
        coordinated_value=float(env("COORDINATED_VALUE", d["coordinated_value"])),
        activate_round=int(env("WARMUP", d["warmup"])) + 1,
        pow_difficulty_bits=int(env("POW_BITS", d["pow_difficulty_bits"])),
        num_buckets=int(env("NUM_BUCKETS", d["num_buckets"])),
        byzantine_fraction=float(env("BYZANTINE_FRACTION", d["byzantine_fraction"])),
        byzantine_profile=env("BYZANTINE_PROFILE", d["byzantine_profile"][0]),
        flooding=int(env("FLOODING", d["flooding"])),
        churn_period=int(env("CHURN_PERIOD", d["churn_period"])),
        selective_p=float(env("SELECTIVE_P", d["selective_p"])),
        timeout_rounds=int(env("TIMEOUT_ROUNDS", d["timeout_rounds"])),
        unresponsive_p=float(env("UNRESPONSIVE_P", d["unresponsive_p"])),
        trim_alpha=float(env("TRIM_ALPHA", d["trim_alpha"])),
        eclipse_targets=int(env("ECLIPSE_TARGETS", d["eclipse_targets"])),
    )
    n_byz, n_syb = spec.malicious_counts()
    state = ControllerState(spec, verbose=True)
    port = int(os.environ.get("PORT", "8000"))
    server = serve(state, "0.0.0.0", port)
    print(f"controller up: n={state.n} byz={n_byz} sybil={n_syb} beta={spec.beta} "
          f"strategy={state.strategy_name} agg={state.aggregation_name} x_star={state.x_star:.4f}",
          flush=True)

    def watch():
        while not state.complete():
            time.sleep(0.2)
        _write_results(state, "results/distributed.csv")
        last = state.metrics.rows[-1]
        print(f"run complete: final err_rel={last.err_rel:.4e} "
              f"sybil_pen={last.sybil_penetration:.3f} -> results/distributed.csv", flush=True)

    threading.Thread(target=watch, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()