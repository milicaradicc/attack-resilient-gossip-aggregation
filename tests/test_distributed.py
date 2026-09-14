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
        self.addresses = {}
        self.lock = threading.Lock()

    def register_address(self, node_id, url):
        with self.lock:
            self.addresses[int(node_id)] = url

    def all_addresses(self):
        with self.lock:
            if len(self.addresses) < self.max_nodes:
                return None
            return {str(k): v for k, v in self.addresses.items()}

    def done(self):
        return self.state.complete()

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
    from core.config import spec_from
    spec = spec_from(n_honest=12, beta=0.3, overlay="random", aggregation="mean",
                     seed=1, num_rounds=20, activate_round=1, pow_difficulty_bits=8,
                     byzantine_profile="random", delay_rounds=2)
    d = _distributed(spec)
    i = run_single(spec).rows[-1]
    assert abs(d.err_rel - i.err_rel) < 1e-9


def test_distributed_churn_matches_inprocess():
    from core.config import spec_from
    spec = spec_from(n_honest=12, beta=0.3, overlay="sybil_resistant",
                     aggregation="mean", seed=1, num_rounds=20, activate_round=1,
                     pow_difficulty_bits=8, churn_period=5, churn_offline=2,
                     timeout_rounds=3)
    d = _distributed(spec)
    i = run_single(spec).rows[-1]
    assert abs(d.err_rel - i.err_rel) < 1e-9
    assert abs(d.sybil_penetration - i.sybil_penetration) < 1e-9


def test_unresponsive_attacker_is_silent_in_both_paths():
    from core.config import spec_from
    common = dict(n_honest=12, beta=0.3, overlay="random", aggregation="mean",
                  seed=1, num_rounds=15, activate_round=1, pow_difficulty_bits=8,
                  timeout_rounds=3)
    spec = spec_from(unresponsive_p=0.8, **common)
    d = _distributed(spec)
    i = run_single(spec).rows[-1]
    assert abs(d.err_rel - i.err_rel) < 1e-9
    assert abs(d.sybil_penetration - i.sybil_penetration) < 1e-9

    silent = run_single(spec)
    talking = run_single(spec_from(unresponsive_p=0.0, **common))
    assert sum(r.timeouts for r in silent.rows) > 0, (
        "an unresponsive attacker never triggered a timeout")
    assert sum(r.data_msgs for r in silent.rows) < sum(
        r.data_msgs for r in talking.rows), "silence did not reduce the value traffic"


def test_reported_peer_set_is_the_post_churn_one():
    from core.config import spec_from
    spec = spec_from(n_honest=12, beta=0.3, overlay="random", aggregation="mean",
                     seed=1, num_rounds=16, activate_round=1, pow_difficulty_bits=8,
                     churn_period=4, churn_offline=2, timeout_rounds=3)
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

    scenario = matrix.state.scenario
    checked = 0
    for r, reported in matrix.state.peers_in.items():
        away = scenario.offline_ids(r)
        if not away:
            continue
        for node_id, peers in reported.items():
            leftover = away & set(peers)
            assert not leftover, (
                f"round {r}, node {node_id}: reported peer set still holds "
                f"departed identities {leftover} - POST /peers ran before before_round")
            checked += 1
    assert checked, "no round with a departure was observed - the test proves nothing"


if __name__ == "__main__":
    test_distributed_benign_matches_inprocess()
    test_distributed_attack_matches_inprocess()
    test_distributed_eclipse_matches_inprocess()
    test_distributed_delay_matches_inprocess()
    test_distributed_churn_matches_inprocess()
    test_unresponsive_attacker_is_silent_in_both_paths()
    test_reported_peer_set_is_the_post_churn_one()
    print("OK - the distributed system (benign + attack) reproduces in-process")