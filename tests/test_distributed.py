from __future__ import annotations

import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.rng import make_rng
from docker.http_api import serve
from docker.run_state import ControllerState
from docker.node import run_matrix_node
from core.config import load_matrix
from in_process.matrix import run_single

TINY = os.path.join(ROOT, "configs", "tiny.json")


class _OneJob:
    # a minimal matrix of a single configuration: the HTTP layer
    # (docker/http_api.py) knows nothing about how many jobs there are, it only
    # asks for state_for/job_payload, so a full MatrixState loaded from a file is
    # not needed here
    def __init__(self, spec):
        self.specs = [spec]
        self.state = ControllerState(
            spec, rng=make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation),
            verbose=False)
        self.max_nodes = self.state.n_total

    def state_for(self, job):
        return self.state

    def job_payload(self, job):
        payload = self.state.config_payload()
        payload["job"] = 0
        payload["n_jobs"] = 1
        payload["participants"] = self.state.n_total
        return payload

    def finalize(self, job):
        return None


def _distributed(spec):
    matrix = _OneJob(spec)
    server = serve(matrix, "127.0.0.1", 0)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    workers = [threading.Thread(target=run_matrix_node, args=(base, i))
               for i in range(matrix.max_nodes)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=120)
    server.shutdown()
    return matrix.state.metrics.rows[-1]


def _tiny(beta):
    # a configuration loaded from file, the same way the matrix loads it
    for s in load_matrix(TINY):
        if s.beta == beta:
            return s
    raise AssertionError(f"beta={beta} not found in tiny.json")


def test_distributed_benign_matches_inprocess():
    spec = _tiny(0.0)
    d = _distributed(spec)
    i = run_single(spec).rows[-1]
    assert abs(d.err_rel - i.err_rel) < 1e-9


def test_distributed_attack_matches_inprocess():
    spec = _tiny(0.2)
    d = _distributed(spec)
    i = run_single(spec).rows[-1]
    assert abs(d.err_rel - i.err_rel) < 1e-9
    assert abs(d.sybil_penetration - i.sybil_penetration) < 1e-9


def test_distributed_eclipse_matches_inprocess():
    from core.config import spec_from
    spec = spec_from(n_honest=12, beta=0.3, overlay="eclipse_resistant",
                     aggregation="trimmed_mean", seed=1, num_rounds=20,
                     activate_round=1, pow_difficulty_bits=8, eclipse_targets=2)
    d = _distributed(spec)
    i = run_single(spec).rows[-1]
    assert abs(d.err_rel - i.err_rel) < 1e-9
    assert abs(d.eclipse_rate - i.eclipse_rate) < 1e-9


def test_distributed_delay_matches_inprocess():
    # 3.9: the delay attack holds a message back, so in some rounds a participant
    # sends nothing; the barrier in distributed mode must tolerate that without
    # the two paths diverging
    from core.config import spec_from
    spec = spec_from(n_honest=12, beta=0.3, overlay="random", aggregation="mean",
                     seed=1, num_rounds=20, activate_round=1, pow_difficulty_bits=8,
                     byzantine_profile="random", delay_rounds=2)
    d = _distributed(spec)
    i = run_single(spec).rows[-1]
    assert abs(d.err_rel - i.err_rel) < 1e-9


def test_distributed_churn_matches_inprocess():
    # 3.8: a churn departure changes the peer sets (ChurnAttack.before_round) and
    # the candidate offer (Scenario.offer_candidates). Both places exist in the
    # distributed path too - the node removes the absent neighbour itself, and the
    # controller filters the offer - so the result must match the in-process path
    from core.config import spec_from
    spec = spec_from(n_honest=12, beta=0.3, overlay="sybil_resistant",
                     aggregation="mean", seed=1, num_rounds=20, activate_round=1,
                     pow_difficulty_bits=8, churn_period=5, churn_offline=2,
                     timeout_rounds=3)
    d = _distributed(spec)
    i = run_single(spec).rows[-1]
    assert abs(d.err_rel - i.err_rel) < 1e-9
    assert abs(d.sybil_penetration - i.sybil_penetration) < 1e-9


if __name__ == "__main__":
    test_distributed_benign_matches_inprocess()
    test_distributed_attack_matches_inprocess()
    test_distributed_eclipse_matches_inprocess()
    test_distributed_delay_matches_inprocess()
    test_distributed_churn_matches_inprocess()
    print("OK - the distributed system (benign + attack) reproduces in-process")