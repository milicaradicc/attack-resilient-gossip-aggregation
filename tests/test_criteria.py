from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import spec_from
from in_process.matrix import run_single
from metrics.criteria import CRITERIA, evaluate_row
from metrics.export import SUMMARY_FIELDS, summarize


def _summary_row(spec):
    # jedno pokretanje svedeno na red sazetka, kao sto ga vidi izvestaj
    metrics = run_single(spec)
    row = dict(zip(SUMMARY_FIELDS, summarize(spec, metrics)))
    row["beta"] = spec.beta
    row["overlay"] = spec.overlay
    row["aggregation"] = spec.aggregation
    return row


def test_criteria_cover_all_five_thresholds():
    # pragovi moraju odgovarati specifikaciji; promena bilo kog od njih menja
    # znacenje rezultata u poglavlju 7, pa je ovde zakljucana
    ocekivano = {
        "3.10.1": ("final_sybil_penetration", 0.20),
        "3.10.2": ("final_eclipse_rate", 0.10),
        "3.10.3": ("final_err_rel", 0.05),
        "3.10.4": ("stability", 0.01),
        "3.10.5": ("convergence_time", 20),
    }
    assert {c.spec for c in CRITERIA} == set(ocekivano)
    for c in CRITERIA:
        kljuc, prag = ocekivano[c.spec]
        assert c.key == kljuc and c.limit == prag, f"{c.spec} ne odgovara 3.10"


def test_never_converged_counts_as_failure():
    # convergence_time = -1 znaci da sistem nikada nije trajno dostigao prag;
    # to mora biti PAD, a ne "bez podatka" (inace bi divergentan sistem prosao)
    assert evaluate_row({"convergence_time": -1})["3.10.5"] is False
    assert evaluate_row({"convergence_time": 11})["3.10.5"] is True
    assert evaluate_row({"convergence_time": 25})["3.10.5"] is False


def test_protected_overlay_meets_criteria():
    # zasticena postavka na gornjoj granici iz 3.10 (beta = 0.30) mora da
    # zadovolji sve kriterijume — to je tvrdnja koju rad brani
    spec = spec_from(n_honest=15, beta=0.3, overlay="eclipse_resistant",
                     aggregation="trimmed_mean", seed=1, num_rounds=50)
    ocene = evaluate_row(_summary_row(spec))
    pali = [spec_id for spec_id, ok in ocene.items() if ok is False]
    assert not pali, f"zasticena postavka obara kriterijume: {pali}"


def test_baseline_fails_at_least_one_criterion():
    # kontrola: bez ikakve zastite bar jedan kriterijum mora pasti, inace
    # provera ne bi razlikovala zasticen sistem od nezasticenog
    spec = spec_from(n_honest=15, beta=0.3, overlay="random",
                     aggregation="mean", seed=1, num_rounds=50)
    ocene = evaluate_row(_summary_row(spec))
    pali = [spec_id for spec_id, ok in ocene.items() if ok is False]
    assert pali, "baseline bez zastite prolazi sve kriterijume — provera ne razlikuje nista"


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — provera kriterijuma iz 3.10 prolazi")