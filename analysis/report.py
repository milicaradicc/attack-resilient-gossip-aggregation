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


def fig_penetration_vs_beta(summary, out_dir):
    betas = sorted({r["beta"] for r in summary})
    stats = group_stats(summary, ("overlay", "beta"), "final_sybil_penetration")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for ov in OVERLAYS:
        ys = [stats.get((ov, b), (0.0, 0.0))[0] for b in betas]
        ax.plot(betas, ys, marker="o", label=ov)
    ax.set_xlabel("beta")
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
    profiles = ["coordinated", "extreme", "random", "low_biased", "stale"]
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
    args.nodes = args.nodes or os.path.join(base, "eclipse_nodes.csv")
    eclipse_path = os.path.join(base, "eclipse_summary.csv")
    sweeps = {name: os.path.join(base, f"{name}_summary.csv")
              for name in ("flooding", "churn", "selective")}
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

    # tabele poglavlja 7, redom kako se u njemu pojavljuju
    table_error_by_beta(summary, args.tables)
    table_profiles(ablation, args.tables)
    table_penetration_by_beta(summary, args.tables)
    table_rejection_reasons(summary, args.beta, args.tables)
    table_eclipse(eclipse, args.tables)
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
        fig_victim_neighborhood(nodes, 0.4, args.figures)
        fig_bucket_histogram(nodes, 0.4, args.figures)
    eclipse_round = os.path.join(base, "eclipse.csv")
    if os.path.exists(eclipse_round):
        fig_eclipse_over_time(load(eclipse_round), 0.4, args.figures)
    table_convergence(summary, args.beta, args.tables)
    if os.path.exists(sweeps["selective"]):
        table_sweep(load(sweeps["selective"]), "unresponsive_p",
                    [("final_err_rel", "relativna greska"),
                     ("final_sybil_penetration", "Sybil penetracija")],
                    "7.5 Selective forwarding", args.tables)
    table_stability(summary, args.beta, args.tables)
    if os.path.exists(sweeps["churn"]):
        table_sweep(load(sweeps["churn"]), "churn_period",
                    [("final_sybil_penetration", "Sybil penetracija"),
                     ("final_err_rel", "relativna greska")],
                    "7.6 Churn napad", args.tables)
    if os.path.exists(args.round):
        round_rows = load(args.round)
        table_diversity(round_rows, args.tables)
        fig_diversity_over_time(round_rows, args.beta, args.figures)
        fig_variance_over_time(round_rows, args.beta, 5, args.figures)
    table_overhead(summary, args.beta, args.tables)
    if os.path.exists(sweeps["flooding"]):
        table_sweep(load(sweeps["flooding"]), "flooding",
                    [("control_overhead", "kontrolni overhead"),
                     ("rejected_ratio", "udeo odbijenih"),
                     ("final_sybil_penetration", "Sybil penetracija")],
                    "7.8 Flooding napad", args.tables)
    table_statistics(summary, args.beta, "trimmed_mean", args.tables)
    print(f"tables -> {args.tables}")
    print(f"figures -> {args.figures}/")


if __name__ == "__main__":
    main()