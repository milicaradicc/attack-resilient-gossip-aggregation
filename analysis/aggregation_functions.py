"""7.2 Uticaj agregacione funkcije na otpornost sistema."""

from __future__ import annotations

import os
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.loader import group_stats

from analysis.common import (BETAS, OVERLAYS, AGGS, _cell, _mean,
                                      _realized, _sel, _time_cell, _write)


def fig_profiles(ablation_summary, out_dir):
    profiles = ["coordinated", "extreme", "random", "low_biased"]
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

def table_recovery_by_profile(ablation, out):
    if not ablation or "recovery_time" not in ablation[0]:
        return
    profiles = sorted({r["byzantine_profile"] for r in ablation})
    lines = ["## 7.2 Vreme oporavka po profilu", "",
             "| agregacija | " + " | ".join(profiles) + " |",
             "|---|" + "---|" * len(profiles)]
    for aggregation in AGGS:
        cells = [_time_cell([r["recovery_time"] for r in
                             _sel(ablation, aggregation=aggregation,
                                  byzantine_profile=p)])
                 for p in profiles]
        lines.append(f"| {aggregation} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])

def _profile_table(rows, field, title, fmt, out):
    # 7.2: ponasanje agregacionih funkcija po Byzantine profilima vrednosti.
    # D7: ablacija sada ukrsta i overlay strategiju, jer spec 7.2 trazi analizu
    # koliko OVERLAY DEGRADACIJA utice na efikasnost robusnih estimatora. Bez
    # overlay-a kao dimenzije reda tabela bi usrednjavala preko strategija i
    # sakrila upravo taj efekat.
    profiles = sorted({r["byzantine_profile"] for r in rows})
    overlays = [o for o in OVERLAYS if any(r.get("overlay") == o for r in rows)]
    lines = [f"## {title}", "",
             "| strategija | agregacija | " + " | ".join(profiles) + " |",
             "|---|---|" + "---|" * len(profiles)]
    for overlay in overlays:
        for aggregation in AGGS:
            cells = [format(_mean(_sel(rows, overlay=overlay,
                                       aggregation=aggregation,
                                       byzantine_profile=p), field), fmt)
                     for p in profiles]
            lines.append(f"| {overlay} | {aggregation} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])

def table_profile_error(ablation, out):
    if ablation:
        _profile_table(ablation, "final_err_rel",
                       "7.2 Agregaciona greska po profilu", ".4f", out)

def table_profile_stability(ablation, out):
    if ablation:
        _profile_table(ablation, "stability",
                       "7.2 Varijansa procene po profilu", ".2e", out)

def table_profile_convergence(ablation, out):
    # -1 znaci da sistem nikada nije dostigao prag, pa se broji odvojeno
    if not ablation:
        return
    # D7: i ovde overlay ulazi kao dimenzija reda (vidi _profile_table)
    profiles = sorted({r["byzantine_profile"] for r in ablation})
    overlays = [o for o in OVERLAYS if any(r.get("overlay") == o for r in ablation)]
    lines = ["## 7.2 Vreme konvergencije po profilu", "",
             "| strategija | agregacija | " + " | ".join(profiles) + " |",
             "|---|---|" + "---|" * len(profiles)]
    for overlay in overlays:
        for aggregation in AGGS:
            cells = []
            for profile in profiles:
                times = [r["convergence_time"] for r in
                         _sel(ablation, overlay=overlay, aggregation=aggregation,
                              byzantine_profile=profile)]
                reached = [t for t in times if t >= 0]
                if not reached:
                    cells.append("nikad")
                elif len(reached) == len(times):
                    cells.append(f"{mean(reached):.1f}")
                else:
                    cells.append(f"{mean(reached):.1f} ({len(times) - len(reached)}/"
                                 f"{len(times)} nikad)")
            lines.append(f"| {overlay} | {aggregation} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])
