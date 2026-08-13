from __future__ import annotations

import argparse
import csv
import json
import os
from typing import List

from aggregation import get_aggregation
from attacks.scenario import AttackParams, Scenario
from core.rng import make_rng
from experiments.config import RunSpec, load_matrix
from experiments.engine import Engine
from core.setup import RunConfig, build_nodes, seed_observations, register_all
from identity.registry import IdentityParams, IdentityRegistry
from metrics.experiment_metrics import FIELDS, ExperimentMetrics
from sampling import get_strategy

CONFIG_FIELDS = ["n_honest", "beta", "overlay", "aggregation", "byzantine_profile", "seed"]

SUMMARY_FIELDS = [
    "final_err_rel", # relativna greska agregacije
    "convergence_time", # vreme konvergencije
    "stability", # stabilnost procene 
    "data_overhead", # 6.3.8  data overhead
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
# 6.3.6 peer diversity

def run_single(spec: RunSpec) -> ExperimentMetrics:
    base = RunConfig(
        n_honest=spec.n_honest,
        peer_set_size=spec.peer_set_size,
        num_rounds=spec.num_rounds,
        global_seed=spec.seed,
    )
    nodes = build_nodes(base)
    seed_observations(nodes)

    honest = set(nodes.keys())
    n_byzantine, n_sybil = spec.malicious_counts()
    b0 = spec.n_honest
    byzantine = set(range(b0, b0 + n_byzantine))
    sybil = set(range(b0 + n_byzantine, b0 + n_byzantine + n_sybil))

    id_params = IdentityParams(
        pow_difficulty_bits=spec.pow_difficulty_bits,
        num_buckets=spec.num_buckets,
    )
    registry = register_all(honest | byzantine | sybil, id_params)

    x_star = Engine.true_mean(nodes)
    if n_byzantine + n_sybil == 0:
        scenario = Scenario.benign(honest)
    else:
        scenario = Scenario(honest, byzantine, sybil, AttackParams(
            byzantine_profile=spec.byzantine_profile,
            coordinated_value=spec.coordinated_value,
            x_star=x_star,
            activate_round=spec.activate_round,
            flooding=spec.flooding,
            churn_period=spec.churn_period,
            selective_p=spec.selective_p,
            unresponsive_p=spec.unresponsive_p,
        ))

    metrics = ExperimentMetrics(x_star=x_star, num_buckets=spec.num_buckets)
    sampling = get_strategy(spec.overlay, spec.peer_set_size, registry, id_params)
    agg_kwargs = {"alpha": spec.trim_alpha} if spec.aggregation == "trimmed_mean" else {}
    aggregation = get_aggregation(spec.aggregation, **agg_kwargs)
    rng = make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation)

    engine = Engine(nodes, aggregation, sampling, scenario, spec.num_rounds, metrics, rng,
                    timeout_rounds=spec.timeout_rounds)
    engine.run()
    return metrics


def summarize(spec: RunSpec, metrics: ExperimentMetrics) -> List:
    last = metrics.rows[-1]
    b = metrics.rejection_breakdown()
    return [
        last.err_rel,
        metrics.convergence_time(spec.epsilon),
        metrics.stability(spec.conv_window_start),
        metrics.data_overhead(spec.n_honest),
        metrics.control_overhead(spec.n_honest),
        metrics.rejected_ratio(),
        metrics.mean_bucket_occupancy(),
        b["pow"], b["age"], b["score"], b["bucket"],
        last.sybil_penetration,
        last.eclipse_rate,
    ]


def run_matrix(config_path: str, out_path: str, summary_path: str, json_path: str = None) -> int:
    specs = load_matrix(config_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    json_runs = []
    with open(out_path, "w", newline="") as f_round, open(summary_path, "w", newline="") as f_sum:
        w_round = csv.writer(f_round)
        w_sum = csv.writer(f_sum)
        w_round.writerow(CONFIG_FIELDS + FIELDS)
        w_sum.writerow(CONFIG_FIELDS + SUMMARY_FIELDS)
        prefix = lambda s: [s.n_honest, s.beta, s.overlay, s.aggregation, s.byzantine_profile, s.seed]
        for i, spec in enumerate(specs, 1):
            metrics = run_single(spec)
            rows = metrics.to_csv_rows()
            for row in rows:
                w_round.writerow(prefix(spec) + row)
            summary = summarize(spec, metrics)
            w_sum.writerow(prefix(spec) + summary)
            json_runs.append({
                "config": dict(zip(CONFIG_FIELDS, prefix(spec))),
                "summary": dict(zip(SUMMARY_FIELDS, summary)),
                "rounds": [dict(zip(FIELDS, row)) for row in rows],
            })
            print(f"[{i}/{len(specs)}] nh={spec.n_honest} beta={spec.beta} "
                  f"{spec.overlay} {spec.aggregation} seed={spec.seed}")
    if json_path:
        with open(json_path, "w") as f:
            json.dump({"runs": json_runs}, f)
    return len(specs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/smoke.json")
    parser.add_argument("--out", default="results/matrix.csv")
    parser.add_argument("--summary", default=None)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    summary = args.summary or args.out.replace(".csv", "_summary.csv")
    json_path = args.json or args.out.replace(".csv", ".json")
    n = run_matrix(args.config, args.out, summary, json_path)
    print(f"done: {n} runs -> {args.out} , {summary} , {json_path}")


if __name__ == "__main__":
    main()
