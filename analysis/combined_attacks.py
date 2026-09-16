"""7.9 Analiza kombinovanih napada."""

from __future__ import annotations

import os
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


from analysis.common import (BETAS, DOPUNSKE_MERE, OVERLAYS, AGGS, _cell, _mean,
                                      _realized, _sel, _time_cell, _write)


def table_amplification(node_rows, beta, aggregation, out):
    # 7.9: kako degradacija peer set-a pojacava uticaj Byzantine vrednosti.
    # Cvorovi se grupisu po broju napadackih suseda, pa se meri greska bas tih
    # cvorova — time se vidi tacka preloma robusne agregacije.
    if not node_rows:
        return
    last = max(r["round"] for r in node_rows)
    selected = [r for r in node_rows if r["round"] == last and r["beta"] == beta
           and r.get("aggregation") == aggregation]
    if not selected:
        return
    groups = {}
    for row in selected:
        count = round(row["peer_count"] - row["honest_peers"])
        groups.setdefault(count, []).append(row["err_rel"])
    lines = [f"## 7.9 Pojacavanje: napadacki susedi -> greska cvora "
             f"(beta={beta}, {aggregation})", "",
             "| napadackih suseda | broj cvorova | prosecna greska |",
             "|---|---|---|"]
    for count in sorted(groups):
        values = groups[count]
        lines.append(f"| {count} | {len(values)} | {mean(values):.4f} |")
    _write(out, lines + [""])

def table_layer_contribution(summary, beta, out):
    # 7.9: da li odbrana jednog sloja posredno poboljsava otpornost ostalih.
    # Uporedjuju se cetiri kombinacije: bez zastite, samo struktura, samo
    # robusna agregacija, i oba sloja zajedno.
    kombinacije = [("random", "mean", "bez zastite"),
                   ("sybil_resistant", "mean", "samo struktura"),
                   ("random", "trimmed_mean", "samo robusna agregacija"),
                   ("sybil_resistant", "trimmed_mean", "oba sloja")]
    lines = [f"## 7.9 Doprinos slojeva odbrane (beta={beta})", "",
             "| konfiguracija | greska | Sybil penetracija |", "|---|---|---|"]
    for overlay, aggregation, opis in kombinacije:
        rows = _sel(summary, overlay=overlay, aggregation=aggregation, beta=beta)
        if not rows:
            continue
        lines.append(f"| {opis} | {_mean(rows, 'final_err_rel'):.4f} | "
                     f"{_mean(rows, 'final_sybil_penetration'):.4f} |")
    _write(out, lines + [""])

def table_penetration_to_eclipse(eclipse_summary, out):
    # 7.9: kako Sybil penetracija povecava verovatnocu Eclipse izolacije
    if not eclipse_summary:
        return
    lines = ["## 7.9 Veza penetracije i Eclipse izolacije", "",
             "| strategija | Sybil penetracija | eclipse rate |", "|---|---|---|"]
    for overlay in OVERLAYS:
        rows = _sel(eclipse_summary, overlay=overlay)
        if not rows:
            continue
        lines.append(f"| {overlay} | {_mean(rows, 'final_sybil_penetration'):.4f} | "
                     f"{_mean(rows, 'final_eclipse_rate'):.3f} |")
    _write(out, lines + [""])

def table_supplementary_attack(rows, column, title, out):
    # 6.2: napadi koji nisu deo glavnog scenarija mere se istim skupom mera,
    # da bi se njihovi efekti mogli uporediti medjusobno i sa glavnom matricom
    if not rows or column not in rows[0]:
        return
    values = sorted({r[column] for r in rows})
    lines = [f"## {title}", ""]
    for field, label in DOPUNSKE_MERE:
        if field not in rows[0]:
            continue
        lines += [f"**{label}**", "",
                  "| strategija | " + " | ".join(f"{column}={v:g}" for v in values) + " |",
                  "|---|" + "---|" * len(values)]
        for overlay in OVERLAYS:
            cells = []
            for value in values:
                selected = _sel(rows, overlay=overlay, **{column: value})
                if not selected:
                    cells.append("-")
                elif field == "recovery_time":
                    cells.append(_time_cell([r[field] for r in selected]))
                else:
                    cells.append(f"{_mean(selected, field):.4f}")
            lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
        lines.append("")
    _write(out, lines)

def table_sweep(rows, column, metrics, title, out):
    # 7.3/7.6/7.8: dopunske ablacije (flooding, churn, selective)
    if not rows or column not in rows[0]:
        return
    values = sorted({r[column] for r in rows})
    lines = [f"## {title}", ""]
    for metric, label in metrics:
        lines += [f"**{label}**", "",
                  "| strategija | " + " | ".join(f"{column}={v}" for v in values) + " |",
                  "|---|" + "---|" * len(values)]
        for overlay in OVERLAYS:
            cells = [f"{_mean(_sel(rows, overlay=overlay, **{column: v}), metric):.4f}"
                     for v in values]
            lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
        lines.append("")
    _write(out, lines)
