from __future__ import annotations

import argparse
import os
from collections import Counter, defaultdict
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.loader import load

OVERLAYS = ["random", "sybil_resistant", "eclipse_resistant"]
AGGS = ["mean", "median", "trimmed_mean"]

# Grayscale with distinct line styles and hatching so the figures stay readable
# in black-and-white print. Axis labels and legends are in Serbian to match the
# text of the thesis.
OVERLAY_LABEL = {"random": "референтна", "sybil_resistant": "Sybil-отпорна",
                 "eclipse_resistant": "Eclipse-отпорна"}
AGG_LABEL = {"mean": "аритметичка средина", "median": "медијана",
             "trimmed_mean": "одсечена средина"}
OVERLAY_STYLE = {"random": dict(color="0.0", ls="-", marker="o"),
                 "sybil_resistant": dict(color="0.35", ls="--", marker="s"),
                 "eclipse_resistant": dict(color="0.6", ls=":", marker="^")}
OVERLAY_FILL = {"random": ("0.25", ""), "sybil_resistant": ("0.6", "//"),
                "eclipse_resistant": ("0.9", "..")}
LINE = dict(markevery=5, markersize=4, linewidth=1.4)

AX_ERROR = "релативна грешка"
AX_ROUND = "рунда"
ATTACK_MARK = "почетак напада"


def _select(rows, **conditions):
    return [r for r in rows if all(r.get(k) == v for k, v in conditions.items())]


def _average(rows, field):
    vals = [r[field] for r in rows if isinstance(r.get(field), (int, float))]
    return mean(vals) if vals else None


def _by_round(rows, field, **conditions):
    selected = _select(rows, **conditions)
    per_round = defaultdict(list)
    for r in selected:
        v = r.get(field)
        if isinstance(v, (int, float)):
            per_round[r["round"]].append(v)
    rounds = sorted(per_round)
    return rounds, [mean(per_round[t]) for t in rounds]


def _grid(ax, axis="both"):
    ax.grid(True, axis=axis, color="0.9", linewidth=0.5)


def _save(fig, out_dir, name):
    fig.tight_layout()
    path = os.path.join(out_dir, name)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print("  ", path)


def fig_error_over_time(rounds, beta, activation, threshold, out_dir):
    # 7.1: relative error per round, one panel per aggregation function
    fig, axes = plt.subplots(1, len(AGGS), figsize=(13, 4), sharey=True)
    for ax, agg in zip(axes, AGGS):
        for ov in OVERLAYS:
            x, y = _by_round(rounds, "err_rel", overlay=ov, aggregation=agg, beta=beta)
            if x:
                ax.plot(x, y, label=OVERLAY_LABEL[ov], **OVERLAY_STYLE[ov], **LINE)
        ax.axvline(activation, ls="-.", color="0.5", linewidth=0.8)
        ax.axhline(threshold, color="0.5", linewidth=0.6)
        ax.set_yscale("log")
        ax.set_title(AGG_LABEL[agg])
        ax.set_xlabel(AX_ROUND)
        _grid(ax)
    axes[0].set_ylabel(AX_ERROR)
    low, high = axes[0].get_ylim()
    axes[0].text(activation - 1.2, (low * high) ** 0.5, ATTACK_MARK,
                 fontsize=8, color="0.4", rotation=90, va="center", ha="right")
    axes[-1].legend(frameon=False, fontsize=9)
    _save(fig, out_dir, "err_over_time.png")


def fig_error_by_configuration(summary, beta, threshold, out_dir):
    # 7.1: mean final error per strategy and aggregation function
    fig, ax = plt.subplots(figsize=(9, 4.5))
    width, positions = 0.26, range(len(AGGS))
    for i, ov in enumerate(OVERLAYS):
        heights = [_average(_select(summary, overlay=ov, aggregation=agg, beta=beta),
                            "final_err_rel") or 0 for agg in AGGS]
        color, hatch = OVERLAY_FILL[ov]
        ax.bar([x + (i - 1) * width for x in positions], heights, width,
               label=OVERLAY_LABEL[ov], color=color, hatch=hatch,
               edgecolor="0.0", linewidth=0.6)
    ax.axhline(threshold, ls="--", color="0.3", linewidth=0.8)
    ax.text(len(AGGS) - 0.55, threshold * 1.15,
            f"праг {threshold:g}".replace(".", ","), fontsize=8, color="0.3")
    ax.set_xticks(list(positions))
    ax.set_xticklabels([AGG_LABEL[a] for a in AGGS])
    ax.set_yscale("log")
    ax.set_ylabel(AX_ERROR)
    ax.legend(frameon=False, fontsize=9)
    _grid(ax, "y")
    _save(fig, out_dir, "final_error_bars.png")


def fig_error_spread(summary, beta, threshold, out_dir):
    # 7.1: spread of the final error across seeds
    fig, axes = plt.subplots(1, len(AGGS), figsize=(13, 4), sharey=True)
    for ax, agg in zip(axes, AGGS):
        data = [[r["final_err_rel"]
                 for r in _select(summary, overlay=ov, aggregation=agg, beta=beta)]
                for ov in OVERLAYS]
        if not any(data):
            continue
        try:
            boxes = ax.boxplot(data, patch_artist=True, widths=0.55,
                               medianprops=dict(color="0.0", linewidth=1.2))
        except TypeError:
            boxes = ax.boxplot(data, patch_artist=True)
        for box, ov in zip(boxes["boxes"], OVERLAYS):
            color, hatch = OVERLAY_FILL[ov]
            box.set_facecolor(color)
            box.set_hatch(hatch)
        ax.axhline(threshold, ls="--", color="0.3", linewidth=0.8)
        ax.set_yscale("log")
        ax.set_title(AGG_LABEL[agg])
        ax.set_xticks(range(1, len(OVERLAYS) + 1))
        ax.set_xticklabels([OVERLAY_LABEL[o] for o in OVERLAYS], fontsize=8)
        _grid(ax, "y")
    axes[0].set_ylabel("релативна грешка на крају")
    _save(fig, out_dir, "error_boxplot.png")


def fig_penetration_over_time(rounds, beta, activation, out_dir):
    # 7.3: share of malicious identities in peer sets over rounds
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for ov in OVERLAYS:
        x, y = _by_round(rounds, "sybil_penetration", overlay=ov, beta=beta)
        if x:
            ax.plot(x, y, label=OVERLAY_LABEL[ov], **OVERLAY_STYLE[ov], **LINE)
    ax.axvline(activation, ls="-.", color="0.5", linewidth=0.8)
    ax.set_xlabel(AX_ROUND)
    ax.set_ylabel("удео нападачких суседа")
    ax.legend(frameon=False, fontsize=9)
    _grid(ax)
    _save(fig, out_dir, "penetration_over_time.png")


def fig_compromise_distribution(nodes, beta, out_dir):
    # 7.3: how many nodes hold how many malicious peers in the last round
    if not nodes:
        return
    last = max(r["round"] for r in nodes)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    width = 0.26
    for i, ov in enumerate(OVERLAYS):
        selected = _select(nodes, overlay=ov, beta=beta, round=last)
        if not selected:
            continue
        counts = Counter(round(r["sybil_share"] * r["peer_count"]) for r in selected)
        keys = range(0, 8)
        shares = [100 * counts.get(k, 0) / len(selected) for k in keys]
        color, hatch = OVERLAY_FILL[ov]
        ax.bar([k + (i - 1) * width for k in keys], shares, width,
               label=OVERLAY_LABEL[ov], color=color, hatch=hatch,
               edgecolor="0.0", linewidth=0.6)
    ax.set_xlabel("број нападачких суседа")
    ax.set_ylabel("удео чворова (%)")
    ax.legend(frameon=False, fontsize=9)
    _grid(ax, "y")
    _save(fig, out_dir, "compromise_distribution.png")


def fig_eclipse_over_time(rounds, out_dir):
    # 7.4: share of fully isolated nodes over rounds, one panel per beta
    betas = sorted({r["beta"] for r in rounds
                    if isinstance(r.get("beta"), (int, float))})
    fig, axes = plt.subplots(1, len(betas), figsize=(4.3 * len(betas), 4), sharey=True)
    axes = axes if len(betas) > 1 else [axes]
    for ax, b in zip(axes, betas):
        for ov in OVERLAYS:
            x, y = _by_round(rounds, "eclipse_rate", overlay=ov, beta=b)
            if x:
                ax.plot(x, y, label=OVERLAY_LABEL[ov], **OVERLAY_STYLE[ov], **LINE)
        ax.set_title(f"β = {b}".replace(".", ","))
        ax.set_xlabel(AX_ROUND)
        ax.set_ylim(-0.05, 1.05)
        _grid(ax)
    axes[0].set_ylabel("удео изолованих учесника")
    axes[-1].legend(frameon=False, fontsize=9)
    _save(fig, out_dir, "eclipse_over_time.png")


def fig_diversity_over_time(rounds, beta, out_dir):
    # 7.7: Shannon entropy of the peer set over rounds
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for ov in OVERLAYS:
        x, y = _by_round(rounds, "peer_diversity", overlay=ov, beta=beta)
        if x:
            ax.plot(x, y, label=OVERLAY_LABEL[ov], **OVERLAY_STYLE[ov], **LINE)
    ax.set_xlabel(AX_ROUND)
    ax.set_ylabel("Шенонова ентропија")
    ax.legend(frameon=False, fontsize=9)
    _grid(ax)
    _save(fig, out_dir, "diversity_over_time.png")


def fig_bucket_histogram(nodes, out_dir):
    # 7.4: largest number of peers drawn from a single bucket
    if not nodes:
        return
    last = max(r["round"] for r in nodes)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    width = 0.26
    for i, ov in enumerate(OVERLAYS):
        selected = _select(nodes, overlay=ov, round=last)
        if not selected:
            continue
        counts = Counter(round(r["bucket_occupancy"] * r["peer_count"])
                         for r in selected)
        keys = range(1, 8)
        shares = [100 * counts.get(k, 0) / len(selected) for k in keys]
        color, hatch = OVERLAY_FILL[ov]
        ax.bar([k + (i - 1) * width for k in keys], shares, width,
               label=OVERLAY_LABEL[ov], color=color, hatch=hatch,
               edgecolor="0.0", linewidth=0.6)
    ax.set_xlabel("највећи број суседа из исте групе")
    ax.set_ylabel("удео учесника (%)")
    ax.legend(frameon=False, fontsize=9)
    _grid(ax, "y")
    _save(fig, out_dir, "bucket_histogram.png")


def fig_moving_average(rounds, beta, window, out_dir):
    # 7.6: moving average of the estimate
    fig, axes = plt.subplots(1, len(AGGS), figsize=(13, 4), sharey=True)
    for ax, agg in zip(axes, AGGS):
        for ov in OVERLAYS:
            x, y = _by_round(rounds, "avg_estimate", overlay=ov, aggregation=agg,
                             beta=beta)
            if not x:
                continue
            smoothed = [mean(y[max(0, i - window + 1):i + 1]) for i in range(len(y))]
            ax.plot(x, smoothed, label=OVERLAY_LABEL[ov], **OVERLAY_STYLE[ov], **LINE)
        ax.set_title(AGG_LABEL[agg])
        ax.set_xlabel(AX_ROUND)
        _grid(ax)
    axes[0].set_ylabel(f"процена (покретни просек, {window} рунди)")
    axes[-1].legend(frameon=False, fontsize=9)
    _save(fig, out_dir, "moving_average.png")


def fig_variance_over_time(rounds, beta, window, out_dir):
    # 7.6: moving variance of the estimate
    fig, axes = plt.subplots(1, len(AGGS), figsize=(13, 4), sharey=True)
    for ax, agg in zip(axes, AGGS):
        for ov in OVERLAYS:
            x, y = _by_round(rounds, "avg_estimate", overlay=ov, aggregation=agg,
                             beta=beta)
            if len(x) < window:
                continue
            variances = []
            for i in range(len(y)):
                chunk = y[max(0, i - window + 1):i + 1]
                m = mean(chunk)
                variances.append(sum((v - m) ** 2 for v in chunk) / len(chunk)
                                 if len(chunk) > 1 else 0.0)
            ax.plot(x, [v if v > 0 else 1e-16 for v in variances],
                    label=OVERLAY_LABEL[ov], **OVERLAY_STYLE[ov], **LINE)
        ax.set_yscale("log")
        ax.set_title(AGG_LABEL[agg])
        ax.set_xlabel(AX_ROUND)
        _grid(ax)
    axes[0].set_ylabel(f"варијанса процене ({window} рунди)")
    axes[-1].legend(frameon=False, fontsize=9)
    _save(fig, out_dir, "variance_over_time.png")


def fig_traffic_per_round(rounds, beta, activation, out_dir):
    # 7.8: stacked view over rounds, data messages at the base
    x, data = _by_round(rounds, "data_msgs", beta=beta, overlay="eclipse_resistant",
                        aggregation="trimmed_mean")
    _, control = _by_round(rounds, "control_msgs", beta=beta,
                           overlay="eclipse_resistant", aggregation="trimmed_mean")
    if not x:
        return
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.stackplot(x, data, control,
                 labels=["агрегационе поруке", "контролне поруке"],
                 colors=["0.35", "0.82"], edgecolor="0.2", linewidth=0.5)
    ax.axvline(activation, ls="-.", color="0.2", linewidth=0.8)
    ax.text(activation + 1, (max(data) + max(control)) * 0.6, ATTACK_MARK,
            fontsize=8, color="0.25")
    ax.set_xlabel(AX_ROUND)
    ax.set_ylabel("број порука")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    _grid(ax, "y")
    _save(fig, out_dir, "overhead_stacked.png")


def fig_overhead_bars(summary, beta, out_dir):
    # 7.8: control and data traffic per strategy
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    control = [_average(_select(summary, overlay=ov, beta=beta),
                        "control_overhead") or 0 for ov in OVERLAYS]
    data = [_average(_select(summary, overlay=ov, beta=beta),
                     "data_overhead") or 0 for ov in OVERLAYS]
    labels = [OVERLAY_LABEL[o] for o in OVERLAYS]
    ax.bar(labels, data, label="агрегационе поруке", color="0.35",
           edgecolor="0.0", linewidth=0.6)
    ax.bar(labels, control, bottom=data, label="контролне поруке", color="0.85",
           hatch="//", edgecolor="0.0", linewidth=0.6)
    ax.set_ylabel("порука по учеснику и рунди")
    ax.legend(frameon=False, fontsize=9)
    _grid(ax, "y")
    _save(fig, out_dir, "overhead_bars.png")


def fig_overhead_per_round(rounds, beta, out_dir):
    # 7.8: control traffic as solid lines, data traffic as dashed
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for ov in OVERLAYS:
        x, y = _by_round(rounds, "control_msgs", overlay=ov, beta=beta)
        if x:
            ax.plot(x, y, label=f"{OVERLAY_LABEL[ov]} — контролне",
                    **OVERLAY_STYLE[ov], **LINE)
        x, y = _by_round(rounds, "data_msgs", overlay=ov, beta=beta)
        if x:
            style = dict(OVERLAY_STYLE[ov])
            style["ls"] = "--"
            style.pop("marker", None)
            ax.plot(x, y, linewidth=1.0, alpha=0.7, **style)
    ax.set_xlabel(AX_ROUND)
    ax.set_ylabel("број порука")
    ax.legend(frameon=False, fontsize=8)
    _grid(ax)
    _save(fig, out_dir, "overhead.png")


def main():
    ap = argparse.ArgumentParser(description="Figures for chapter 7")
    ap.add_argument("--source", default="inprocess", choices=["inprocess", "docker"])
    ap.add_argument("--beta", type=float, default=0.3)
    ap.add_argument("--out", default="figures")
    ap.add_argument("--activation", type=int, default=11)
    ap.add_argument("--epsilon", type=float, default=0.05)
    ap.add_argument("--window", type=int, default=5)
    args = ap.parse_args()

    base = os.path.join("results", args.source)
    os.makedirs(args.out, exist_ok=True)

    def optional(name):
        path = os.path.join(base, name)
        return load(path) if os.path.exists(path) else []

    summary = optional("main_summary.csv")
    rounds, nodes = optional("main.csv"), optional("main_nodes.csv")
    eclipse_rounds = optional("eclipse.csv")
    eclipse_nodes = optional("eclipse_nodes.csv")
    if not summary:
        raise SystemExit(f"missing {base}/main_summary.csv - run the main matrix first")

    print("figures ->")
    if rounds:
        fig_error_over_time(rounds, args.beta, args.activation, args.epsilon, args.out)
    fig_error_by_configuration(summary, args.beta, args.epsilon, args.out)
    fig_error_spread(summary, args.beta, args.epsilon, args.out)
    if rounds:
        fig_penetration_over_time(rounds, args.beta, args.activation, args.out)
    fig_compromise_distribution(nodes, args.beta, args.out)
    if eclipse_rounds:
        fig_eclipse_over_time(eclipse_rounds, args.out)
    if rounds:
        fig_diversity_over_time(rounds, args.beta, args.out)
        fig_moving_average(rounds, args.beta, args.window, args.out)
        fig_variance_over_time(rounds, args.beta, args.window, args.out)
        fig_overhead_per_round(rounds, args.beta, args.out)
        fig_traffic_per_round(rounds, args.beta, args.activation, args.out)
    fig_bucket_histogram(eclipse_nodes or nodes, args.out)
    fig_overhead_bars(summary, args.beta, args.out)


if __name__ == "__main__":
    main()