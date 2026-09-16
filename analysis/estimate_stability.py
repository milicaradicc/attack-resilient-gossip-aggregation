"""7.6 Stabilnost agregacione procene."""

from __future__ import annotations

import os
from statistics import pvariance

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.loader import filter_rows, group_stats, load

from analysis.common import (BETAS, OVERLAYS, AGGS, _cell, _mean,
                                      _realized, _sel, _time_cell, _write)


def fig_variance_over_time(round_rows, beta, window, out_dir):
    # 7.6: pokretna varijansa procene, prozor duzine `window` rundi
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for agg in AGGS:
        sub = filter_rows(round_rows, beta=beta, aggregation=agg,
                          overlay="eclipse_resistant")
        series = group_stats(sub, ("round",), "avg_estimate")
        xs = sorted(series)
        values = [series[x][0] for x in xs]
        rounds, variances = [], []
        for i in range(window, len(values)):
            chunk = values[i - window:i]
            variances.append(pvariance(chunk))
            rounds.append(xs[i][0])
        if variances:
            ax.plot(rounds, [max(v, 1e-18) for v in variances], label=agg)
    ax.set_xlabel("round_no")
    ax.set_ylabel(f"varijansa procene (prozor {window})")
    ax.set_yscale("log")
    ax.set_title(f"Stabilnost procene kroz vreme (eclipse_resistant, beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "variance_over_time.png"), dpi=130)
    plt.close(fig)

def table_stability(summary, beta, out):
    # 7.6: varijansa procene u konvergencijskom prozoru
    lines = [f"## 7.6 Stabilnost procene (beta={beta})", "",
             "| strategija | " + " | ".join(AGGS) + " |", "|---|" + "---|" * len(AGGS)]
    for overlay in OVERLAYS:
        cells = [f"{_mean(_sel(summary, overlay=overlay, aggregation=a, beta=beta), 'stability'):.2e}"
                 for a in AGGS]
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])

def table_stability_vs_error(summary_rows, beta, out):
    # 7.6: da li sistem kratkorocno postize malu gresku a dugorocno ostaje
    # nestabilan. Niska varijansa sama po sebi nije povoljan ishod — mora se
    # citati zajedno sa greskom, jer sistem moze mirno konvergirati ka pogresnoj
    # vrednosti.
    lines = [f"## 7.6 Stabilnost uz gresku (beta={beta})", "",
             "| strategija | agregacija | greska | varijansa | ocena |",
             "|---|---|---|---|---|"]
    for overlay in OVERLAYS:
        for aggregation in AGGS:
            rows = _sel(summary_rows, overlay=overlay, aggregation=aggregation, beta=beta)
            if not rows:
                continue
            error = _mean(rows, "final_err_rel")
            varijansa = _mean(rows, "stability")
            if error < 0.05 and varijansa < 0.01:
                ocena = "tacan i stabilan"
            elif error < 0.05:
                ocena = "tacan, ali osciluje"
            elif varijansa < 0.01:
                ocena = "stabilno pogresan"
            else:
                ocena = "netacan i nestabilan"
            lines.append(f"| {overlay} | {aggregation} | {error:.4f} | "
                         f"{varijansa:.2e} | {ocena} |")
    _write(out, lines + [""])

def table_attack_effect_on_stability(sweeps, out):
    # 7.6: uticaj churn i delay napada na stabilnost procene
    for naziv, kolona, naslov in (("churn", "churn_period", "churn napada"),
                                  ("delay", "delay_rounds", "delay napada")):
        path = sweeps.get(naziv)
        if not path or not os.path.exists(path):
            continue
        rows = load(path)
        if kolona not in rows[0]:
            continue
        values = sorted({r[kolona] for r in rows})
        lines = [f"## 7.6 Uticaj {naslov} na stabilnost", "",
                 "| strategija | " + " | ".join(f"{kolona}={v:g}" for v in values) + " |",
                 "|---|" + "---|" * len(values)]
        for overlay in OVERLAYS:
            cells = [f"{_mean(_sel(rows, overlay=overlay, **{kolona: v}), 'stability'):.2e}"
                     for v in values]
            lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
        _write(out, lines + [""])
