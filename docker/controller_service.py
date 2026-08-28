from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from statistics import mean

from attacks.scenario import AttackParams, Scenario
from core.rng import make_rng
from core.setup import RunConfig, build_nodes, register_all, seed_observations
from identity.registry import IdentityParams
from metrics.experiment_metrics import ExperimentMetrics, RoundCounters


# TODO: zasto kontroler nema prave node objekte pa pravi zamene
class _Stub:
    __slots__ = ("peers", "estimate")

    def __init__(self, peers, estimate):
        self.peers = list(peers) # kopija liste
        self.estimate = estimate # procena


class _OfferView:
    __slots__ = ("node_id", "peers")

    def __init__(self, node_id, peers):
        self.node_id = node_id
        self.peers = list(peers)


class ControllerState:
    def __init__(self, 
                cfg, 
                id_params, 
                strategy_name, 
                aggregation_name,
                n_byzantine, 
                n_sybil, 
                coordinated_value, 
                byzantine_profile,
                activate_round, 
                timeout_rounds, 
                unresponsive_p, 
                flooding,
                churn_period, 
                selective_p, 
                trim_alpha, 
                verbose=False,
                rng=None # matricni rezim salje isti rng kao in-process
                ):
        self.cfg = cfg
        self.id_params = id_params
        self.strategy_name = strategy_name
        self.aggregation_name = aggregation_name
        self.timeout_rounds = timeout_rounds
        self.trim_alpha = trim_alpha
        self.verbose = verbose

        nodes = build_nodes(cfg) # prave se honest cvorove sa pocetnim vrednostima  i topologijom (deterministicki, seed)
        seed_observations(nodes) # za svaki cvor se pisu pocetne observacije za komsije, starost krece od 0
        self.n = len(nodes)
        self.assignments = {i: {"x_local": n.x_local, "peers": list(n.peers)}
                            for i, n in nodes.items()}
        honest = set(nodes.keys()) # 0...n-1
        byzantine = set(range(self.n, self.n + n_byzantine)) # n...nb
        sybil = set(range(self.n + n_byzantine, self.n + n_byzantine + n_sybil))
        self.honest, self.byzantine, self.sybil = honest, byzantine, sybil
        self.n_total = self.n + n_byzantine + n_sybil
        self.registry = register_all(honest | byzantine | sybil, id_params)
        self.x_star = mean(n.x_local for n in nodes.values()) # prava srednja vrednost, sistem ovo treba da pogodi
        self.num_rounds = cfg.num_rounds

        self.params = AttackParams(
            byzantine_profile=byzantine_profile, 
            coordinated_value=coordinated_value,
            x_star=self.x_star, 
            activate_round=activate_round, 
            flooding=flooding,
            churn_period=churn_period, 
            selective_p=selective_p, 
            unresponsive_p=unresponsive_p)
        self.scenario = Scenario(honest, byzantine, sybil, self.params)
        # bez prosledjenog rng-a koristi se "attack" grana; matricni rezim salje
        # make_rng(seed, "matrix", overlay, aggregation) da redosled ponuda bude
        # identican in-process matrici
        self.rng = rng if rng is not None else make_rng(cfg.global_seed, "attack")

        self.peers_in = {}
        self.offers = {} # kes kandidata 
        self.offers_done = set()
        self.broadcasts = {}
        self.reports = {}
        self.recorded = {0} # runda 0 se belezi ispod, mora da udje da bi complete() bio tacan
        self.stubs = {i: _Stub(a["peers"], a["x_local"]) for i, a in self.assignments.items()}
        self.metrics = ExperimentMetrics(x_star=self.x_star, num_buckets=id_params.num_buckets)
        self.metrics.record(0, self.stubs, self.scenario, RoundCounters()) # ubelezi rundu 0 (pocetno stanje, prazni brojaci)
        self.rows = []
        self.lock = threading.Lock()

    def config_payload(self):
        return {
            "num_rounds": self.num_rounds, "n_honest": self.n,
            "strategy": self.strategy_name, "aggregation": self.aggregation_name,
            "trim_alpha": self.trim_alpha, "timeout_rounds": self.timeout_rounds,
            "peer_set_size": self.cfg.peer_set_size,
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
            elif parts[0] == "rows":
                self._send(200, {"rows": state.rows, "num_rounds": state.num_rounds,
                                 "x_star": state.x_star})
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
    n_honest = int(os.environ.get("N_HONEST", "15"))
    beta = float(os.environ.get("BETA", "0.3"))
    n_mal = round(n_honest * beta / (1.0 - beta)) if beta > 0 else 0
    n_byz = round(n_mal * float(os.environ.get("BYZANTINE_FRACTION", "0.34")))
    n_syb = n_mal - n_byz
    cfg = RunConfig(n_honest=n_honest, peer_set_size=int(os.environ.get("PEER_SET_SIZE", "7")),
                    num_rounds=int(os.environ.get("ROUNDS", "50")),
                    global_seed=int(os.environ.get("SEED", "42")))
    id_params = IdentityParams(pow_difficulty_bits=int(os.environ.get("POW_BITS", "12")),
                               num_buckets=int(os.environ.get("NUM_BUCKETS", "8")),
                               timeout_rounds=int(os.environ.get("TIMEOUT_ROUNDS", "3")))
    state = ControllerState(
        cfg, id_params, os.environ.get("STRATEGY", "eclipse_resistant"),
        os.environ.get("AGGREGATION", "trimmed_mean"), n_byz, n_syb,
        float(os.environ.get("COORDINATED_VALUE", "1000.0")),
        os.environ.get("BYZANTINE_PROFILE", "coordinated"),
        int(os.environ.get("WARMUP", "10")) + 1, id_params.timeout_rounds,
        float(os.environ.get("UNRESPONSIVE_P", "0.0")), int(os.environ.get("FLOODING", "0")),
        int(os.environ.get("CHURN_PERIOD", "0")), float(os.environ.get("SELECTIVE_P", "1.0")),
        float(os.environ.get("TRIM_ALPHA", "0.2")), verbose=True)
    port = int(os.environ.get("PORT", "8000"))
    server = serve(state, "0.0.0.0", port)
    print(f"controller up: n={state.n} byz={n_byz} sybil={n_syb} beta={beta} "
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
