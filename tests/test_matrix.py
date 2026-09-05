from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import RunSpec, load_matrix
from experiments.matrix import run_single


def _spec(beta, overlay="sybil_resistant", aggregation="median"):
    return RunSpec(
        n_honest=8, beta=beta, overlay=overlay, aggregation=aggregation, seed=1,
        peer_set_size=7, num_rounds=15, coordinated_value=1000.0, activate_round=1,
        pow_difficulty_bits=8, num_buckets=8, byzantine_fraction=0.34,
        epsilon=0.05, conv_window_start=8,
        byzantine_profile="coordinated", flooding=0, churn_period=0, selective_p=1.0,
        timeout_rounds=0, unresponsive_p=0.0,
    )


def test_load_matrix_count():
    specs = load_matrix(os.path.join(ROOT, "configs", "smoke.json"))
    assert len(specs) == 1 * 2 * 3 * 3 * 2


def test_benign_has_no_malicious():
    assert _spec(0.0).malicious_counts() == (0, 0)


def test_malicious_split():
    spec = RunSpec(10, 0.3, "random", "mean", 1, 7, 50, 1000.0, 1, 8, 8, 0.34, 0.05, 20,
                   "coordinated", 0, 0, 1.0, 0, 0.0)
    nb, ns = spec.malicious_counts()
    assert nb + ns == 4 and nb == 1 and ns == 3


def test_run_single_deterministic():
    a = run_single(_spec(0.3)).rows
    b = run_single(_spec(0.3)).rows
    assert len(a) == len(b)
    for ra, rb in zip(a, b):
        assert ra.err_rel == rb.err_rel
        assert ra.sybil_penetration == rb.sybil_penetration


def test_benign_converges_with_only_heartbeat_control():
    # 5.1.5: u benignom slucaju nema discovery ni admission saobracaja,
    # pa control poruke poticu iskljucivo od heartbeat provera
    m = run_single(_spec(0.0, overlay="random", aggregation="mean"))
    assert m.rows[-1].err_rel < 1e-2
    assert m.convergence_time(0.05) >= 1
    assert all(r.offered == 0 and r.rejected == 0 for r in m.rows)
    assert m.control_overhead(8) > 0.0
    assert m.data_overhead(8) > 0.0


def test_attack_has_control_overhead_and_rejections():
    m = run_single(_spec(0.3, overlay="sybil_resistant"))
    assert m.control_overhead(8) > 0.0
    assert 0.0 <= m.rejected_ratio() <= 1.0


def test_rejection_breakdown_sums_and_bucket_occupancy():
    m = run_single(_spec(0.3, overlay="eclipse_resistant"))
    b = m.rejection_breakdown()
    assert abs(sum(b.values()) - 1.0) < 1e-9 or sum(b.values()) == 0.0
    assert 0.0 <= m.mean_bucket_occupancy() <= 1.0


def test_json_export():
    import json
    import os
    from experiments.matrix import run_matrix
    out = os.path.join(ROOT, "results", "test_matrix.csv")
    js = os.path.join(ROOT, "results", "test_matrix.json")
    run_matrix(os.path.join(ROOT, "configs", "smoke.json"), out,
               out.replace(".csv", "_summary.csv"), js)
    data = json.load(open(js))
    assert "runs" in data and len(data["runs"]) == 36
    r0 = data["runs"][0]
    assert "config" in r0 and "summary" in r0 and "rounds" in r0
    os.remove(out); os.remove(out.replace(".csv", "_summary.csv")); os.remove(js)


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — testovi matrice prolaze")