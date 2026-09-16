"""7.4 Analiza Eclipse otpornosti."""

from __future__ import annotations

import os
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.loader import filter_rows, group_stats, load

from analysis.common import (BETAS, OVERLAYS, AGGS, _cell, _mean,
                                      _realized, _sel, _time_cell, _write)


def fig_victim_neighborhood(node_rows, beta, out_dir):
    # 7.4: kako izgleda komsiluk ciljane zrtve kroz vreme (per-node podaci, 4.9)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for overlay in OVERLAYS:
        selected = [r for r in node_rows
               if r["overlay"] == overlay and r["node_id"] == 0
               and r["beta"] == beta and r["seed"] == 1]
        if not selected:
            continue
        selected.sort(key=lambda r: r["round"])
        ax.plot([r["round"] for r in selected],
                [r["honest_peers"] for r in selected], label=overlay)
    ax.set_xlabel("round_no")
    ax.set_ylabel("count honest suseda zrtve")
    ax.set_title(f"Komsiluk ciljane zrtve tokom napada (beta={beta})")
    ax.axhline(0, linestyle="--", linewidth=0.8)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "victim_neighborhood.png"), dpi=130)
    plt.close(fig)

def fig_eclipse_over_time(round_rows, beta, out_dir):
    # 7.4: Eclipse success rate kroz rounde. Koriste se podaci iz ciljanog
    # scenarija (configs/eclipse.json), jer u glavnoj matrici napad je "sirok"
    # pa do potpune izolacije ne dolazi ni kod referentne strategije.
    fig, ax = plt.subplots(figsize=(8, 4.5))
    sub = filter_rows(round_rows, beta=beta, aggregation="trimmed_mean")
    for ov in OVERLAYS:
        series = group_stats(filter_rows(sub, overlay=ov), ("round",), "eclipse_rate")
        xs = sorted(series)
        ax.plot([x[0] for x in xs], [series[x][0] for x in xs], label=ov)
    ax.set_xlabel("round_no")
    ax.set_ylabel("eclipse rate")
    ax.set_title(f"Eclipse success rate kroz vreme (beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "eclipse_over_time.png"), dpi=130)
    plt.close(fig)

def fig_bucket_histogram(node_rows, beta, out_dir):
    # 7.4: raspodela peer-ova po bucket-ima u poslednjoj rundi
    if not node_rows:
        return
    last = max(r["round"] for r in node_rows)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    width = 0.25
    for i, ov in enumerate(OVERLAYS):
        selected = [r for r in node_rows
               if r["round"] == last and r["overlay"] == ov and r["beta"] == beta]
        if not selected:
            continue
        counts = Counter(round(r["bucket_occupancy"] * r["peer_count"]) for r in selected)
        keys = sorted(counts)
        ax.bar([k + (i - 1) * width for k in keys],
               [counts[k] / len(selected) for k in keys], width=width, label=ov)
    svi = sorted({round(r["bucket_occupancy"] * r["peer_count"])
                  for r in node_rows if r["round"] == last and r["beta"] == beta})
    ax.set_xticks(svi)
    ax.set_xlabel("najveci count peer-ova iz istog bucketa")
    ax.set_ylabel("udeo cvorova")
    ax.set_title(f"Raspodela zauzetosti bucket-a (round_no {last}, beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "bucket_histogram.png"), dpi=130)
    plt.close(fig)


BETAS = [0.0, 0.1, 0.2, 0.3]

def table_eclipse(eclipse_summary, out):
    # 7.4: ciljani Eclipse napad
    if not eclipse_summary:
        return
    betas = sorted({r["beta"] for r in eclipse_summary})
    lines = ["## 7.4 Ciljani Eclipse napad (eclipse_rate)", "",
             "| strategija | " + " | ".join(f"b={b}" for b in betas) + " |",
             "|---|" + "---|" * len(betas)]
    for overlay in OVERLAYS:
        cells = [f"{_mean(_sel(eclipse_summary, overlay=overlay, beta=b), 'final_eclipse_rate'):.3f}"
                 for b in betas]
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])

def table_eclipse_counts(node_rows, out):
    # 7.4: broj izolovanih cvorova, ne samo udeo
    if not node_rows:
        return
    last = max(r["round"] for r in node_rows)
    betas = sorted({r["beta"] for r in node_rows})
    lines = [f"## 7.4 Broj izolovanih cvorova (runda {last})", "",
             "| strategija | " + " | ".join(f"b={b}" for b in betas) + " |",
             "|---|" + "---|" * len(betas)]
    for overlay in OVERLAYS:
        cells = []
        for beta in betas:
            selected = [r for r in node_rows if r["round"] == last
                   and r["overlay"] == overlay and r["beta"] == beta]
            if not selected:
                cells.append("-")
                continue
            izolovanih = sum(1 for r in selected if r["eclipsed"])
            seedova = len({r["seed"] for r in selected})
            cells.append(f"{izolovanih / max(seedova, 1):.1f} od {len(selected) // max(seedova, 1)}")
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])

def table_peer_degradation(node_rows, beta, out):
    # 7.4: kako peer poisoning degradira peer set kroz vreme i koliko brzo.
    # Prati se prosecan broj honest suseda ciljanog cvora po rundama.
    if not node_rows:
        return
    last = max(r["round"] for r in node_rows)
    marks = [r for r in (0, 1, 2, 5, 10, 25, last) if r <= last]
    lines = [f"## 7.4 Degradacija peer set-a zrtve (beta={beta})", "",
             "| strategija | " + " | ".join(f"runda {r}" for r in marks) + " |",
             "|---|" + "---|" * len(marks)]
    for overlay in OVERLAYS:
        cells = []
        for round_no in marks:
            selected = [r for r in node_rows if r["round"] == round_no
                   and r["overlay"] == overlay and r["beta"] == beta
                   and r["node_id"] == 0]
            cells.append(f"{_mean(selected, 'honest_peers'):.1f}" if selected else "-")
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])

def table_bucket_distribution(node_rows, beta, out):
    # 7.4: raspodela peer-ova po bucket-ima — najveci broj iz istog bucketa
    if not node_rows:
        return
    last = max(r["round"] for r in node_rows)
    lines = [f"## 7.4 Raspodela peer-ova po bucket-ima (runda {last}, beta={beta})", "",
             "| strategija | najvise iz istog bucketa | udeo cvorova |", "|---|---|---|"]
    for overlay in OVERLAYS:
        selected = [r for r in node_rows if r["round"] == last
               and r["overlay"] == overlay and r["beta"] == beta]
        if not selected:
            continue
        distribution = Counter(round(r["bucket_occupancy"] * r["peer_count"]) for r in selected)
        for count in sorted(distribution):
            lines.append(f"| {overlay} | {count} | {distribution[count] / len(selected):.1%} |")
    _write(out, lines + [""])

def table_eclipse_counts_guard(path, out, beta):
    if not os.path.exists(path):
        return
    rows = load(path)
    table_eclipse_counts(rows, out)
    table_peer_degradation(rows, beta, out)
    table_bucket_distribution(rows, beta, out)
