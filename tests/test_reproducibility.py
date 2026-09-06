from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import spec_from
from core.rng import make_rng
from in_process.matrix import run_single

# 4.10: isti eksperiment mora dati identican rezultat i izmedju POKRETANJA,
# ne samo unutar istog procesa. Ugradjeni hash() se ne sme koristiti kao izvor
# randomness-a jer je nasumican po procesu (PYTHONHASHSEED).

SNIPPET = (
    "import sys; sys.path.insert(0, {root!r});"
    "from core.config import spec_from;"
    "from in_process.matrix import run_single;"
    "s = spec_from(n_honest=15, beta=0.2, overlay='eclipse_resistant',"
    " aggregation='mean', seed=1, num_rounds=20, activate_round=1,"
    " pow_difficulty_bits=8, byzantine_profile={profile!r});"
    "print(repr(run_single(s).rows[-1].err_rel))"
)


def _run_in_new_process(profile: str) -> str:
    out = subprocess.run([sys.executable, "-c", SNIPPET.format(root=ROOT, profile=profile)],
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_random_profile_reproducible_across_processes():
    # profil "random" bira vrednosti pseudo-slucajno; mora biti isti u svakom procesu
    first = _run_in_new_process("random")
    second = _run_in_new_process("random")
    assert first == second, f"{first} != {second}"


def test_all_profiles_reproducible_in_process():
    for profile in ("coordinated", "extreme", "random", "low_biased", "stale"):
        spec = spec_from(n_honest=12, beta=0.3, overlay="sybil_resistant",
                         aggregation="mean", seed=3, num_rounds=15, activate_round=1,
                         pow_difficulty_bits=8, byzantine_profile=profile)
        a = [r.err_rel for r in run_single(spec).rows]
        b = [r.err_rel for r in run_single(spec).rows]
        assert a == b, f"profil {profile} nije reproduktivan"


def test_unresponsive_reproducible_across_processes():
    # selective/unresponsive takodje koriste pseudo-slucajnost
    snippet = SNIPPET.replace("byzantine_profile={profile!r}",
                              "byzantine_profile='coordinated', unresponsive_p=0.5")
    cmd = [sys.executable, "-c", snippet.format(root=ROOT, profile="coordinated")]
    first = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    second = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout


def test_exported_files_are_identical():
    # 5.2.7: porede se i EKSPORTOVANI fajlovi — per-round, summary, per-node i trace
    import filecmp
    import json
    import tempfile
    from in_process.matrix import run_matrix

    config = os.path.join(ROOT, "configs", "tiny.json")
    with open(config) as f:
        base = json.load(f)
    base["per_node_metrics"] = True
    base["trace_events"] = True

    outputs = []
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = os.path.join(tmp, "replay.json")
        with open(cfg_path, "w") as f:
            json.dump(base, f)
        for run in ("a", "b"):
            out = os.path.join(tmp, f"{run}.csv")
            run_matrix(cfg_path, out, out.replace(".csv", "_summary.csv"),
                       out.replace(".csv", ".json"))
            outputs.append(out)

        for suffix in (".csv", "_summary.csv", ".json", "_nodes.csv", "_trace.csv"):
            first = outputs[0].replace(".csv", suffix)
            second = outputs[1].replace(".csv", suffix)
            assert os.path.exists(first), f"nedostaje {suffix}"
            assert filecmp.cmp(first, second, shallow=False), (
                f"eksportovani fajl {suffix} nije identican izmedju pokretanja")


def test_peer_selection_decisions_reproduce():
    # 5.2.7: peer selection odluke — redosled i sadrzaj ponuda mora biti isti
    from core.setup import build_world
    decisions = []
    for _ in range(2):
        spec = spec_from(n_honest=12, beta=0.3, overlay="eclipse_resistant",
                         aggregation="trimmed_mean", seed=5, num_rounds=10,
                         activate_round=1, pow_difficulty_bits=8)
        world = build_world(spec)
        rng = make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation)
        offers = []
        for round_now in range(1, spec.num_rounds + 1):
            for node in world.nodes.values():
                offers.append(tuple(world.scenario.offer_candidates(node, round_now, rng)))
        decisions.append(offers)
    assert decisions[0] == decisions[1]


if __name__ == "__main__":
    test_random_profile_reproducible_across_processes()
    test_all_profiles_reproducible_in_process()
    test_unresponsive_reproducible_across_processes()
    test_exported_files_are_identical()
    test_peer_selection_decisions_reproduce()
    print("OK — deterministicka reproduktivnost (4.10) prolazi")