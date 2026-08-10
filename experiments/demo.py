from __future__ import annotations

import random

from aggregation import get_aggregation
from attacks.scenario import AttackParams, Scenario
from core.rng import make_rng
from experiments.setup import RunConfig, build_nodes
from identity.buckets import bucket_of
from identity.observation import Observation
from identity.pow import solve_pow
from identity.registry import IdentityParams, IdentityRegistry
from metrics.experiment_metrics import ExperimentMetrics, RoundCounters
from sampling import get_strategy

LINE = "=" * 70
FOCUS = 0


def hr(title):
    print(f"\n{LINE}\n  {title}\n{LINE}")


def admission_reason(strategy, node, candidate, r, params):
    if candidate in node.peers:
        return "vec je peer"
    if hasattr(strategy, "pow_valid") and not strategy.pow_valid(candidate):
        return "nevazeci PoW"
    obs = node.observations.get(candidate)
    age = 0 if obs is None else r - obs.first_seen_round
    if params and age < params.age_min:
        return f"premlad (age {age} < {params.age_min})"
    if hasattr(strategy, "score") and params:
        s = strategy.score(node, candidate, r)
        if s < params.score_threshold:
            return f"nizak skor ({s:.2f} < {params.score_threshold})"
    if hasattr(strategy, "bucket") and params:
        b = strategy.bucket(candidate)
        occ = sum(1 for p in node.peers if strategy.bucket(p) == b)
        if occ >= params.max_per_bucket:
            return f"bucket {b} pun ({occ}/{params.max_per_bucket})"
    return None


def kind(nid, scenario):
    if nid in scenario.sybil_ids:
        return "SYBIL"
    if nid in scenario.byzantine_ids:
        return "BYZANTINE"
    return "honest"


def main():
    n_honest, n_byz, n_syb = 6, 1, 2
    rounds, activate = 12, 3
    coord = 1000.0
    strategy_name, agg_name = "eclipse_resistant", "median"

    base = RunConfig(n_honest=n_honest, peer_set_size=5, num_rounds=rounds, global_seed=42)
    id_params = IdentityParams(pow_difficulty_bits=8, age_min=2, age_max=8,
                               score_threshold=0.7, num_buckets=6, max_per_bucket=2)

    nodes = build_nodes(base)
    for node in nodes.values():
        for peer in node.peers:
            node.observations[peer] = Observation(first_seen_round=0, last_seen_round=0)

    honest = set(nodes.keys())
    byz = set(range(n_honest, n_honest + n_byz))
    syb = set(range(n_honest + n_byz, n_honest + n_byz + n_syb))
    x_star = sum(n.x_local for n in nodes.values()) / len(nodes)

    registry = IdentityRegistry()
    for i in honest | byz | syb:
        registry.register(i, solve_pow(str(i), id_params.pow_difficulty_bits))

    scenario = Scenario(honest, byz, syb, AttackParams(
        byzantine_profile="coordinated", coordinated_value=coord,
        x_star=x_star, activate_round=activate))
    strategy = get_strategy(strategy_name, base.peer_set_size, registry, id_params)
    aggregation = get_aggregation(agg_name)
    metrics = ExperimentMetrics(x_star=x_star, num_buckets=id_params.num_buckets)
    rng = make_rng(base.global_seed, "demo")

    hr("KONFIGURACIJA SISTEMA")
    print(f"  strategija odbrane : {strategy_name}")
    print(f"  agregacija         : {agg_name}")
    print(f"  runde              : {rounds}   napad se aktivira u rundi {activate}")
    print(f"  prava sredina x*   : {x_star:.3f}")

    hr("IDENTITETI")
    for i in sorted(honest):
        print(f"  cvor {i}  [{kind(i, scenario):9}]  x_i={nodes[i].x_local:7.2f}  "
              f"bucket={bucket_of(str(i), id_params.num_buckets)}  peers={nodes[i].peers}")
    for i in sorted(byz | syb):
        print(f"  cvor {i}  [{kind(i, scenario):9}]  PoW resen (nonce={registry.nonce_of(i)}), "
              f"bucket={bucket_of(str(i), id_params.num_buckets)}")
    print(f"\n  Napadaci ({len(byz | syb)}) pokusavaju da se ubace u peer set-ove i emituju {coord}.")

    metrics.record(0, nodes, scenario)

    for r in range(1, rounds + 1):
        hr(f"RUNDA {r}")
        if r == activate:
            print("  >>> NAPAD AKTIVIRAN <<<\n")

        offered = scenario.offer_candidates(nodes[FOCUS], r, rng)
        if offered:
            print(f"  Discovery za cvor {FOCUS} (peers={nodes[FOCUS].peers}):")
            for c in offered:
                accepted = strategy.accept_peer(nodes[FOCUS], c, r)
                nodes[FOCUS].observations.setdefault(c, Observation(r, r))
                if accepted:
                    print(f"    kandidat {c} [{kind(c, scenario):9}] -> PRIHVACEN")
                else:
                    why = admission_reason(strategy, nodes[FOCUS], c, r, id_params)
                    print(f"    kandidat {c} [{kind(c, scenario):9}] -> ODBIJEN ({why})")

        acc = rej = 0
        for node in nodes.values():
            for c in scenario.offer_candidates(node, r, rng):
                node.observations.setdefault(c, Observation(r, r))
                if c in node.peers:
                    continue
                if strategy.accept_peer(node, c, r):
                    if len(node.peers) >= strategy.max_peers:
                        v = strategy.evict_peer(node, r)
                        if v is None:
                            continue
                        node.peers.remove(v)
                    node.peers.append(c)
                    acc += 1
                else:
                    rej += 1
        print(f"  Admission (svi cvorovi): {acc} prihvaceno, {rej} odbijeno")

        broadcast = {}
        for hid, node in nodes.items():
            broadcast[hid] = scenario.broadcast_value(hid, node.estimate, r)
        for m in scenario.malicious_ids:
            broadcast[m] = scenario.broadcast_value(m, 0.0, r)
        if scenario.active(r):
            print(f"  Napadaci emituju vrednost = {coord}")

        own = {hid: n.estimate for hid, n in nodes.items()}
        fp = nodes[FOCUS].peers
        recv = [broadcast[p] for p in fp]
        for hid, node in nodes.items():
            rr = [broadcast[p] for p in node.peers]
            node.estimate = aggregation.aggregate(own[hid], rr)
        print(f"  Agregacija cvora {FOCUS}: own={own[FOCUS]:.2f}, peers={fp}")
        print(f"    primljeno={[round(v, 1) for v in recv]}  ->  nova procena={nodes[FOCUS].estimate:.2f}")

        m = metrics.record(r, nodes, scenario)
        print(f"  METRIKE: err={m.err_rel:.3e}  sybil_pen={m.sybil_penetration:.3f}  "
              f"eclipse={m.eclipse_rate:.2f}  diversity={m.peer_diversity:.2f}")

    hr("ZAVRSNI REZULTAT")
    last = metrics.rows[-1]
    avg_est = sum(n.estimate for n in nodes.values()) / len(nodes)
    print(f"  finalna greska err_rel     : {last.err_rel:.3e}")
    print(f"  Sybil penetracija          : {last.sybil_penetration:.3f}")
    print(f"  Eclipse rate               : {last.eclipse_rate:.2f}")
    print(f"  prosecna procena cvorova   : {avg_est:.2f}   (prava vrednost x*={x_star:.2f})")

    contrast = _run_silent("random", agg_name, base, id_params, honest, byz, syb, x_star, coord, activate)
    hr("POREDJENJE: ISTI NAPAD BEZ ODBRANE (random)")
    print(f"  random strategija -> err={contrast.err_rel:.3e}  sybil_pen={contrast.sybil_penetration:.3f}")
    print(f"  eclipse odbrana   -> err={last.err_rel:.3e}  sybil_pen={last.sybil_penetration:.3f}")

    if last.err_rel < 0.1 and last.sybil_penetration < 0.15:
        print(f"\n  >>> ODBRANA DRZI: napadaci su odbijani svake runde (nizak skor / premladi),")
        print(f"      penetracija ostala niska, agregacija blizu prave vrednosti.")
        print(f"      Bez odbrane (random) ista mreza kolabira na err={contrast.err_rel:.2e}. <<<")
    else:
        print(f"\n  >>> Napadaci su vremenom prodrli; err porastao. Vidi poredjenje gore. <<<")


def _run_silent(strategy_name, agg_name, base, id_params, honest, byz, syb, x_star, coord, activate):
    nodes = build_nodes(base)
    for node in nodes.values():
        for peer in node.peers:
            node.observations[peer] = Observation(first_seen_round=0, last_seen_round=0)
    registry = IdentityRegistry()
    for i in honest | byz | syb:
        registry.register(i, solve_pow(str(i), id_params.pow_difficulty_bits))
    scenario = Scenario(set(honest), set(byz), set(syb), AttackParams(
        byzantine_profile="coordinated", coordinated_value=coord,
        x_star=x_star, activate_round=activate))
    strategy = get_strategy(strategy_name, base.peer_set_size, registry, id_params)
    aggregation = get_aggregation(agg_name)
    metrics = ExperimentMetrics(x_star=x_star, num_buckets=id_params.num_buckets)
    rng = make_rng(base.global_seed, "demo")
    metrics.record(0, nodes, scenario)
    for r in range(1, base.num_rounds + 1):
        for node in nodes.values():
            for c in scenario.offer_candidates(node, r, rng):
                node.observations.setdefault(c, Observation(r, r))
                if c in node.peers:
                    continue
                if strategy.accept_peer(node, c, r):
                    if len(node.peers) >= strategy.max_peers:
                        v = strategy.evict_peer(node, r)
                        if v is None:
                            continue
                        node.peers.remove(v)
                    node.peers.append(c)
        broadcast = {hid: scenario.broadcast_value(hid, n.estimate, r) for hid, n in nodes.items()}
        for m in scenario.malicious_ids:
            broadcast[m] = scenario.broadcast_value(m, 0.0, r)
        own = {hid: n.estimate for hid, n in nodes.items()}
        for hid, node in nodes.items():
            node.estimate = aggregation.aggregate(own[hid], [broadcast[p] for p in node.peers])
        metrics.record(r, nodes, scenario)
    return metrics.rows[-1]


if __name__ == "__main__":
    main()
