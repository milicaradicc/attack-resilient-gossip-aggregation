"""7.1 Uticaj overlay strategije na agregacionu tacnost."""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.loader import filter_rows, group_stats, group_values

from analysis.common import (BETAS, OVERLAYS, AGGS, _cell, _mean,
                                      _realized, _sel, _time_cell, _write)


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
    fig.suptitle(f"Aggregation greska over time (beta={beta})")
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
    ax.set_title(f"Final aggregation greska by overlay x aggregation (beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "final_greska_bars.png"), dpi=130)
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
    fig.savefig(os.path.join(out_dir, "greska_boxplot.png"), dpi=130)
    plt.close(fig)

def table_error_by_beta(summary, out):
    # 7.1: greska po strategiji, agregaciji i udelu zlonamernih
    lines = ["## 7.1 Relativna greska po beta", "",
             "| strategija | agregacija | " + " | ".join(f"b={b}" for b in BETAS) + " |",
             "|---|---|" + "---|" * len(BETAS)]
    for overlay in OVERLAYS:
        for aggregation in AGGS:
            cells = [f"{_mean(_sel(summary, overlay=overlay, aggregation=aggregation, beta=b), 'final_err_rel'):.4f}"
                     for b in BETAS]
            lines.append(f"| {overlay} | {aggregation} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])


def table_benign_baseline(summary, out):
    lines = ["## 7.1 Benigna bazna greska (beta=0, bez napadaca)", "",
             "| strategija | " + " | ".join(AGGS) + " |",
             "|---|" + "---|" * len(AGGS)]
    for overlay in OVERLAYS:
        cells = []
        for aggregation in AGGS:
            v = _mean(_sel(summary, overlay=overlay, aggregation=aggregation, beta=0.0),
                      "final_err_rel")
            # prag iz 5.2.6 je 0.01; oznacava se sta ga prelazi
            cells.append(f"{v:.2e}" + (" (iznad 0.01)" if v > 0.01 else ""))
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])


def table_error_above_baseline(summary, out):
    lines = ["## 7.1 Greska umanjena za benignu baznu liniju", "",
             "| strategija | agregacija | " + " | ".join(f"b={b}" for b in BETAS if b > 0) + " |",
             "|---|---|" + "---|" * len([b for b in BETAS if b > 0])]
    for overlay in OVERLAYS:
        for aggregation in AGGS:
            baseline = _mean(_sel(summary, overlay=overlay, aggregation=aggregation,
                                  beta=0.0), "final_err_rel")
            cells = []
            for b in BETAS:
                if b <= 0:
                    continue
                v = _mean(_sel(summary, overlay=overlay, aggregation=aggregation, beta=b),
                          "final_err_rel")
                cells.append(f"{v - baseline:+.4f}")
            lines.append(f"| {overlay} | {aggregation} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])