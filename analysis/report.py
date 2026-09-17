from __future__ import annotations

import argparse
import os

from analysis.loader import load

from analysis.common import table_realized_beta

# 7.1
from analysis.error_by_strategy import (
    fig_err_over_time,
    table_benign_baseline,
    table_error_above_baseline,
    fig_error_boxplot,
    fig_final_error_bars,
    table_error_by_beta)

# 7.2
from analysis.aggregation_functions import (
    fig_profiles,
    table_profile_convergence,
    table_profile_error,
    table_profile_stability,
    table_recovery_by_profile)

# 7.3
from analysis.sybil_penetration import (
    fig_penetration_over_time,
    fig_penetration_vs_beta,
    fig_rejection_reasons,
    table_admission_mechanisms,
    table_compromise_distribution,
    table_penetration_by_beta,
    table_penetration_over_time,
    table_rejection_reasons)

# 7.4
from analysis.eclipse_resilience import (
    fig_bucket_histogram,
    fig_eclipse_over_time,
    fig_victim_neighborhood,
    table_bucket_distribution,
    table_eclipse,
    table_eclipse_counts,
    table_eclipse_counts_guard,
    table_peer_degradation)

# 7.5
from analysis.convergence_time import (
    fig_moving_average,
    table_attack_effect_on_time,
    table_convergence,
    table_convergence_stats,
    table_recovery)

# 7.6
from analysis.estimate_stability import (
    fig_variance_over_time,
    table_attack_effect_on_stability,
    table_stability,
    table_stability_vs_error)

# 7.7
from analysis.peer_diversity import (
    fig_diversity_over_time,
    table_diversity,
    table_diversity_over_time,
    table_diversity_vs_eclipse)

# 7.8
from analysis.overhead import (
    fig_overhead,
    fig_overhead_stacked,
    table_overhead,
    table_overhead_over_time,
    table_overhead_vs_resilience,
    table_tradeoff)

# 7.9
from analysis.combined_attacks import (
    table_amplification,
    table_layer_contribution,
    table_penetration_to_eclipse,
    table_supplementary_attack,
    table_sweep)

# 7.10
from analysis.statistical_analysis import (
    table_seed_sensitivity,
    table_statistics,
    table_statistics_all)


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

    # tabele poglavlja 7, redom kako se u njemu pojavljuju
    # D1: prvo preslikavanje nominalne u realizovanu betu, da se ostale tabele
    # sa "b=..." zaglavljima citaju sa ispravnim apscisama
    # F / 3.10: provera kriterijuma ide prva — daje odgovor na pitanje
    # da li sistem zadovoljava zahteve, pre nego sto slede detalji
    table_criteria(summary, args.tables)
    table_criteria_by_overlay(summary, args.tables)
    table_realized_beta(summary, args.tables)
    table_error_by_beta(summary, args.tables)
    # E2: bazna linija i greska umanjena za nju — bez toga se u 7.1
    # sistemska pristrasnost median/trimmed_mean mesa sa efektom napada
    table_benign_baseline(summary, args.tables)
    table_error_above_baseline(summary, args.tables)
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