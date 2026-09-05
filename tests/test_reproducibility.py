from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import spec_from
from experiments.matrix import run_single

# 4.10: isti eksperiment mora dati identican rezultat i izmedju POKRETANJA,
# ne samo unutar istog procesa. Ugradjeni hash() se ne sme koristiti kao izvor
# randomness-a jer je nasumican po procesu (PYTHONHASHSEED).

SNIPPET = (
    "import sys; sys.path.insert(0, {root!r});"
    "from core.config import spec_from;"
    "from experiments.matrix import run_single;"
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


if __name__ == "__main__":
    test_random_profile_reproducible_across_processes()
    test_all_profiles_reproducible_in_process()
    test_unresponsive_reproducible_across_processes()
    print("OK — deterministicka reproduktivnost (4.10) prolazi")