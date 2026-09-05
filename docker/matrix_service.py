from __future__ import annotations

import csv
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler

from docker.controller_service import ControllerState, _Server
from core.rng import make_rng
from core.config import RunSpec, load_matrix
from experiments.matrix import CONFIG_FIELDS, SUMMARY_FIELDS, summarize
from metrics.experiment_metrics import FIELDS, NODE_FIELDS


def _spec_state(spec: RunSpec) -> ControllerState:
    # ista priprema kao in-process; rng se poravnava sa matricom da bi
    # redosled ponuda bio identican
    return ControllerState(
        spec, rng=make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation))


class MatrixState:
    def __init__(self, config_path: str, verbose: bool = True):
        self.specs = load_matrix(config_path)
        self.verbose = verbose
        self.states = {}
        self.summaries = {}
        self.round_rows = {}
        self.node_rows = {}
        self.lock = threading.Lock()
        self.max_nodes = max(s.n_honest + sum(s.malicious_counts()) for s in self.specs)

    def state_for(self, job: int) -> ControllerState:
        with self.lock:
            st = self.states.get(job)
            if st is None:
                st = _spec_state(self.specs[job])
                self.states[job] = st
            return st

    def job_payload(self, job: int):
        spec = self.specs[job]
        st = self.state_for(job)
        payload = st.config_payload()
        payload["job"] = job
        payload["n_jobs"] = len(self.specs)
        payload["participants"] = st.n_total
        return payload

    def finalize(self, job: int) -> None:
        # dva izvestaja mogu istovremeno videti da je konfiguracija gotova,
        # pa se pod katancem preuzima vlasnistvo (states[job] = None) pre obrade
        with self.lock:
            st = self.states.get(job)
            if st is None or not st.complete():
                return
            self.states[job] = None
        spec = self.specs[job]
        prefix = [spec.n_honest, spec.beta, spec.overlay, spec.aggregation,
                  spec.byzantine_profile, spec.seed]
        summary = summarize(spec, st.metrics)
        self.summaries[job] = (prefix, summary)
        self.round_rows[job] = (prefix, st.metrics.to_csv_rows())
        if st.metrics.per_node:
            self.node_rows[job] = (prefix, st.metrics.node_csv_rows())
        if self.verbose:
            last = st.metrics.rows[-1]
            print(f"[{job + 1}/{len(self.specs)}] nh={spec.n_honest} beta={spec.beta} "
                  f"{spec.overlay} {spec.aggregation} seed={spec.seed} "
                  f"err={last.err_rel:.4e}", flush=True)

    def done(self) -> bool:
        return len(self.summaries) >= len(self.specs)

    def write(self, out_path: str, summary_path: str, json_path: str) -> None:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", newline="") as f_round, \
                open(summary_path, "w", newline="") as f_sum:
            w_round = csv.writer(f_round)
            w_sum = csv.writer(f_sum)
            w_round.writerow(CONFIG_FIELDS + FIELDS)
            w_sum.writerow(CONFIG_FIELDS + SUMMARY_FIELDS)
            for j in sorted(self.round_rows):
                prefix, rows = self.round_rows[j]
                for row in rows:
                    w_round.writerow(prefix + row)
            for j in sorted(self.summaries):
                prefix, summary = self.summaries[j]
                w_sum.writerow(prefix + summary)
        runs = []
        for j in sorted(self.summaries):
            prefix, summary = self.summaries[j]
            rows = self.round_rows[j][1]
            runs.append({
                "config": dict(zip(CONFIG_FIELDS, prefix)),
                "summary": dict(zip(SUMMARY_FIELDS, summary)),
                "rounds": [dict(zip(FIELDS, row)) for row in rows],
            })
        with open(json_path, "w") as f:
            json.dump({"runs": runs}, f)
        # per-node zapis (4.9) samo ako je trazen u konfiguraciji
        if self.node_rows:
            node_path = out_path.replace(".csv", "_nodes.csv")
            with open(node_path, "w", newline="") as f_node:
                w_node = csv.writer(f_node)
                w_node.writerow(CONFIG_FIELDS + NODE_FIELDS)
                for j in sorted(self.node_rows):
                    prefix, rows = self.node_rows[j]
                    for row in rows:
                        w_node.writerow(prefix + row)


def make_handler(matrix: MatrixState):
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
            if parts[0] == "jobs":
                self._send(200, {"n_jobs": len(matrix.specs), "max_nodes": matrix.max_nodes})
            elif parts[0] == "job":
                self._send(200, matrix.job_payload(int(parts[1])))
            elif parts[0] == "assignment":
                job, i = int(parts[1]), int(parts[2])
                st = matrix.state_for(job)
                self._send(200, {"node_id": i, **st.assignments[i]})
            elif parts[0] == "offers":
                job, i, r = int(parts[1]), int(parts[2]), int(parts[3])
                st = matrix.state_for(job)
                with st.lock:
                    st.maybe_build_offers(r)
                    ready = (r, i) in st.offers
                    offers = st.offers.get((r, i))
                self._send(200 if ready else 425,
                           {"offers": offers} if ready else {"ready": False})
            else:
                self._send(404, {})

        def do_POST(self):
            parts = self.path.strip("/").split("/")
            data = self._body()
            job = data.get("job", 0)
            st = matrix.state_for(job)
            if parts[0] == "peers":
                with st.lock:
                    st.peers_in.setdefault(data["round"], {})[data["node_id"]] = data["peers"]
                self._send(200, {"ok": True})
            elif parts[0] == "broadcast":
                with st.lock:
                    st.broadcasts.setdefault(data["round"], {})[data["node_id"]] = data["value"]
                self._send(200, {"ok": True})
            elif parts[0] == "values":
                r = data["round"]
                with st.lock:
                    ready = len(st.broadcasts.get(r, {})) == st.n_total
                    b = st.broadcasts.get(r, {})
                    out = {str(p): b[p] for p in data["peers"] if p in b} if ready else None
                self._send(200 if ready else 425, {"values": out} if ready else {"ready": False})
            elif parts[0] == "report":
                with st.lock:
                    st.reports.setdefault(data["round"], {})[data["node_id"]] = data
                    st.maybe_record(data["round"])
                    finished = st.complete()
                if finished:
                    matrix.finalize(job)
                self._send(200, {"ok": True})
            else:
                self._send(404, {})

    return Handler


def serve(matrix: MatrixState, host: str, port: int):
    return _Server((host, port), make_handler(matrix))


def main():
    config_path = os.environ.get("MATRIX_CONFIG", "configs/smoke.json")
    config_name = os.path.splitext(os.path.basename(config_path))[0]
    out = os.environ.get("MATRIX_OUT", f"results/docker/{config_name}.csv")
    summary = out.replace(".csv", "_summary.csv")
    json_path = out.replace(".csv", ".json")
    matrix = MatrixState(config_path)
    port = int(os.environ.get("PORT", "8000"))
    server = serve(matrix, "0.0.0.0", port)
    print(f"matrix controller up: {len(matrix.specs)} konfiguracija, "
          f"max_nodes={matrix.max_nodes}, config={config_path}", flush=True)

    def watch():
        while not matrix.done():
            time.sleep(0.2)
        matrix.write(out, summary, json_path)
        print(f"matrix complete: {len(matrix.summaries)} konfiguracija -> {summary}", flush=True)

    threading.Thread(target=watch, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()