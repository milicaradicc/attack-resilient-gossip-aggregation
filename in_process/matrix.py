from __future__ import annotations

import argparse
import csv
import json
import os
from typing import List

from aggregation import get_aggregation
from core.rng import make_rng
from core.config import SWEEPABLE, RunSpec, load_matrix
from in_process.engine import Engine
from core.setup import build_world
from metrics.event_trace import TRACE_FIELDS, EventTrace
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


def run_single(spec: RunSpec, trace: EventTrace = None) -> ExperimentMetrics:
    world = build_world(spec)

    # metrika za merenje rezultata
    metrics = ExperimentMetrics(x_star=world.x_star, num_buckets=spec.num_buckets,
                                per_node=spec.per_node_metrics)

    # sampling strategija
    sampling = get_strategy(spec.overlay, spec.peer_set_size, world.registry, world.id_params)

    # za agregaciju (ako je trimmed prosledjuje se alfa)
    agg_kwargs = {"alpha": spec.trim_alpha} if spec.aggregation == "trimmed_mean" else {}
    aggregation = get_aggregation(spec.aggregation, **agg_kwargs)

    # random generator
    rng = make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation)

    engine = Engine(world.nodes, aggregation, sampling, world.scenario, spec.num_rounds,
                    metrics, rng, timeout_rounds=spec.timeout_rounds, trace=trace)
    engine.run()
    return metrics


def summarize(spec: RunSpec, metrics: ExperimentMetrics) -> List:
    last = metrics.rows[-1]
    b = metrics.rejection_breakdown()
    return [
        last.err_rel,
        metrics.convergence_time(spec.epsilon, since=spec.activate_round),
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
    return [k for k in SWEEPABLE if len({getattr(sp, k) for sp in specs}) > 1]


def run_matrix(config_path: str, out_path: str, summary_path: str, json_path: str = None) -> int:
    specs = load_matrix(config_path)
    extra = varying_fields(specs)
    config_fields = CONFIG_FIELDS + extra
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    json_runs = []

    # po cvoru
    node_path = out_path.replace(".csv", "_nodes.csv") if any(
        sp.per_node_metrics for sp in specs) else None
    f_node = open(node_path, "w", newline="") if node_path else None
    w_node = csv.writer(f_node) if f_node else None
    if w_node:
        w_node.writerow(config_fields + NODE_FIELDS)

    # putanja
    trace_path = out_path.replace(".csv", "_trace.csv") if any(
        sp.trace_events for sp in specs) else None
    f_trace = open(trace_path, "w", newline="") if trace_path else None
    w_trace = csv.writer(f_trace) if f_trace else None
    if w_trace:
        w_trace.writerow(config_fields + TRACE_FIELDS)

    with open(out_path, "w", newline="") as f_round, open(summary_path, "w", newline="") as f_sum:
        w_round = csv.writer(f_round)
        w_sum = csv.writer(f_sum)
        w_round.writerow(config_fields + FIELDS)
        w_sum.writerow(config_fields + SUMMARY_FIELDS)
        prefix = lambda s: ([s.n_honest, s.beta, s.overlay, s.aggregation,
                             s.byzantine_profile, s.seed]
                            + [getattr(s, k) for k in extra])
        for i, spec in enumerate(specs, 1):
            trace = EventTrace() if spec.trace_events else None
            metrics = run_single(spec, trace=trace)
            rows = metrics.to_csv_rows()
            # upisuje runde
            for row in rows:
                w_round.writerow(prefix(spec) + row)
            summary = summarize(spec, metrics)
            w_sum.writerow(prefix(spec) + summary)
            json_runs.append({
                "config": dict(zip(config_fields, prefix(spec))),
                "summary": dict(zip(SUMMARY_FIELDS, summary)),
                "rounds": [dict(zip(FIELDS, row)) for row in rows],
            })
            # upisuje po cvoru
            if w_node:
                for row in metrics.node_csv_rows():
                    w_node.writerow(prefix(spec) + row)
            # putanju
            if w_trace and trace is not None:
                for row in trace.csv_rows():
                    w_trace.writerow(prefix(spec) + row)
            print(f"[{i}/{len(specs)}] nh={spec.n_honest} beta={spec.beta} "
                  f"{spec.overlay} {spec.aggregation} seed={spec.seed}")
    if f_node:
        f_node.close()
    if f_trace:
        f_trace.close()
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
    out = args.out or os.path.join(
        "results", "inprocess",
        os.path.splitext(os.path.basename(args.config))[0] + ".csv")
    args.out = out
    summary = args.summary or args.out.replace(".csv", "_summary.csv")
    json_path = args.json or args.out.replace(".csv", ".json")
    print("evo: ", args.out)
    n = run_matrix(args.config, args.out, summary, json_path)
    print(f"done: {n} runs -> {args.out} , {summary} , {json_path}")


if __name__ == "__main__":
    main()