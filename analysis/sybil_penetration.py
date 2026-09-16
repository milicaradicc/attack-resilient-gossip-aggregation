"""7.3 Analiza Sybil penetracije."""

from __future__ import annotations

import os
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.loader import filter_rows, group_stats

from analysis.common import (BETAS, OVERLAYS, AGGS, _cell, _mean,
                                      _realized, _sel, _time_cell, _write)


def fig_penetration_vs_beta(summary, out_dir):
    betas = sorted({r["beta"] for r in summary})
    stats = group_stats(summary, ("overlay", "beta"), "final_sybil_penetration")
    # D1: na x-osi stoji REALIZOVANA beta. Nominalna beta je samo oznaka
    # konfiguracije; sa celobrojnim brojem cvorova stvarni udeo zlonamernih
    # odstupa od nje (npr. N=10, beta=0.2 -> 3/13 = 0.231), pa bi tacke inace
    # stajale na pogresnim apscisama.
    xs = [_realized(summary, b) for b in betas]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for ov in OVERLAYS:
        ys = [stats.get((ov, b), (0.0, 0.0))[0] for b in betas]
        ax.plot(xs, ys, marker="o", label=ov)
    ax.set_xlabel("realizovana beta (nominalna: " +
                  ", ".join(str(b) for b in betas) + ")")
    ax.set_ylabel("Sybil penetration")
    ax.set_title("Sybil penetration vs malicious share")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "penetration_vs_beta.png"), dpi=130)
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

def table_admission_mechanisms(rows, out):
    # 7.3: koliko age-gating i prag skora smanjuju uspesnost Sybil napada.
    # Prikazuje se ukupan broj odbijenih kandidata, jer penetracija ostaje
    # zanemarljiva i bez pragova (izbacivanje najslabijeg suseda je odlucujuce).
    if not rows or "age_min" not in rows[0] or "score_threshold" not in rows[0]:
        return
    ages = sorted({r["age_min"] for r in rows})
    thresholds = sorted({r["score_threshold"] for r in rows})
    for field, label, fmt in (("rejected_ratio", "udeo odbijenih kandidata", ".3f"),
                              ("final_sybil_penetration", "Sybil penetracija", ".4f")):
        lines = [f"## 7.3 Mehanizmi pristupa: {label}", "",
                 "| age_min | " + " | ".join(f"skor >= {t}" for t in thresholds) + " |",
                 "|---|" + "---|" * len(thresholds)]
        for age in ages:
            cells = [format(_mean(_sel(rows, age_min=age, score_threshold=t), field), fmt)
                     for t in thresholds]
            lines.append(f"| {age} | " + " | ".join(cells) + " |")
        _write(out, lines + [""])

def table_penetration_over_time(round_rows, beta, out):
    # 7.3: promene penetracije kroz vreme
    if not round_rows:
        return
    last = max(r["round"] for r in round_rows)
    marks = [r for r in (0, 10, 11, 15, 25, last) if r <= last]
    sub = filter_rows(round_rows, beta=beta, aggregation="trimmed_mean")
    lines = [f"## 7.3 Penetracija kroz vreme (beta={beta})", "",
             "| strategija | " + " | ".join(f"runda {r}" for r in marks) + " |",
             "|---|" + "---|" * len(marks)]
    for overlay in OVERLAYS:
        cells = [f"{_mean(_sel(sub, overlay=overlay, round=r), 'sybil_penetration'):.4f}"
                 for r in marks]
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])

def table_compromise_distribution(node_rows, beta, out):
    # 7.3: raspodela kompromitovanosti peer set-ova umesto samo proseka
    if not node_rows:
        return
    last = max(r["round"] for r in node_rows)
    lines = [f"## 7.3 Raspodela kompromitovanosti peer set-ova (runda {last})", "",
             "| strategija | broj Sybil suseda | udeo cvorova |", "|---|---|---|"]
    for overlay in OVERLAYS:
        selected = [r for r in node_rows
               if r["round"] == last and r["overlay"] == overlay and r["beta"] == beta]
        if not selected:
            continue
        counts = Counter(round(r["sybil_share"] * r["peer_count"]) for r in selected)
        for count in sorted(counts):
            lines.append(f"| {overlay} | {count} | {counts[count] / len(selected):.1%} |")
    _write(out, lines + [""])

def fig_penetration_over_time(round_rows, beta, out_dir):
    # 7.3: penetracija po rundama
    fig, ax = plt.subplots(figsize=(8, 4.5))
    sub = filter_rows(round_rows, beta=beta, aggregation="trimmed_mean")
    for ov in OVERLAYS:
        series = group_stats(filter_rows(sub, overlay=ov), ("round",), "sybil_penetration")
        xs = sorted(series)
        ax.plot([x[0] for x in xs], [series[x][0] for x in xs], label=ov)
    ax.set_xlabel("round_no")
    ax.set_ylabel("Sybil penetracija")
    ax.set_title(f"Sybil penetracija kroz vreme (beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "penetration_over_time.png"), dpi=130)
    plt.close(fig)

def table_penetration_by_beta(summary, out):
    # 7.3: Sybil penetracija po beta
    lines = ["## 7.3 Sybil penetracija po beta", "",
             "| strategija | " + " | ".join(f"b={b}" for b in BETAS) + " |",
             "|---|" + "---|" * len(BETAS)]
    for overlay in OVERLAYS:
        cells = [f"{_mean(_sel(summary, overlay=overlay, beta=b), 'final_sybil_penetration'):.4f}"
                 for b in BETAS]
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])

def table_rejection_reasons(summary, beta, out):
    # 7.3: struktura odbijanja po mehanizmu
    lines = [f"## 7.3 Struktura odbijanja (beta={beta})", "",
             "| strategija | PoW | starost | skor | bucket |", "|---|---|---|---|---|"]
    for overlay in OVERLAYS:
        rows = _sel(summary, overlay=overlay, beta=beta)
        cells = [f"{_mean(rows, c):.2f}" for c in ("rej_pow", "rej_age", "rej_score", "rej_bucket")]
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])
