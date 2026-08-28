from __future__ import annotations

import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from docker.matrix_service import MatrixState, serve
from docker.node_service import run_matrix_node
from experiments.config import load_matrix
from experiments.matrix import run_single, summarize

CONFIG = os.path.join(ROOT, "configs", "tiny.json")


def _run_distributed(config_path):
    matrix = MatrixState(config_path, verbose=False)
    server = serve(matrix, "127.0.0.1", 0)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    workers = [threading.Thread(target=run_matrix_node, args=(base, i))
               for i in range(matrix.max_nodes)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=300)
    server.shutdown()
    return matrix


def test_matrix_in_containers_matches_inprocess():
    matrix = _run_distributed(CONFIG)
    specs = load_matrix(CONFIG)
    assert len(matrix.summaries) == len(specs)
    for j, spec in enumerate(specs):
        _, summary = matrix.summaries[j]
        expected = summarize(spec, run_single(spec))
        for a, b in zip(summary, expected):
            if isinstance(a, float) and isinstance(b, float):
                assert abs(a - b) < 1e-9


def test_matrix_results_ordered_by_config():
    matrix = _run_distributed(CONFIG)
    specs = load_matrix(CONFIG)
    for j, spec in enumerate(specs):
        prefix, _ = matrix.summaries[j]
        assert prefix[0] == spec.n_honest and prefix[2] == spec.overlay


if __name__ == "__main__":
    test_matrix_in_containers_matches_inprocess()
    test_matrix_results_ordered_by_config()
    print("OK — matrica u kontejnerima reprodukuje in-process rezultate")
