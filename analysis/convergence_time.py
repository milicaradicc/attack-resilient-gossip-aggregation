"""7.5 Analiza vremena konvergencije."""

from __future__ import annotations

import os
from statistics import mean, pstdev

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.loader import filter_rows, group_stats, load

from analysis.common import (BETAS, OVERLAYS, AGGS, _cell, _mean,
                                      _realized, _sel, _time_cell, _write)


def table_recovery(summary_rows, beta, out):
    # Dopuna uz 7.5: prva runda od koje greska TRAJNO ostaje ispod praga.
    # convergence_time belezi i kratkotrajan prolazak ispod praga, pa sistem koji
    # se kasnije pokvari izgleda kao da je konvergirao; oporavak to razdvaja.
    lines = [f"## 7.5 Vreme oporavka (beta={beta})", "",
             "| overlay \\ aggregation | " + " | ".join(AGGS) + " |",
             "|---|" + "---|" * len(AGGS)]
    for overlay in OVERLAYS:
        cells = [_time_cell([r["recovery_time"] for r in
                             _sel(summary_rows, overlay=overlay,
                                  aggregation=aggregation, beta=beta)])
                 for aggregation in AGGS]
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])

def table_convergence(summary_rows, beta, out):
    # 6.3.2: -1 znaci da sistem nikada nije dostigao prag i ne sme se usrednjavati
    # sa brojem rundi, pa se prikazuje odvojeno kao udeo pokretanja bez konvergencije
    lines = [f"## 7.5 Vreme konvergencije (beta={beta})", "",
             "| overlay \\ aggregation | " + " | ".join(AGGS) + " |",
             "|---|" + "---|" * len(AGGS)]
    for overlay in OVERLAYS:
        cells = []
        for aggregation in AGGS:
            selected = [r for r in summary_rows
                   if r["overlay"] == overlay and r["aggregation"] == aggregation
                   and r["beta"] == beta]
            times = [r["convergence_time"] for r in selected]
            reached = [t for t in times if t >= 0]
            if not reached:
                cells.append("nikad")
            elif len(reached) == len(times):
                cells.append(f"{mean(reached):.1f}")
            else:
                cells.append(f"{mean(reached):.1f} ({len(times) - len(reached)}/"
                             f"{len(times)} nikad)")
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    lines.append("")
    with open(out, "a") as f:
        f.write("\n".join(lines) + "\n")

def fig_moving_average(round_rows, beta, window, out_dir):
    # 7.6: pokretni prosek procene, da se vide oscilacije tokom prozora
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for agg in AGGS:
        sub = filter_rows(round_rows, beta=beta, aggregation=agg,
                          overlay="eclipse_resistant")
        series = group_stats(sub, ("round",), "avg_estimate")
        xs = sorted(series)
        values = [series[x][0] for x in xs]
        rounds, avg = [], []
        for i in range(window, len(values)):
            avg.append(mean(values[i - window:i]))
            rounds.append(xs[i][0])
        if avg:
            ax.plot(rounds, avg, label=agg)
    ax.set_xlabel("round_no")
    ax.set_ylabel(f"pokretni prosek procene (prozor {window})")
    ax.set_title(f"Oscilacije procene (eclipse_resistant, beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "moving_average.png"), dpi=130)
    plt.close(fig)

def table_convergence_stats(summary_rows, beta, out):
    # 7.5: prosek, standardna devijacija i broj pokretanja koja ne konvergiraju
    lines = [f"## 7.5 Statistika vremena konvergencije (beta={beta})", "",
             "| strategija | agregacija | prosek | std | ne konvergira |",
             "|---|---|---|---|---|"]
    for overlay in OVERLAYS:
        for aggregation in AGGS:
            rows = _sel(summary_rows, overlay=overlay, aggregation=aggregation, beta=beta)
            if not rows:
                continue
            times = [r["convergence_time"] for r in rows]
            reached = [t for t in times if t >= 0]
            if not reached:
                lines.append(f"| {overlay} | {aggregation} | nikad | - | "
                             f"{len(times)}/{len(times)} |")
                continue
            std = pstdev(reached) if len(reached) > 1 else 0.0
            lines.append(f"| {overlay} | {aggregation} | {mean(reached):.1f} | "
                         f"{std:.2f} | {len(times) - len(reached)}/{len(times)} |")
    _write(out, lines + [""])

def table_attack_effect_on_time(sweeps, base, out):
    # 7.5: kako delay i selective forwarding uticu na vreme oporavka
    for naziv, kolona, naslov in (("delay", "delay_rounds", "delay napada"),
                                  ("selective", "unresponsive_p",
                                   "selective forwarding napada")):
        path = sweeps.get(naziv)
        if not path or not os.path.exists(path):
            continue
        rows = load(path)
        if "recovery_time" not in rows[0] or kolona not in rows[0]:
            continue
        values = sorted({r[kolona] for r in rows})
        lines = [f"## 7.5 Uticaj {naslov} na vreme oporavka", "",
                 "| strategija | " + " | ".join(f"{kolona}={v:g}" for v in values) + " |",
                 "|---|" + "---|" * len(values)]
        for overlay in OVERLAYS:
            cells = [_time_cell([r["recovery_time"] for r in
                                 _sel(rows, overlay=overlay, **{kolona: v})])
                     for v in values]
            lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
        _write(out, lines + [""])
