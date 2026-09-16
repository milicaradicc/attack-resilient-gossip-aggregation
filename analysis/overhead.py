"""7.8 Analiza kontrolnog i data overhead-a."""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.loader import filter_rows, group_stats

from analysis.common import (BETAS, DOPUNSKE_MERE, OVERLAYS, AGGS, _cell, _mean,
                                      _realized, _sel, _time_cell, _write)


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

def table_overhead(summary, beta, out):
    # 7.8: cena zastitnih mehanizama
    lines = [f"## 7.8 Overhead (beta={beta})", "",
             "| strategija | control | data | udeo odbijenih |", "|---|---|---|---|"]
    for overlay in OVERLAYS:
        rows = _sel(summary, overlay=overlay, beta=beta)
        lines.append(f"| {overlay} | {_mean(rows, 'control_overhead'):.2f} | "
                     f"{_mean(rows, 'data_overhead'):.2f} | "
                     f"{_mean(rows, 'rejected_ratio'):.3f} |")
    _write(out, lines + [""])


DOPUNSKE_MERE = [("final_err_rel", "relativna greska"),
                 ("final_sybil_penetration", "Sybil penetracija"),
                 ("recovery_time", "vreme oporavka"),
                 ("control_overhead", "kontrolni overhead"),
                 ("rejected_ratio", "udeo odbijenih")]

def table_overhead_vs_resilience(summary_rows, beta, out):
    # 7.8: odnos izmedju placenog overhead-a i postignute otpornosti.
    # Referentna strategija sluzi kao osnova: koliko dodatnih kontrolnih poruka
    # je placeno i koliko je puta smanjena greska odnosno penetracija.
    osnova = _sel(summary_rows, overlay="random", aggregation="trimmed_mean", beta=beta)
    if not osnova:
        return
    o_control = _mean(osnova, "control_overhead")
    o_greska = _mean(osnova, "final_err_rel")
    o_pen = _mean(osnova, "final_sybil_penetration")
    lines = [f"## 7.8 Overhead naspram otpornosti (beta={beta}, trimmed_mean)", "",
             "| strategija | dodatni control | greska manja | penetracija manja |",
             "|---|---|---|---|"]
    for overlay in OVERLAYS:
        rows = _sel(summary_rows, overlay=overlay, aggregation="trimmed_mean", beta=beta)
        if not rows:
            continue
        control = _mean(rows, "control_overhead")
        error = _mean(rows, "final_err_rel")
        pen = _mean(rows, "final_sybil_penetration")
        dodatni = f"{control - o_control:+.2f} ({(control / o_control - 1) * 100:+.0f}%)"
        puta_greska = "-" if error <= 0 else f"{o_greska / greska:.0f}x"
        puta_pen = "-" if pen <= 0 else f"{o_pen / pen:.0f}x"
        lines.append(f"| {overlay} | {dodatni} | {puta_greska} | {puta_pen} |")
    _write(out, lines + [""])

def table_tradeoff(summary_rows, beta, out):
    # 7.8: koji pristup ostvaruje najbolji kompromis izmedju bezbednosti,
    # stabilnosti i overhead-a — sve tri mere na jednom mestu
    lines = [f"## 7.8 Kompromis bezbednost / stabilnost / overhead (beta={beta})", "",
             "| strategija | agregacija | greska | penetracija | varijansa | control |",
             "|---|---|---|---|---|---|"]
    for overlay in OVERLAYS:
        for aggregation in AGGS:
            rows = _sel(summary_rows, overlay=overlay, aggregation=aggregation, beta=beta)
            if not rows:
                continue
            lines.append(f"| {overlay} | {aggregation} | "
                         f"{_mean(rows, 'final_err_rel'):.4f} | "
                         f"{_mean(rows, 'final_sybil_penetration'):.4f} | "
                         f"{_mean(rows, 'stability'):.2e} | "
                         f"{_mean(rows, 'control_overhead'):.2f} |")
    _write(out, lines + [""])

def table_overhead_over_time(round_rows, beta, out):
    # 7.8: overhead po rundi, da se vidi kada zastita pocinje da kosta
    if not round_rows:
        return
    last = max(r["round"] for r in round_rows)
    marks = [r for r in (1, 5, 10, 11, 15, 25, last) if r <= last]
    sub = filter_rows(round_rows, beta=beta, aggregation="trimmed_mean")
    lines = [f"## 7.8 Kontrolne poruke po rundi (beta={beta})", "",
             "| strategija | " + " | ".join(f"runda {r}" for r in marks) + " |",
             "|---|" + "---|" * len(marks)]
    for overlay in OVERLAYS:
        cells = [f"{_mean(_sel(sub, overlay=overlay, round=r), 'control_msgs'):.0f}"
                 for r in marks]
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])

def fig_overhead_stacked(round_rows, beta, out_dir):
    # 7.8: control i data saobracaj po rundi, jedno preko drugog
    fig, ax = plt.subplots(figsize=(8, 4.5))
    sub = filter_rows(round_rows, beta=beta, aggregation="trimmed_mean",
                      overlay="eclipse_resistant")
    control = group_stats(sub, ("round",), "control_msgs")
    data = group_stats(sub, ("round",), "data_msgs")
    xs = sorted(control)
    rounds = [x[0] for x in xs]
    c = [control[x][0] for x in xs]
    d = [data[x][0] for x in xs]
    ax.stackplot(rounds, d, c, labels=["data", "control"])
    ax.set_xlabel("round_no")
    ax.set_ylabel("count poruka")
    ax.set_title(f"Saobracaj po rundi (eclipse_resistant, beta={beta})")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "overhead_stacked.png"), dpi=130)
    plt.close(fig)
