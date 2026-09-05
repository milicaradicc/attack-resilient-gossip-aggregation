from __future__ import annotations

import argparse
import csv
import json
import os
from typing import List

from aggregation import get_aggregation
from core.rng import make_rng
from core.config import RunSpec, load_matrix
from core.engine import Engine
from core.setup import build_world
from metrics.experiment_metrics import FIELDS, NODE_FIELDS, ExperimentMetrics
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
    # svet (cvorovi, identiteti, PoW registar, scenario) sklapa se u core/setup.py,
    # istom funkcijom koju koristi i distribuirani controller
    world = build_world(spec)

    metrics = ExperimentMetrics(x_star=world.x_star, num_buckets=spec.num_buckets,
                                per_node=spec.per_node_metrics)
    sampling = get_strategy(spec.overlay, spec.peer_set_size, world.registry, world.id_params)
    agg_kwargs = {"alpha": spec.trim_alpha} if spec.aggregation == "trimmed_mean" else {}
    aggregation = get_aggregation(spec.aggregation, **agg_kwargs)
    rng = make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation)

    engine = Engine(world.nodes, aggregation, sampling, world.scenario, spec.num_rounds,
                    metrics, rng, timeout_rounds=spec.timeout_rounds)
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
    # per-node zapis (4.9) se pise samo kada je trazen u konfiguraciji,
    # jer nad punom matricom daje red velicine milion redova
    node_path = out_path.replace(".csv", "_nodes.csv") if any(
        sp.per_node_metrics for sp in specs) else None
    f_node = open(node_path, "w", newline="") if node_path else None
    w_node = csv.writer(f_node) if f_node else None
    if w_node:
        w_node.writerow(CONFIG_FIELDS + NODE_FIELDS)
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
            if w_node:
                for row in metrics.node_csv_rows():
                    w_node.writerow(prefix(spec) + row)
            print(f"[{i}/{len(specs)}] nh={spec.n_honest} beta={spec.beta} "
                  f"{spec.overlay} {spec.aggregation} seed={spec.seed}")
    if f_node:
        f_node.close()
    if json_path:
        with open(json_path, "w") as f:
            json.dump({"runs": json_runs}, f)
    return len(specs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/smoke.json")
    parser.add_argument("--out", default=None)
    parser.add_argument("--summary", default=None)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    # podrazumevano: results/inprocess/<ime configa>.csv
    out = args.out or os.path.join(
        "results", "inprocess",
        os.path.splitext(os.path.basename(args.config))[0] + ".csv")
    args.out = out
    summary = args.summary or args.out.replace(".csv", "_summary.csv")
    json_path = args.json or args.out.replace(".csv", ".json")
    n = run_matrix(args.config, args.out, summary, json_path)
    print(f"done: {n} runs -> {args.out} , {summary} , {json_path}")


if __name__ == "__main__":
    main()