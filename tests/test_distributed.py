from __future__ import annotations

import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from docker.controller_service import ControllerState, serve
from docker.node_service import run_node
from core.config import load_matrix
from experiments.matrix import run_single

TINY = os.path.join(ROOT, "configs", "tiny.json")


def _distributed(spec):
    st = ControllerState(spec)
    server = serve(st, "127.0.0.1", 0)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    total = st.n_total
    workers = [threading.Thread(target=run_node, args=(base, i)) for i in range(total)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=120)
    server.shutdown()
    return st.metrics.rows[-1]


def _spec(overlay, aggregation, beta):
    for s in load_matrix(TINY):
        if s.overlay == overlay and s.aggregation == aggregation and s.beta == beta:
            return s
    raise AssertionError("konfiguracija nije nadjena u tiny.json")


def test_distributed_benign_matches_inprocess():
    spec = _spec("random", "mean", 0.0)
    d = _distributed(spec)
    i = run_single(spec).rows[-1]
    assert abs(d.err_rel - i.err_rel) < 1e-9


def test_distributed_attack_matches_inprocess():
    spec = _spec("eclipse_resistant", "trimmed_mean", 0.3)
    d = _distributed(spec)
    i = run_single(spec).rows[-1]
    assert abs(d.err_rel - i.err_rel) < 1e-9
    assert abs(d.sybil_penetration - i.sybil_penetration) < 1e-9


if __name__ == "__main__":
    test_distributed_benign_matches_inprocess()
    test_distributed_attack_matches_inprocess()
    print("OK — distribuirani sistem (benigno + napad) reprodukuje in-process")
