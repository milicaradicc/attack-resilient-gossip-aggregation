"""7.10 Statisticka obrada rezultata."""

from __future__ import annotations

import os
from statistics import mean, pstdev

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


from analysis.common import (BETAS, OVERLAYS, AGGS, _cell, _mean,
                                      _realized, _sel, _time_cell, _write)


def table_statistics_all(summary_rows, beta, out):
    # 7.10: srednja vrednost, standardna devijacija, minimum i maksimum za
    # SVAKU konfiguraciju, uz koeficijent varijacije kao meru osetljivosti na
    # slucajne overlay varijacije (std / srednja vrednost)
    lines = [f"## 7.10 Statistika po konfiguraciji (beta={beta})", "",
             "| strategija | agregacija | srednja | std | min | max | CV |",
             "|---|---|---|---|---|---|---|"]
    for overlay in OVERLAYS:
        for aggregation in AGGS:
            values = [r["final_err_rel"] for r in
                      _sel(summary_rows, overlay=overlay,
                           aggregation=aggregation, beta=beta)]
            if not values:
                continue
            sr = mean(values)
            std = pstdev(values) if len(values) > 1 else 0.0
            cv = std / sr if sr else 0.0
            lines.append(f"| {overlay} | {aggregation} | {sr:.4f} | {std:.4f} | "
                         f"{min(values):.4f} | {max(values):.4f} | {cv:.3f} |")
    _write(out, lines + [""])

def table_seed_sensitivity(summary_rows, beta, out):
    # 7.10: da li su pojedini seed-ovi proizveli znacajno drugacije rezultate.
    # Za svaku konfiguraciju trazi se seed sa najvecim odstupanjem od proseka.
    lines = [f"## 7.10 Osetljivost na seed (beta={beta})", "",
             "| strategija | agregacija | seed | odstupanje od proseka |",
             "|---|---|---|---|"]
    for overlay in OVERLAYS:
        for aggregation in AGGS:
            rows = _sel(summary_rows, overlay=overlay,
                        aggregation=aggregation, beta=beta)
            if len(rows) < 2:
                continue
            po_seedu = {}
            for row in rows:
                po_seedu.setdefault(row["seed"], []).append(row["final_err_rel"])
            proseci = {seed: mean(v) for seed, v in po_seedu.items()}
            ukupno = mean(proseci.values())
            if not ukupno:
                continue
            najgori = max(proseci, key=lambda s: abs(proseci[s] - ukupno))
            odstupanje = (proseci[najgori] - ukupno) / ukupno
            lines.append(f"| {overlay} | {aggregation} | {najgori} | "
                         f"{odstupanje:+.1%} |")
    _write(out, lines + [""])

def table_statistics(summary, beta, aggregation, out):
    # 7.10: srednja vrednost, standardna devijacija, minimum i maksimum
    lines = [f"## 7.10 Statisticka obrada (beta={beta}, {aggregation})", "",
             "| strategija | srednja | std | min | max |", "|---|---|---|---|---|"]
    for overlay in OVERLAYS:
        values = [r["final_err_rel"] for r in
                  _sel(summary, overlay=overlay, aggregation=aggregation, beta=beta)]
        if not values:
            continue
        lines.append(f"| {overlay} | {mean(values):.4f} | {pstdev(values):.4f} | "
                     f"{min(values):.4f} | {max(values):.4f} |")
    _write(out, lines + [""])
