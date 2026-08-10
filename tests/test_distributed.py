from __future__ import annotations

import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from docker.controller_service import ControllerState, serve
from docker.node_service import run_node
from experiments.scenarios import AttackConfig, run_attack, run_benign
from experiments.setup import RunConfig
from identity.registry import IdentityParams

BENIGN_ACTIVATE = 10 ** 9


def _distributed(cfg, idp, strat, agg, n_byz, n_syb, activate, alpha=0.2):
    st = ControllerState(cfg, idp, strat, agg, n_byz, n_syb, 1000.0, "coordinated",
                         activate, 0, 0.0, 0, 0, 1.0, alpha)
    server = serve(st, "127.0.0.1", 0)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    total = cfg.n_honest + n_byz + n_syb
    workers = [threading.Thread(target=run_node, args=(base, i)) for i in range(total)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=90)
    server.shutdown()
    return st.metrics.rows[-1]


def test_distributed_benign_matches_inprocess():
    cfg = RunConfig(n_honest=6, peer_set_size=5, num_rounds=15, global_seed=42)
    idp = IdentityParams(pow_difficulty_bits=8, num_buckets=8, timeout_rounds=0)
    d = _distributed(cfg, idp, "random", "mean", 0, 0, BENIGN_ACTIVATE)
    i = run_benign(cfg, "mean")[-1]
    assert abs(d.err_rel - i.err_rel) < 1e-9


def test_distributed_attack_matches_inprocess():
    cfg = RunConfig(n_honest=12, peer_set_size=7, num_rounds=20, global_seed=42)
    idp = IdentityParams(pow_difficulty_bits=8, num_buckets=8, timeout_rounds=0)
    d = _distributed(cfg, idp, "sybil_resistant", "mean", 2, 4, activate=1)
    ipc = AttackConfig(base=cfg, n_sybil=4, n_byzantine=2,
                       coordinated_value=1000.0, activate_round=1)
    i = run_attack(ipc, "sybil_resistant", "mean", idp)[-1]
    assert abs(d.err_rel - i.err_rel) < 1e-9
    assert abs(d.sybil_penetration - i.sybil_penetration) < 1e-9


if __name__ == "__main__":
    test_distributed_benign_matches_inprocess()
    test_distributed_attack_matches_inprocess()
    print("OK — distribuirani sistem (benigno + napad) reprodukuje in-process")
