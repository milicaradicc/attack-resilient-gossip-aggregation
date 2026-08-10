from __future__ import annotations

import argparse

from experiments.scenarios import AttackConfig, run_attack, run_benign, scenario_ids
from experiments.setup import RunConfig
from identity.registry import IdentityParams


def benign_demo(cfg):
    print(f"BENIGNO: n_honest={cfg.n_honest} K={cfg.peer_set_size} "
          f"rounds={cfg.num_rounds} seed={cfg.global_seed}\n")
    print(f"{'agregacija':>14} {'err_rel':>14} {'spread':>14}")
    for name in ("mean", "median", "trimmed_mean"):
        last = run_benign(cfg, name)[-1]
        print(f"{name:>14} {last.err_rel:>14.3e} {last.spread:>14.3e}")


def attack_demo():
    cfg = AttackConfig()
    params = IdentityParams()
    honest, byzantine, sybil = scenario_ids(cfg)
    total = len(honest) + len(byzantine) + len(sybil)
    beta = (len(byzantine) + len(sybil)) / total
    print(f"\nNAPAD: honest={len(honest)} byzantine={len(byzantine)} sybil={len(sybil)} "
          f"beta={beta:.2f} rounds={cfg.base.num_rounds}\n")

    strategies = ("random", "sybil_resistant", "eclipse_resistant")
    aggregations = ("mean", "median", "trimmed_mean")

    print("strukturne metrike (nezavisne od agregacije):")
    print(f"{'strategija':>18} {'sybil_pen':>10} {'eclipse':>9} {'diversity':>10}")
    for strat in strategies:
        last = run_attack(cfg, strat, "mean", params)[-1]
        print(f"{strat:>18} {last.sybil_penetration:>10.3f} "
              f"{last.eclipse_rate:>9.3f} {last.peer_diversity:>10.3f}")

    print("\nerr_rel (strategija x agregacija):")
    print(f"{'strategija':>18} " + " ".join(f"{a:>12}" for a in aggregations))
    for strat in strategies:
        cells = [f"{run_attack(cfg, strat, agg, params)[-1].err_rel:>12.3e}" for agg in aggregations]
        print(f"{strat:>18} " + " ".join(cells))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["benign", "attack", "both"], default="both")
    args = parser.parse_args()
    if args.mode in ("benign", "both"):
        benign_demo(RunConfig())
    if args.mode in ("attack", "both"):
        attack_demo()


if __name__ == "__main__":
    main()
