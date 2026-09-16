"""Zajednicke konstante i pomocne funkcije za izvestaje."""

from __future__ import annotations

import os
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


OVERLAYS = ["random", "sybil_resistant", "eclipse_resistant"]
AGGS = ["mean", "median", "trimmed_mean"]
BETAS = [0.0, 0.1, 0.2, 0.3]

# mere koje se prikazuju za dopunske napade (7.9)
DOPUNSKE_MERE = [("final_err_rel", "relativna greska"),
                 ("final_sybil_penetration", "Sybil penetracija"),
                 ("recovery_time", "vreme oporavka"),
                 ("control_overhead", "kontrolni overhead"),
                 ("rejected_ratio", "udeo odbijenih")]


def _cell(stats, key):
    m, s = stats.get(key, (float("nan"), 0.0))
    return f"{m:.3e} ± {s:.1e}"

def _realized(summary, nominal):
    # prosek realizovane bete preko svih pokretanja sa datom nominalnom betom;
    # ako kolone nema (stariji rezultati), vraca nominalnu
    vals = [r["realized_beta"] for r in summary
            if r.get("beta") == nominal and isinstance(r.get("realized_beta"), (int, float))]
    return mean(vals) if vals else nominal

def table_realized_beta(summary, out):
    # D1: preslikavanje nominalne u realizovanu betu po velicini mreze
    betas = sorted({r["beta"] for r in summary})
    sizes = sorted({r["n_honest"] for r in summary})
    lines = ["## Nominalna naspram realizovane bete", "",
             "| N | " + " | ".join(f"b={b}" for b in betas) + " |",
             "|" + "---|" * (len(betas) + 1)]
    for n in sizes:
        cells = []
        for b in betas:
            rows = [r for r in summary
                    if r.get("n_honest") == n and r.get("beta") == b]
            rb = [r["realized_beta"] for r in rows
                  if isinstance(r.get("realized_beta"), (int, float))]
            nb = [r["n_byzantine"] for r in rows
                  if isinstance(r.get("n_byzantine"), (int, float))]
            ns = [r["n_sybil"] for r in rows
                  if isinstance(r.get("n_sybil"), (int, float))]
            if rb:
                cells.append(f"{mean(rb):.4f} (f={int(mean(nb))}, S={int(mean(ns))})")
            else:
                cells.append("-")
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    with open(out, "a") as f:
        f.write("\n".join(lines) + "\n\n")

def _time_cell(times):
    reached = [t for t in times if t >= 0]
    if not reached:
        return "nikad"
    if len(reached) == len(times):
        return f"{mean(reached):.1f}"
    return f"{mean(reached):.1f} ({len(times) - len(reached)}/{len(times)} nikad)"

def _write(out, lines):
    with open(out, "a") as f:
        f.write("\n".join(lines) + "\n")

def _mean(rows, field):
    values = [r[field] for r in rows]
    return mean(values) if values else float("nan")

def _sel(rows, **conditions):
    return [r for r in rows
            if all(r.get(k) == v for k, v in conditions.items())]
