from __future__ import annotations

import csv
import json
import os
import threading
import time

from docker.http_api import serve
from docker.run_state import ControllerState
from core.rng import make_rng
from core.config import RunSpec, load_matrix
from metrics.export import (CONFIG_FIELDS, SUMMARY_FIELDS, summarize,
                            varying_fields)
from metrics.event_trace import TRACE_FIELDS
from metrics.experiment_metrics import FIELDS, NODE_FIELDS


def _spec_state(spec: RunSpec) -> ControllerState:
    # ista priprema kao in-process; rng se poravnava sa matricom da bi
    # redosled ponuda bio identican
    return ControllerState(
        spec, rng=make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation))


class MatrixState:
    def __init__(self, config_path: str, verbose: bool = True):
        self.specs = load_matrix(config_path) # 540 eksp
        self.verbose = verbose
        self.states = {}

        self.summaries = {}
        self.round_rows = {}
        self.node_rows = {}
        self.trace_rows = {}

        self.lock = threading.Lock()
        self.max_nodes = max(s.n_honest + sum(s.malicious_counts()) for s in self.specs) # za kontejnere
        self.addresses = {}
        self.extra = varying_fields(self.specs) # za ablaciju
        self.config_fields = CONFIG_FIELDS + self.extra

    def register_address(self, node_id: int, url: str) -> None:
        with self.lock:
            self.addresses[int(node_id)] = url

    def all_addresses(self):

        with self.lock:
            if len(self.addresses) < self.max_nodes:
                return None
            return {str(k): v for k, v in self.addresses.items()}

    def state_for(self, job: int) -> ControllerState:
        with self.lock: # da se ne napravi vise statea
            st = self.states.get(job)
            if st is None:
                st = _spec_state(self.specs[job])
                self.states[job] = st
            return st

    def job_payload(self, job: int):
        # job payload = konfiguracija + redni broj posla + ukupan br + koliko ucesnika
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
        prefix = ([spec.n_honest, spec.beta, spec.overlay, spec.aggregation,
                   spec.byzantine_profile, spec.seed]
                  + [getattr(spec, k) for k in self.extra])
        summary = summarize(spec, st.metrics)
        self.summaries[job] = (prefix, summary)
        self.round_rows[job] = (prefix, st.metrics.to_csv_rows())
        if st.metrics.per_node:
            self.node_rows[job] = (prefix, st.metrics.node_csv_rows())
        if st.trace is not None:
            self.trace_rows[job] = (prefix, st.trace.csv_rows())
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
            w_round.writerow(self.config_fields + FIELDS)
            w_sum.writerow(self.config_fields + SUMMARY_FIELDS)
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
                "config": dict(zip(self.config_fields, prefix)),
                "summary": dict(zip(SUMMARY_FIELDS, summary)),
                "rounds": [dict(zip(FIELDS, row)) for row in rows],
            })
        with open(json_path, "w") as f:
            json.dump({"runs": runs}, f)
        # per-node zapis (4.9) samo ako je trazen u konfiguraciji
        if self.trace_rows:
            trace_path = out_path.replace(".csv", "_trace.csv")
            with open(trace_path, "w", newline="") as f_trace:
                w_trace = csv.writer(f_trace)
                w_trace.writerow(self.config_fields + TRACE_FIELDS)
                for j in sorted(self.trace_rows):
                    prefix, rows = self.trace_rows[j]
                    for row in rows:
                        w_trace.writerow(prefix + row)
        if self.node_rows:
            node_path = out_path.replace(".csv", "_nodes.csv")
            with open(node_path, "w", newline="") as f_node:
                w_node = csv.writer(f_node)
                w_node.writerow(self.config_fields + NODE_FIELDS)
                for j in sorted(self.node_rows):
                    prefix, rows = self.node_rows[j]
                    for row in rows:
                        w_node.writerow(prefix + row)
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