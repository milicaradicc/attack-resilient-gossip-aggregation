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


def table_criteria(summary, out):
    from metrics.criteria import CRITERIA, applicable, summarize

    rows = applicable(summary)
    counts = summarize(summary)
    lines = [f"## 3.10 Provera kriterijuma prihvatljivosti (beta <= 0.30, "
             f"{len(rows)} pokretanja)", "",
             "| kriterijum | mera | prag | prolaz | pad | udeo |",
             "|---|---|---|---|---|---|"]
    for c in CRITERIA:
        p = counts[c.spec]["prolaz"]
        f = counts[c.spec]["pad"]
        uk = p + f
        udeo = f"{p / uk:.1%}" if uk else "-"
        prag = f"{c.limit:g}" if c.limit >= 1 else f"{c.limit}"
        lines.append(f"| {c.spec} | {c.label} | <= {prag} | {p} | {f} | {udeo} |")
    _write(out, lines + [""])


def table_criteria_by_overlay(summary, out):    
    from metrics.criteria import CRITERIA, applicable, evaluate_row

    lines = ["## 3.10 Kriterijumi po strategiji i agregaciji", "",
             "| strategija | agregacija | " +
             " | ".join(c.spec for c in CRITERIA) + " | svi |",
             "|---|---|" + "---|" * (len(CRITERIA) + 1)]
    for overlay in OVERLAYS:
        for aggregation in AGGS:
            rows = [r for r in applicable(summary)
                    if r.get("overlay") == overlay and r.get("aggregation") == aggregation]
            if not rows:
                continue
            cells = []
            svi = True
            for c in CRITERIA:
                ocene = [evaluate_row(r)[c.spec] for r in rows]
                prolaz = sum(1 for o in ocene if o is True)
                uk = sum(1 for o in ocene if o is not None)
                cells.append(f"{prolaz}/{uk}" if uk else "-")
                if uk and prolaz < uk:
                    svi = False
            lines.append(f"| {overlay} | {aggregation} | " + " | ".join(cells) +
                         f" | {'DA' if svi else 'ne'} |")
    _write(out, lines + [""])