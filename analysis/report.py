from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from collections import Counter
from statistics import mean, pstdev, pvariance

from analysis.loader import filter_rows, group_stats, group_values, load

OVERLAYS = ["random", "sybil_resistant", "eclipse_resistant"]
AGGS = ["mean", "median", "trimmed_mean"]


def _cell(stats, key):
    m, s = stats.get(key, (float("nan"), 0.0))
    return f"{m:.3e} ± {s:.1e}"


def table_final_error(summary, beta, out_md):
    rows_b = filter_rows(summary, beta=beta)
    stats = group_stats(rows_b, ("overlay", "aggregation"), "final_err_rel")
    lines = [f"## Final err_rel (beta={beta}, mean ± std across seeds)", "",
             "| overlay \\ aggregation | " + " | ".join(AGGS) + " |",
             "|" + "---|" * (len(AGGS) + 1)]
    for ov in OVERLAYS:
        lines.append("| " + ov + " | " + " | ".join(_cell(stats, (ov, a)) for a in AGGS) + " |")
    with open(out_md, "a") as f:
        f.write("\n".join(lines) + "\n\n")


def table_penetration(summary, out_md):
    betas = sorted({r["beta"] for r in summary})
    stats = group_stats(summary, ("overlay", "beta"), "final_sybil_penetration")
    lines = ["## Sybil penetration by overlay x beta (mean across seeds)", "",
             "| overlay \\ beta | " + " | ".join(str(b) for b in betas) + " |",
             "|" + "---|" * (len(betas) + 1)]
    for ov in OVERLAYS:
        cells = []
        for b in betas:
            m, _ = stats.get((ov, b), (float("nan"), 0.0))
            cells.append(f"{m:.3f}")
        lines.append("| " + ov + " | " + " | ".join(cells) + " |")
    with open(out_md, "a") as f:
        f.write("\n".join(lines) + "\n\n")


def fig_err_over_time(round_rows, beta, out_dir):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, agg in zip(axes, ["mean", "median"]):
        sub = filter_rows(round_rows, beta=beta, aggregation=agg)
        for ov in OVERLAYS:
            series = group_stats(filter_rows(sub, overlay=ov), ("round",), "err_rel")
            xs = sorted(series)
            ys = [series[x][0] for x in xs]
            ax.plot([x[0] for x in xs], ys, label=ov)
        ax.set_title(f"aggregation = {agg}")
        ax.set_xlabel("round")
        ax.set_yscale("log")
        ax.legend()
    axes[0].set_ylabel("err_rel (log)")
    fig.suptitle(f"Aggregation error over time (beta={beta})")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "err_over_time.png"), dpi=130)
    plt.close(fig)


def fig_final_error_bars(summary, beta, out_dir):
    stats = group_stats(filter_rows(summary, beta=beta), ("overlay", "aggregation"), "final_err_rel")
    x = range(len(AGGS))
    width = 0.25
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, ov in enumerate(OVERLAYS):
        ys = [stats.get((ov, a), (0.0, 0.0))[0] for a in AGGS]
        ax.bar([xi + (i - 1) * width for xi in x], ys, width, label=ov)
    ax.set_xticks(list(x))
    ax.set_xticklabels(AGGS)
    ax.set_yscale("log")
    ax.set_ylabel("final err_rel (log)")
    ax.set_title(f"Final aggregation error by overlay x aggregation (beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "final_error_bars.png"), dpi=130)
    plt.close(fig)


def _realized(summary, nominal):
    vals = [r["realized_beta"] for r in summary
            if r.get("beta") == nominal and isinstance(r.get("realized_beta"), (int, float))]
    return mean(vals) if vals else nominal


def table_realized_beta(summary, out):
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


def fig_penetration_vs_beta(summary, out_dir):
    betas = sorted({r["beta"] for r in summary})
    stats = group_stats(summary, ("overlay", "beta"), "final_sybil_penetration")
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


def fig_overhead(summary, beta, out_dir):
    stats_c = group_stats(filter_rows(summary, beta=beta, aggregation="mean"),
                          ("overlay",), "control_overhead")
    stats_r = group_stats(filter_rows(summary, beta=beta, aggregation="mean"),
                          ("overlay",), "rejected_ratio")
    x = range(len(OVERLAYS))
    fig, ax1 = plt.subplots(figsize=(7, 4.5))
    ax1.bar([xi - 0.2 for xi in x], [stats_c.get((ov,), (0, 0))[0] for ov in OVERLAYS],
            0.4, label="control overhead")
    ax2 = ax1.twinx()
    ax2.bar([xi + 0.2 for xi in x], [stats_r.get((ov,), (0, 0))[0] for ov in OVERLAYS],
            0.4, color="orange", label="rejected ratio")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(OVERLAYS)
    ax1.set_ylabel("control msgs / node / round")
    ax2.set_ylabel("rejected ratio")
    ax1.set_title(f"Cost of defense (beta={beta})")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "overhead.png"), dpi=130)
    plt.close(fig)


def fig_error_boxplot(summary, beta, aggregation, out_dir):
    groups = group_values(filter_rows(summary, beta=beta, aggregation=aggregation),
                          ("overlay",), "final_err_rel")
    data = [groups.get((ov,), []) for ov in OVERLAYS]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.boxplot(data, tick_labels=OVERLAYS)
    ax.set_yscale("log")
    ax.set_ylabel("final err_rel (log)")
    ax.set_title(f"Error spread across seeds (beta={beta}, {aggregation})")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "error_boxplot.png"), dpi=130)
    plt.close(fig)


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


def fig_victim_neighborhood(node_rows, beta, out_dir):
    # 7.4: kako izgleda komsiluk ciljane zrtve kroz vreme (per-node podaci, 4.9)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for overlay in OVERLAYS:
        sel = [r for r in node_rows
               if r["overlay"] == overlay and r["node_id"] == 0
               and r["beta"] == beta and r["seed"] == 1]
        if not sel:
            continue
        sel.sort(key=lambda r: r["round"])
        ax.plot([r["round"] for r in sel],
                [r["honest_peers"] for r in sel], label=overlay)
    ax.set_xlabel("runda")
    ax.set_ylabel("broj honest suseda zrtve")
    ax.set_title(f"Komsiluk ciljane zrtve tokom napada (beta={beta})")
    ax.axhline(0, linestyle="--", linewidth=0.8)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "victim_neighborhood.png"), dpi=130)
    plt.close(fig)


def _time_cell(times):
    reached = [t for t in times if t >= 0]
    if not reached:
        return "nikad"
    if len(reached) == len(times):
        return f"{mean(reached):.1f}"
    return f"{mean(reached):.1f} ({len(times) - len(reached)}/{len(times)} nikad)"


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


def table_convergence(summary_rows, beta, out):
    # 6.3.2: -1 znaci da sistem nikada nije dostigao prag i ne sme se usrednjavati
    # sa brojem rundi, pa se prikazuje odvojeno kao udeo pokretanja bez konvergencije
    lines = [f"## 7.5 Vreme konvergencije (beta={beta})", "",
             "| overlay \\ aggregation | " + " | ".join(AGGS) + " |",
             "|---|" + "---|" * len(AGGS)]
    for overlay in OVERLAYS:
        cells = []
        for aggregation in AGGS:
            sel = [r for r in summary_rows
                   if r["overlay"] == overlay and r["aggregation"] == aggregation
                   and r["beta"] == beta]
            times = [r["convergence_time"] for r in sel]
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
    ax.set_xlabel("runda")
    ax.set_ylabel("eclipse rate")
    ax.set_title(f"Eclipse success rate kroz vreme (beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "eclipse_over_time.png"), dpi=130)
    plt.close(fig)


def fig_diversity_over_time(round_rows, beta, out_dir):
    # 7.7: Shannon entropija peer set-ova kroz rounde
    fig, ax = plt.subplots(figsize=(8, 4.5))
    sub = filter_rows(round_rows, beta=beta, aggregation="trimmed_mean")
    for ov in OVERLAYS:
        series = group_stats(filter_rows(sub, overlay=ov), ("round",), "peer_diversity")
        xs = sorted(series)
        ax.plot([x[0] for x in xs], [series[x][0] for x in xs], label=ov)
    ax.set_xlabel("runda")
    ax.set_ylabel("Shannon entropija")
    ax.set_title(f"Peer diversity kroz vreme (beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "diversity_over_time.png"), dpi=130)
    plt.close(fig)


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
    ax.set_xlabel("runda")
    ax.set_ylabel(f"varijansa procene (prozor {window})")
    ax.set_yscale("log")
    ax.set_title(f"Stabilnost procene kroz vreme (eclipse_resistant, beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "variance_over_time.png"), dpi=130)
    plt.close(fig)


def fig_bucket_histogram(node_rows, beta, out_dir):
    # 7.4: raspodela peer-ova po bucket-ima u poslednjoj rundi
    if not node_rows:
        return
    last = max(r["round"] for r in node_rows)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    width = 0.25
    for i, ov in enumerate(OVERLAYS):
        sel = [r for r in node_rows
               if r["round"] == last and r["overlay"] == ov and r["beta"] == beta]
        if not sel:
            continue
        counts = Counter(round(r["bucket_occupancy"] * r["peer_count"]) for r in sel)
        keys = sorted(counts)
        ax.bar([k + (i - 1) * width for k in keys],
               [counts[k] / len(sel) for k in keys], width=width, label=ov)
    svi = sorted({round(r["bucket_occupancy"] * r["peer_count"])
                  for r in node_rows if r["round"] == last and r["beta"] == beta})
    ax.set_xticks(svi)
    ax.set_xlabel("najveci broj peer-ova iz istog bucketa")
    ax.set_ylabel("udeo cvorova")
    ax.set_title(f"Raspodela zauzetosti bucket-a (runda {last}, beta={beta})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "bucket_histogram.png"), dpi=130)
    plt.close(fig)


BETAS = [0.0, 0.1, 0.2, 0.3]


def _write(out, lines):
    with open(out, "a") as f:
        f.write("\n".join(lines) + "\n")


def _mean(rows, field):
    values = [r[field] for r in rows]
    return mean(values) if values else float("nan")


def _sel(rows, **conditions):
    return [r for r in rows
            if all(r.get(k) == v for k, v in conditions.items())]


def table_error_by_beta(summary, out):
    # 7.1: greska po strategiji, agregaciji i udelu zlonamernih
    lines = ["## 7.1 Relativna greska po beta", "",
             "| strategija | agregacija | " + " | ".join(f"b={b}" for b in BETAS) + " |",
             "|---|---|" + "---|" * len(BETAS)]
    for overlay in OVERLAYS:
        for aggregation in AGGS:
            cells = [f"{_mean(_sel(summary, overlay=overlay, aggregation=aggregation, beta=b), 'final_err_rel'):.4f}"
                     for b in BETAS]
            lines.append(f"| {overlay} | {aggregation} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])


def table_profiles(ablation, out):
    # 7.2: Byzantine profili vrednosti
    if not ablation:
        return
    profiles = sorted({r["byzantine_profile"] for r in ablation})
    lines = ["## 7.2 Byzantine profili vrednosti", "",
             "| profil | " + " | ".join(AGGS) + " |", "|---|" + "---|" * len(AGGS)]
    for profile in profiles:
        cells = [f"{_mean(_sel(ablation, byzantine_profile=profile, aggregation=a), 'final_err_rel'):.4f}"
                 for a in AGGS]
        lines.append(f"| {profile} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])


def _profile_table(rows, field, title, fmt, out):
    # 7.2: ponasanje agregacionih funkcija po Byzantine profilima vrednosti
    profiles = sorted({r["byzantine_profile"] for r in rows})
    lines = [f"## {title}", "",
             "| agregacija | " + " | ".join(profiles) + " |",
             "|---|" + "---|" * len(profiles)]
    for aggregation in AGGS:
        cells = [format(_mean(_sel(rows, aggregation=aggregation,
                                   byzantine_profile=p), field), fmt)
                 for p in profiles]
        lines.append(f"| {aggregation} | " + " | ".join(cells) + " |")
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
    profiles = sorted({r["byzantine_profile"] for r in ablation})
    lines = ["## 7.2 Vreme konvergencije po profilu", "",
             "| agregacija | " + " | ".join(profiles) + " |",
             "|---|" + "---|" * len(profiles)]
    for aggregation in AGGS:
        cells = []
        for profile in profiles:
            times = [r["convergence_time"] for r in
                     _sel(ablation, aggregation=aggregation, byzantine_profile=profile)]
            reached = [t for t in times if t >= 0]
            if not reached:
                cells.append("nikad")
            elif len(reached) == len(times):
                cells.append(f"{mean(reached):.1f}")
            else:
                cells.append(f"{mean(reached):.1f} ({len(times) - len(reached)}/"
                             f"{len(times)} nikad)")
        lines.append(f"| {aggregation} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])


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
        sel = [r for r in node_rows
               if r["round"] == last and r["overlay"] == overlay and r["beta"] == beta]
        if not sel:
            continue
        counts = Counter(round(r["sybil_share"] * r["peer_count"]) for r in sel)
        for broj in sorted(counts):
            lines.append(f"| {overlay} | {broj} | {counts[broj] / len(sel):.1%} |")
    _write(out, lines + [""])


def fig_penetration_over_time(round_rows, beta, out_dir):
    # 7.3: penetracija po rundama
    fig, ax = plt.subplots(figsize=(8, 4.5))
    sub = filter_rows(round_rows, beta=beta, aggregation="trimmed_mean")
    for ov in OVERLAYS:
        series = group_stats(filter_rows(sub, overlay=ov), ("round",), "sybil_penetration")
        xs = sorted(series)
        ax.plot([x[0] for x in xs], [series[x][0] for x in xs], label=ov)
    ax.set_xlabel("runda")
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


def table_stability(summary, beta, out):
    # 7.6: varijansa procene u konvergencijskom prozoru
    lines = [f"## 7.6 Stabilnost procene (beta={beta})", "",
             "| strategija | " + " | ".join(AGGS) + " |", "|---|" + "---|" * len(AGGS)]
    for overlay in OVERLAYS:
        cells = [f"{_mean(_sel(summary, overlay=overlay, aggregation=a, beta=beta), 'stability'):.2e}"
                 for a in AGGS]
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])


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


def table_overhead(summary, beta, out):
    # 7.8: cena zastitnih mehanizama
    lines = [f"## 7.8 Overhead (beta={beta})", "",
             "| strategija | control | data | udeo odbijenih |", "|---|---|---|---|"]
    for overlay in OVERLAYS:
        rows = _sel(summary, overlay=overlay, beta=beta)
        lines.append(f"| {overlay} | {_mean(rows, 'control_overhead'):.2f} | "
                     f"{_mean(rows, 'data_overhead'):.2f} | "
                     f"{_mean(rows, 'rejected_ratio'):.3f} |")
    _write(out, lines + [""])


DOPUNSKE_MERE = [("final_err_rel", "relativna greska"),
                 ("final_sybil_penetration", "Sybil penetracija"),
                 ("recovery_time", "vreme oporavka"),
                 ("control_overhead", "kontrolni overhead"),
                 ("rejected_ratio", "udeo odbijenih")]


def table_amplification(node_rows, beta, aggregation, out):
    # 7.9: kako degradacija peer set-a pojacava uticaj Byzantine vrednosti.
    # Cvorovi se grupisu po broju napadackih suseda, pa se meri greska bas tih
    # cvorova — time se vidi tacka preloma robusne agregacije.
    if not node_rows:
        return
    last = max(r["round"] for r in node_rows)
    sel = [r for r in node_rows if r["round"] == last and r["beta"] == beta
           and r.get("aggregation") == aggregation]
    if not sel:
        return
    grupe = {}
    for row in sel:
        broj = round(row["peer_count"] - row["honest_peers"])
        grupe.setdefault(broj, []).append(row["err_rel"])
    lines = [f"## 7.9 Pojacavanje: napadacki susedi -> greska cvora "
             f"(beta={beta}, {aggregation})", "",
             "| napadackih suseda | broj cvorova | prosecna greska |",
             "|---|---|---|"]
    for broj in sorted(grupe):
        vrednosti = grupe[broj]
        lines.append(f"| {broj} | {len(vrednosti)} | {mean(vrednosti):.4f} |")
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


def table_overhead_vs_resilience(summary_rows, beta, out):
    # 7.8: odnos izmedju placenog overhead-a i postignute otpornosti.
    # Referentna strategija sluzi kao osnova: koliko dodatnih kontrolnih poruka
    # je placeno i koliko je puta smanjena greska odnosno penetracija.
    osnova = _sel(summary_rows, overlay="random", aggregation="trimmed_mean", beta=beta)
    if not osnova:
        return
    o_control = _mean(osnova, "control_overhead")
    o_greska = _mean(osnova, "final_err_rel")
    o_pen = _mean(osnova, "final_sybil_penetration")
    lines = [f"## 7.8 Overhead naspram otpornosti (beta={beta}, trimmed_mean)", "",
             "| strategija | dodatni control | greska manja | penetracija manja |",
             "|---|---|---|---|"]
    for overlay in OVERLAYS:
        rows = _sel(summary_rows, overlay=overlay, aggregation="trimmed_mean", beta=beta)
        if not rows:
            continue
        control = _mean(rows, "control_overhead")
        greska = _mean(rows, "final_err_rel")
        pen = _mean(rows, "final_sybil_penetration")
        dodatni = f"{control - o_control:+.2f} ({(control / o_control - 1) * 100:+.0f}%)"
        puta_greska = "-" if greska <= 0 else f"{o_greska / greska:.0f}x"
        puta_pen = "-" if pen <= 0 else f"{o_pen / pen:.0f}x"
        lines.append(f"| {overlay} | {dodatni} | {puta_greska} | {puta_pen} |")
    _write(out, lines + [""])


def table_tradeoff(summary_rows, beta, out):
    # 7.8: koji pristup ostvaruje najbolji kompromis izmedju bezbednosti,
    # stabilnosti i overhead-a — sve tri mere na jednom mestu
    lines = [f"## 7.8 Kompromis bezbednost / stabilnost / overhead (beta={beta})", "",
             "| strategija | agregacija | greska | penetracija | varijansa | control |",
             "|---|---|---|---|---|---|"]
    for overlay in OVERLAYS:
        for aggregation in AGGS:
            rows = _sel(summary_rows, overlay=overlay, aggregation=aggregation, beta=beta)
            if not rows:
                continue
            lines.append(f"| {overlay} | {aggregation} | "
                         f"{_mean(rows, 'final_err_rel'):.4f} | "
                         f"{_mean(rows, 'final_sybil_penetration'):.4f} | "
                         f"{_mean(rows, 'stability'):.2e} | "
                         f"{_mean(rows, 'control_overhead'):.2f} |")
    _write(out, lines + [""])


def table_overhead_over_time(round_rows, beta, out):
    # 7.8: overhead po rundi, da se vidi kada zastita pocinje da kosta
    if not round_rows:
        return
    last = max(r["round"] for r in round_rows)
    marks = [r for r in (1, 5, 10, 11, 15, 25, last) if r <= last]
    sub = filter_rows(round_rows, beta=beta, aggregation="trimmed_mean")
    lines = [f"## 7.8 Kontrolne poruke po rundi (beta={beta})", "",
             "| strategija | " + " | ".join(f"runda {r}" for r in marks) + " |",
             "|---|" + "---|" * len(marks)]
    for overlay in OVERLAYS:
        cells = [f"{_mean(_sel(sub, overlay=overlay, round=r), 'control_msgs'):.0f}"
                 for r in marks]
        lines.append(f"| {overlay} | " + " | ".join(cells) + " |")
    _write(out, lines + [""])


def fig_overhead_stacked(round_rows, beta, out_dir):
    # 7.8: control i data saobracaj po rundi, jedno preko drugog
    fig, ax = plt.subplots(figsize=(8, 4.5))
    sub = filter_rows(round_rows, beta=beta, aggregation="trimmed_mean",
                      overlay="eclipse_resistant")
    control = group_stats(sub, ("round",), "control_msgs")
    data = group_stats(sub, ("round",), "data_msgs")
    xs = sorted(control)
    rounds = [x[0] for x in xs]
    c = [control[x][0] for x in xs]
    d = [data[x][0] for x in xs]
    ax.stackplot(rounds, d, c, labels=["data", "control"])
    ax.set_xlabel("runda")
    ax.set_ylabel("broj poruka")
    ax.set_title(f"Saobracaj po rundi (eclipse_resistant, beta={beta})")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "overhead_stacked.png"), dpi=130)
    plt.close(fig)


def table_diversity_vs_eclipse(node_rows, beta, out):
    # 7.7: povezanost diversity metrike sa Eclipse otpornoscu. Cvorovi se
    # grupisu po broju honest suseda, pa se meri njihova entropija — time se
    # vidi da li pad raznovrsnosti prethodi izolaciji.
    if not node_rows:
        return
    last = max(r["round"] for r in node_rows)
    sel = [r for r in node_rows if r["round"] == last and r["beta"] == beta]
    if not sel:
        return
    grupe = {}
    for row in sel:
        grupe.setdefault(round(row["honest_peers"]), []).append(row)
    lines = [f"## 7.7 Diversity i Eclipse otpornost (runda {last}, beta={beta})", "",
             "| honest suseda | broj cvorova | entropija | izolovanih |",
             "|---|---|---|---|"]
    for broj in sorted(grupe):
        redovi = grupe[broj]
        izolovanih = sum(1 for r in redovi if r["eclipsed"])
        lines.append(f"| {broj} | {len(redovi)} | "
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
            greska = _mean(rows, "final_err_rel")
            varijansa = _mean(rows, "stability")
            if greska < 0.05 and varijansa < 0.01:
                ocena = "tacan i stabilan"
            elif greska < 0.05:
                ocena = "tacan, ali osciluje"
            elif varijansa < 0.01:
                ocena = "stabilno pogresan"
            else:
                ocena = "netacan i nestabilan"
            lines.append(f"| {overlay} | {aggregation} | {greska:.4f} | "
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
    ax.set_xlabel("runda")
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
            sel = [r for r in node_rows if r["round"] == last
                   and r["overlay"] == overlay and r["beta"] == beta]
            if not sel:
                cells.append("-")
                continue
            izolovanih = sum(1 for r in sel if r["eclipsed"])
            seedova = len({r["seed"] for r in sel})
            cells.append(f"{izolovanih / max(seedova, 1):.1f} od {len(sel) // max(seedova, 1)}")
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
        for runda in marks:
            sel = [r for r in node_rows if r["round"] == runda
                   and r["overlay"] == overlay and r["beta"] == beta
                   and r["node_id"] == 0]
            cells.append(f"{_mean(sel, 'honest_peers'):.1f}" if sel else "-")
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
        sel = [r for r in node_rows if r["round"] == last
               and r["overlay"] == overlay and r["beta"] == beta]
        if not sel:
            continue
        raspodela = Counter(round(r["bucket_occupancy"] * r["peer_count"]) for r in sel)
        for broj in sorted(raspodela):
            lines.append(f"| {overlay} | {broj} | {raspodela[broj] / len(sel):.1%} |")
    _write(out, lines + [""])


def table_eclipse_counts_guard(path, out, beta):
    if not os.path.exists(path):
        return
    rows = load(path)
    table_eclipse_counts(rows, out)
    table_peer_degradation(rows, beta, out)
    table_bucket_distribution(rows, beta, out)


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
                sel = _sel(rows, overlay=overlay, **{column: value})
                if not sel:
                    cells.append("-")
                elif field == "recovery_time":
                    cells.append(_time_cell([r[field] for r in sel]))
                else:
                    cells.append(f"{_mean(sel, field):.4f}")
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


def main() -> None:
    parser = argparse.ArgumentParser()
    # podrazumevano se izvestaj pravi iz rezultata dobijenih u Docker okruzenju;
    # --source inprocess prebacuje na in-process rezultate
    parser.add_argument("--source", default="docker", choices=["docker", "inprocess"])
    parser.add_argument("--round", default=None)
    parser.add_argument("--summary", default=None)
    parser.add_argument("--ablation", default=None)
    parser.add_argument("--nodes", default=None)
    parser.add_argument("--figures", default="figures")
    parser.add_argument("--tables", default=None)
    parser.add_argument("--beta", type=float, default=0.3)
    args = parser.parse_args()
    base = os.path.join("results", args.source)
    args.round = args.round or os.path.join(base, "main.csv")
    args.summary = args.summary or os.path.join(base, "main_summary.csv")
    args.ablation = args.ablation or os.path.join(base, "ablation_summary.csv")
    args.tables = args.tables or os.path.join(base, "tables.md")
    args.nodes = args.nodes or os.path.join(base, "main_nodes.csv")
    eclipse_path = args.summary
    sweeps = {name: os.path.join(base, f"{name}_summary.csv")
              for name in ("flooding", "churn", "selective", "delay", "admission")}
    if not os.path.exists(args.summary):
        raise SystemExit(
            f"nema rezultata: {args.summary}\n"
            f"pokreni matricu za izvor '{args.source}', ili koristi --source "
            f"{'inprocess' if args.source == 'docker' else 'docker'}")

    os.makedirs(args.figures, exist_ok=True)
    open(args.tables, "w").close()

    summary = load(args.summary)
    ablation = load(args.ablation) if os.path.exists(args.ablation) else []
    eclipse = load(eclipse_path) if os.path.exists(eclipse_path) else []

    table_realized_beta(summary, args.tables)
    table_error_by_beta(summary, args.tables)
    table_profile_error(ablation, args.tables)
    table_profile_stability(ablation, args.tables)
    table_profile_convergence(ablation, args.tables)
    table_recovery_by_profile(ablation, args.tables)
    table_penetration_by_beta(summary, args.tables)
    table_rejection_reasons(summary, args.beta, args.tables)
    if os.path.exists(sweeps["admission"]):
        table_admission_mechanisms(load(sweeps["admission"]), args.tables)
    if os.path.exists(args.round):
        table_penetration_over_time(load(args.round), args.beta, args.tables)
    if os.path.exists(sweeps["flooding"]):
        table_sweep(load(sweeps["flooding"]), "flooding",
                    [("final_sybil_penetration", "Sybil penetracija"),
                     ("rejected_ratio", "udeo odbijenih")],
                    "7.3 Uticaj peer flooding scenarija", args.tables)
    table_eclipse(eclipse, args.tables)
    # 7.4: broj izolovanih cvorova, degradacija peer set-a i raspodela po bucket-ima
    table_eclipse_counts_guard(args.nodes, args.tables, args.beta)
    fig_final_error_bars(summary, args.beta, args.figures)
    fig_penetration_vs_beta(summary, args.figures)
    fig_overhead(summary, args.beta, args.figures)
    fig_rejection_reasons(summary, args.beta, args.figures)
    fig_error_boxplot(summary, args.beta, "median", args.figures)

    if os.path.exists(args.round):
        fig_err_over_time(load(args.round), args.beta, args.figures)
    if os.path.exists(args.ablation):
        fig_profiles(load(args.ablation), args.figures)

    if os.path.exists(args.nodes):
        nodes = load(args.nodes)
        fig_victim_neighborhood(nodes, args.beta, args.figures)
        fig_bucket_histogram(nodes, args.beta, args.figures)
        table_compromise_distribution(nodes, args.beta, args.tables)
        table_diversity_vs_eclipse(nodes, args.beta, args.tables)
    if os.path.exists(args.round):
        fig_eclipse_over_time(load(args.round), args.beta, args.figures)
    table_convergence(summary, args.beta, args.tables)
    table_recovery(summary, args.beta, args.tables)
    table_convergence_stats(summary, args.beta, args.tables)
    table_attack_effect_on_time(sweeps, base, args.tables)
    table_stability(summary, args.beta, args.tables)
    table_stability_vs_error(summary, args.beta, args.tables)
    table_attack_effect_on_stability(sweeps, args.tables)
    if os.path.exists(args.round):
        round_rows = load(args.round)
        table_diversity(round_rows, args.tables)
        table_diversity_over_time(round_rows, args.beta, args.tables)
        fig_diversity_over_time(round_rows, args.beta, args.figures)
        fig_penetration_over_time(round_rows, args.beta, args.figures)
        fig_variance_over_time(round_rows, args.beta, 5, args.figures)
        fig_moving_average(round_rows, args.beta, 5, args.figures)
    table_overhead(summary, args.beta, args.tables)
    table_overhead_vs_resilience(summary, args.beta, args.tables)
    table_tradeoff(summary, args.beta, args.tables)
    if os.path.exists(args.round):
        rr = load(args.round)
        table_overhead_over_time(rr, args.beta, args.tables)
        fig_overhead_stacked(rr, args.beta, args.figures)
    # 7.9: medjuzavisnost napada i doprinos slojeva odbrane
    table_layer_contribution(summary, args.beta, args.tables)
    table_penetration_to_eclipse(eclipse, args.tables)
    main_nodes = os.path.join(base, "main_nodes.csv")
    if os.path.exists(main_nodes):
        table_amplification(load(main_nodes), args.beta, "trimmed_mean", args.tables)
    # 6.2: dopunski napadi izvan glavnog scenarija, isti skup mera za svaki
    for naziv, kolona, naslov in (
            ("flooding", "flooding", "7.9 Peer flooding"),
            ("churn", "churn_period", "7.9 Churn"),
            ("delay", "delay_rounds", "7.9 Delay"),
            ("selective", "unresponsive_p", "7.9 Selective forwarding")):
        if os.path.exists(sweeps[naziv]):
            table_supplementary_attack(load(sweeps[naziv]), kolona, naslov, args.tables)
    table_statistics(summary, args.beta, "trimmed_mean", args.tables)
    table_statistics_all(summary, args.beta, args.tables)
    table_seed_sensitivity(summary, args.beta, args.tables)
    print(f"tables -> {args.tables}")
    print(f"figures -> {args.figures}/")


if __name__ == "__main__":
    main()