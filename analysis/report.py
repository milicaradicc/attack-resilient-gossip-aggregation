from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.loader import filter_rows, group_stats, group_values, load

OVERLAYS = ["random", "sybil_resistant", "eclipse_resistant"]
AGGS = ["mean", "median", "trimmed_mean"]


def _cell(stats, key):
    m, s = stats.get(key, (float("nan"), 0.0))
    return f"{m:.3e} ± {s:.1e}"


def table_final_error(summary, beta, out_md):
    rows_b = filter_rows(summary, beta=beta)
    stats = group_stats(rows_b, ("overlay", "aggregation"), "final_err_rel")
    lines = [f"## Final err_rel (beta={beta}, mean ± std across seeds)", "",
             "| overlay \\ aggregation | " + " | ".join(AGGS) + " |",
             "|" + "---|" * (len(AGGS) + 1)]
    for ov in OVERLAYS:
        lines.append("| " + ov + " | " + " | ".join(_cell(stats, (ov, a)) for a in AGGS) + " |")
    with open(out_md, "a") as f:
        f.write("\n".join(lines) + "\n\n")


def table_penetration(summary, out_md):
    betas = sorted({r["beta"] for r in summary})
    stats = group_stats(summary, ("overlay", "beta"), "final_sybil_penetration")
    lines = ["## Sybil penetration by overlay x beta (mean across seeds)", "",
             "| overlay \\ beta | " + " | ".join(str(b) for b in betas) + " |",
             "|" + "---|" * (len(betas) + 1)]
    for ov in OVERLAYS:
        cells = []
        for b in betas:
            m, _ = stats.get((ov, b), (float("nan"), 0.0))
            cells.append(f"{m:.3f}")
        lines.append("| " + ov + " | " + " | ".join(cells) + " |")
    with open(out_md, "a") as f:
        f.write("\n".join(lines) + "\n\n")


def fig_err_over_time(round_rows, beta, out_dir):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, agg in zip(axes, ["mean", "median"]):
        sub = filter_rows(round_rows, beta=beta, aggregation=agg)
        for ov in OVERLAYS:
            series = group_stats(filter_rows(sub, overlay=ov), ("round",), "err_rel")
            xs = sorted(series)
            ys = [series[x][0] for x in xs]
            ax.plot([x[0] for x in xs], ys, label=ov)
        ax.set_title(f"aggregation = {agg}")
        ax.set_xlabel("round")
        ax.set_yscale("log")
        ax.legend()
    axes[0].set_ylabel("err_rel (log)")
    fig.suptitle(f"Aggregation error over time (beta={beta})")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "err_over_time.png"), dpi=130)
    plt.close(fig)


def fig_final_error_bars(summary, beta, out_dir):
    stats = group_stats(filter_rows(summary, beta=beta), ("overlay", "aggregation"), "final_err_rel")
    x = range(len(AGGS))
    width = 0.25
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, ov in enumerate(OVERLAYS):
        ys = [stats.get((ov, a), (0.0, 0.0))[0] for a in AGGS]
        ax.bar([xi + (i - 1) * width for xi in x], ys, width, label=ov)
    ax.set_xticks(list(x))
    ax.set_xticklabels(AGGS)
    ax.set_yscale("log")
    ax.set_ylabel("final err_rel (log)")
    ax.set_title(f"Final aggregation error by overlay x aggregation (beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "final_error_bars.png"), dpi=130)
    plt.close(fig)


def fig_penetration_vs_beta(summary, out_dir):
    betas = sorted({r["beta"] for r in summary})
    stats = group_stats(summary, ("overlay", "beta"), "final_sybil_penetration")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for ov in OVERLAYS:
        ys = [stats.get((ov, b), (0.0, 0.0))[0] for b in betas]
        ax.plot(betas, ys, marker="o", label=ov)
    ax.set_xlabel("beta")
    ax.set_ylabel("Sybil penetration")
    ax.set_title("Sybil penetration vs malicious share")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "penetration_vs_beta.png"), dpi=130)
    plt.close(fig)


def fig_overhead(summary, beta, out_dir):
    stats_c = group_stats(filter_rows(summary, beta=beta, aggregation="mean"),
                          ("overlay",), "control_overhead")
    stats_r = group_stats(filter_rows(summary, beta=beta, aggregation="mean"),
                          ("overlay",), "rejected_ratio")
    x = range(len(OVERLAYS))
    fig, ax1 = plt.subplots(figsize=(7, 4.5))
    ax1.bar([xi - 0.2 for xi in x], [stats_c.get((ov,), (0, 0))[0] for ov in OVERLAYS],
            0.4, label="control overhead")
    ax2 = ax1.twinx()
    ax2.bar([xi + 0.2 for xi in x], [stats_r.get((ov,), (0, 0))[0] for ov in OVERLAYS],
            0.4, color="orange", label="rejected ratio")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(OVERLAYS)
    ax1.set_ylabel("control msgs / node / round")
    ax2.set_ylabel("rejected ratio")
    ax1.set_title(f"Cost of defense (beta={beta})")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "overhead.png"), dpi=130)
    plt.close(fig)


def fig_error_boxplot(summary, beta, aggregation, out_dir):
    groups = group_values(filter_rows(summary, beta=beta, aggregation=aggregation),
                          ("overlay",), "final_err_rel")
    data = [groups.get((ov,), []) for ov in OVERLAYS]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.boxplot(data, tick_labels=OVERLAYS)
    ax.set_yscale("log")
    ax.set_ylabel("final err_rel (log)")
    ax.set_title(f"Error spread across seeds (beta={beta}, {aggregation})")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "error_boxplot.png"), dpi=130)
    plt.close(fig)


def fig_profiles(ablation_summary, out_dir):
    profiles = ["coordinated", "extreme", "random", "low_biased", "stale"]
    stats = group_stats(ablation_summary, ("byzantine_profile", "aggregation"), "final_err_rel")
    x = range(len(profiles))
    width = 0.25
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for i, agg in enumerate(AGGS):
        ys = [stats.get((p, agg), (0.0, 0.0))[0] for p in profiles]
        ax.bar([xi + (i - 1) * width for xi in x], ys, width, label=agg)
    ax.set_xticks(list(x))
    ax.set_xticklabels(profiles)
    ax.set_yscale("log")
    ax.set_ylabel("final err_rel (log)")
    ax.set_title("Byzantine profiles vs aggregation (eclipse-resistant)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "byzantine_profiles.png"), dpi=130)
    plt.close(fig)


def fig_rejection_reasons(summary, beta, out_dir):
    reasons = ["rej_pow", "rej_age", "rej_score", "rej_bucket"]
    labels = ["invalid PoW", "too young", "low score", "bucket full"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bottom = [0.0] * len(OVERLAYS)
    for reason, label in zip(reasons, labels):
        stats = group_stats(filter_rows(summary, beta=beta, aggregation="mean"), ("overlay",), reason)
        ys = [stats.get((ov,), (0.0, 0.0))[0] for ov in OVERLAYS]
        ax.bar(OVERLAYS, ys, bottom=bottom, label=label)
        bottom = [b + y for b, y in zip(bottom, ys)]
    ax.set_ylabel("udeo odbijanja po razlogu")
    ax.set_title(f"Razlozi odbijanja kandidata (beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "rejection_reasons.png"), dpi=130)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    # podrazumevano se izvestaj pravi iz rezultata dobijenih u Docker okruzenju;
    # --source inprocess prebacuje na in-process rezultate
    parser.add_argument("--source", default="docker", choices=["docker", "inprocess"])
    parser.add_argument("--round", default=None)
    parser.add_argument("--summary", default=None)
    parser.add_argument("--ablation", default=None)
    parser.add_argument("--figures", default="figures")
    parser.add_argument("--tables", default=None)
    parser.add_argument("--beta", type=float, default=0.3)
    args = parser.parse_args()
    base = os.path.join("results", args.source)
    args.round = args.round or os.path.join(base, "main.csv")
    args.summary = args.summary or os.path.join(base, "main_summary.csv")
    args.ablation = args.ablation or os.path.join(base, "ablation_summary.csv")
    args.tables = args.tables or os.path.join(base, "tables.md")
    if not os.path.exists(args.summary):
        raise SystemExit(
            f"nema rezultata: {args.summary}\n"
            f"pokreni matricu za izvor '{args.source}', ili koristi --source "
            f"{'inprocess' if args.source == 'docker' else 'docker'}")

    os.makedirs(args.figures, exist_ok=True)
    open(args.tables, "w").close()

    summary = load(args.summary)
    table_final_error(summary, args.beta, args.tables)
    table_penetration(summary, args.tables)
    fig_final_error_bars(summary, args.beta, args.figures)
    fig_penetration_vs_beta(summary, args.figures)
    fig_overhead(summary, args.beta, args.figures)
    fig_rejection_reasons(summary, args.beta, args.figures)
    fig_error_boxplot(summary, args.beta, "median", args.figures)

    if os.path.exists(args.round):
        fig_err_over_time(load(args.round), args.beta, args.figures)
    if os.path.exists(args.ablation):
        fig_profiles(load(args.ablation), args.figures)

    print(f"tables -> {args.tables}")
    print(f"figures -> {args.figures}/")


if __name__ == "__main__":
    main()
