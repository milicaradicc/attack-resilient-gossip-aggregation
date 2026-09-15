from __future__ import annotations

import argparse
import csv
import json
import os
from typing import List

from aggregation import get_aggregation
from core.rng import make_rng
from core.config import RunSpec, load_matrix
from in_process.engine import Engine
from core.setup import build_world
from metrics.event_trace import TRACE_FIELDS, EventTrace
from metrics.experiment_metrics import FIELDS, NODE_FIELDS, ExperimentMetrics
from metrics.export import (CONFIG_FIELDS, SUMMARY_FIELDS, summarize,
                            varying_fields)
from sampling import get_strategy


def run_single(spec: RunSpec, trace: EventTrace = None) -> ExperimentMetrics:
    world = build_world(spec)

    metrics = ExperimentMetrics(x_star=world.x_star, num_buckets=spec.num_buckets,
                                per_node=spec.per_node_metrics)
    sampling = get_strategy(spec.overlay, spec.peer_set_size, world.id_params, spec.seed,
                            spec.gossip_fanout)
    agg_kwargs = {"alpha": spec.trim_alpha} if spec.aggregation == "trimmed_mean" else {}
    aggregation = get_aggregation(spec.aggregation, **agg_kwargs)
    rng = make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation)

    engine = Engine(world.nodes, aggregation, sampling, world.scenario, spec.num_rounds,
                    metrics, rng, world.nonces, timeout_rounds=spec.timeout_rounds, trace=trace)
    engine.run()
    return metrics


def run_matrix(config_path: str, out_path: str, summary_path: str, json_path: str = None) -> int:
    specs = load_matrix(config_path)
    extra = varying_fields(specs)
    config_fields = CONFIG_FIELDS + extra
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    json_runs = []
    node_path = out_path.replace(".csv", "_nodes.csv") if any(
        sp.per_node_metrics for sp in specs) else None
    f_node = open(node_path, "w", newline="") if node_path else None
    w_node = csv.writer(f_node) if f_node else None
    if w_node:
        w_node.writerow(config_fields + NODE_FIELDS)
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
            for row in rows:
                w_round.writerow(prefix(spec) + row)
            summary = summarize(spec, metrics)
            w_sum.writerow(prefix(spec) + summary)
            json_runs.append({
                "config": dict(zip(config_fields, prefix(spec))),
                "summary": dict(zip(SUMMARY_FIELDS, summary)),
                "rounds": [dict(zip(FIELDS, row)) for row in rows],
            })
            if w_node:
                for row in metrics.node_csv_rows():
                    w_node.writerow(prefix(spec) + row)
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
    n = run_matrix(args.config, args.out, summary, json_path)
    print(f"done: {n} runs -> {args.out} , {summary} , {json_path}")


if __name__ == "__main__":
    main()