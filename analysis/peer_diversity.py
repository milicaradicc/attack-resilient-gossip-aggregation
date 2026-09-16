"""7.7 Analiza peer diversity metrike."""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.loader import filter_rows, group_stats

from analysis.common import (BETAS, OVERLAYS, AGGS, _cell, _mean,
                                      _realized, _sel, _time_cell, _write)


def fig_diversity_over_time(round_rows, beta, out_dir):
    # 7.7: Shannon entropija peer set-ova kroz rounde
    fig, ax = plt.subplots(figsize=(8, 4.5))
    sub = filter_rows(round_rows, beta=beta, aggregation="trimmed_mean")
    for ov in OVERLAYS:
        series = group_stats(filter_rows(sub, overlay=ov), ("round",), "peer_diversity")
        xs = sorted(series)
        ax.plot([x[0] for x in xs], [series[x][0] for x in xs], label=ov)
    ax.set_xlabel("round_no")
    ax.set_ylabel("Shannon entropija")
    ax.set_title(f"Peer diversity kroz vreme (beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "diversity_over_time.png"), dpi=130)
    plt.close(fig)

def table_diversity(round_rows, out):
    # 7.7: Shannon entropija u poslednjoj rundi
    if not round_rows:
        return
    last = max(r["round"] for r in round_rows)
    final = [r for r in round_rows if r["round"] == last]
    lines = [f"## 7.7 Peer diversity (runda {last})", "",
             "| strategija | " + " | ".join(f"b={b}" for b in BETAS) + " |",
             "|---|" + "---|" * len(BETAS)]
    for overlay in OVERLAYS:
        cells = [f"{_mean(_sel(final, overlay=overlay, beta=b), 'peer_diversity'):.4f}"
                 for b in BETAS]
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])

def table_diversity_vs_eclipse(node_rows, beta, out):
    # 7.7: povezanost diversity metrike sa Eclipse otpornoscu. Cvorovi se
    # grupisu po broju honest suseda, pa se meri njihova entropija — time se
    # vidi da li pad raznovrsnosti prethodi izolaciji.
    if not node_rows:
        return
    last = max(r["round"] for r in node_rows)
    selected = [r for r in node_rows if r["round"] == last and r["beta"] == beta]
    if not selected:
        return
    groups = {}
    for row in selected:
        groups.setdefault(round(row["honest_peers"]), []).append(row)
    lines = [f"## 7.7 Diversity i Eclipse otpornost (runda {last}, beta={beta})", "",
             "| honest suseda | broj cvorova | entropija | izolovanih |",
             "|---|---|---|---|"]
    for count in sorted(groups):
        redovi = groups[count]
        izolovanih = sum(1 for r in redovi if r["eclipsed"])
        lines.append(f"| {count} | {len(redovi)} | "
                     f"{_mean(redovi, 'peer_diversity'):.4f} | {izolovanih} |")
    _write(out, lines + [""])

def table_diversity_over_time(round_rows, beta, out):
    # 7.7: kako peer poisoning utice na entropiju kroz vreme
    if not round_rows:
        return
    last = max(r["round"] for r in round_rows)
    marks = [r for r in (0, 10, 11, 15, 25, last) if r <= last]
    sub = filter_rows(round_rows, beta=beta, aggregation="trimmed_mean")
    lines = [f"## 7.7 Entropija kroz vreme (beta={beta})", "",
             "| strategija | " + " | ".join(f"runda {r}" for r in marks) + " |",
             "|---|" + "---|" * len(marks)]
    for overlay in OVERLAYS:
        cells = [f"{_mean(_sel(sub, overlay=overlay, round=r), 'peer_diversity'):.4f}"
                 for r in marks]
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])
