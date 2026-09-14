from __future__ import annotations

from typing import List

from core.config import SWEEPABLE
from metrics.experiment_metrics import ExperimentMetrics

# 5.2.9: zajednicki opis izvoza rezultata.
#
# Oba pokretaca — in-process matrica (in_process/matrix.py) i distribuirani
# controller (docker/matrix.py) — pisu isti CSV/JSON format. Definicije kolona i
# sazimanje jednog pokretanja zato stoje ovde, u sloju modela, da se ne bi
# duplirali i vremenom razisli. Time izvoz iz dve putanje ostaje uporediv, sto je
# uslov za proveru da se putanje nisu razisle (5.9).
#
# Paket metrics namerno ne uvozi nista ni iz docker ni iz in_process — zavisnost
# ide samo u jednom smeru, od pokretaca ka modelu.

CONFIG_FIELDS = ["n_honest", "beta", "overlay", "aggregation", "byzantine_profile", "seed"]

SUMMARY_FIELDS = [
    "final_err_rel", # 6.3.1 relativna greska agregacije
    "convergence_time", # 6.3.2 vreme konvergencije
    "recovery_time", # prva runda od koje greska trajno ostaje ispod praga
    "stability", # 6.3.3 stabilnost procene
    "data_overhead", # 6.3.8 data overhead
    "control_overhead", # 6.3.7 kontrolni overhead
    "rejected_ratio", # 6.3.9 rejected peer ratio
    "bucket_occupancy", # 6.3.10 bucket occupancy distribucija
    "rej_pow",
    "rej_age",
    "rej_score",
    "rej_bucket",
    "final_sybil_penetration", # 6.3.4 sybil penetration
    "final_eclipse_rate", # 6.3.5 eclipse success rate
]
# 6.3.6 peer diversity se belezi po rundi (FIELDS), ne u sazetku


def summarize(spec, metrics: ExperimentMetrics) -> List:
    # jedno pokretanje svedeno na red sazetka; redosled prati SUMMARY_FIELDS
    last = metrics.rows[-1]
    b = metrics.rejection_breakdown()
    return [
        last.err_rel,
        metrics.convergence_time(spec.epsilon, since=spec.activate_round),
        metrics.recovery_time(spec.epsilon, since=spec.activate_round),
        metrics.stability(spec.conv_window_start),
        metrics.data_overhead(spec.n_honest),
        metrics.control_overhead(spec.n_honest),
        metrics.rejected_ratio(),
        metrics.mean_bucket_occupancy(),
        b["pow"], b["age"], b["score"], b["bucket"],
        last.sybil_penetration,
        last.eclipse_rate,
    ]


def varying_fields(specs) -> List[str]:
    # dopunski ablacioni scenariji svipuju i parametre napada; oni koji se menjaju
    # dodaju se kao kolone da bi se redovi mogli razlikovati
    return [k for k in SWEEPABLE if len({getattr(sp, k) for sp in specs}) > 1]
