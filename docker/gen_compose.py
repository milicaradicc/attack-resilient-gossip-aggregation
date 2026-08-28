from __future__ import annotations

import argparse

from core.setup import malicious_counts
from experiments.config import load_defaults


def counts(n_honest, beta, byzantine_fraction=None):
    # ista formula kao u core/setup.py (jedno mesto)
    if byzantine_fraction is None:
        byzantine_fraction = load_defaults()["byzantine_fraction"]
    return malicious_counts(n_honest, beta, byzantine_fraction)


def generate(args):
    if args.matrix:
        from experiments.config import load_matrix
        specs = load_matrix(args.matrix)
        total = max(s.n_honest + sum(s.malicious_counts()) for s in specs)
        n_byz = n_syb = 0
    else:
        n_byz, n_syb = counts(args.n_honest, args.beta)
        total = args.n_honest + n_byz + n_syb
    env = {
        "ROLE": "controller",
        **({"MODE": "matrix", "MATRIX_CONFIG": args.matrix, "MATRIX_OUT": args.matrix_out}
           if args.matrix else {}), "N_HONEST": args.n_honest, "BETA": args.beta,
        "ROUNDS": args.rounds, "SEED": args.seed, "WARMUP": args.warmup,
        "PEER_SET_SIZE": args.peer_set_size, "STRATEGY": args.strategy,
        "AGGREGATION": args.aggregation, "BYZANTINE_PROFILE": args.profile,
        "COORDINATED_VALUE": args.coordinated_value, "POW_BITS": args.pow_bits,
        "NUM_BUCKETS": args.num_buckets, "TIMEOUT_ROUNDS": args.timeout_rounds,
        "TRIM_ALPHA": args.trim_alpha, "FLOODING": args.flooding,
        "CHURN_PERIOD": args.churn_period, "UNRESPONSIVE_P": args.unresponsive_p,
        "SELECTIVE_P": args.selective_p, "PORT": args.port,
    }
    lines = ["services:", "  controller:",
             "    build:", "      context: ..", "      dockerfile: docker/Dockerfile",
             "    environment:"]
    for k, v in env.items():
        lines.append(f"      {k}: \"{v}\"")
    lines += ["    ports:", f"      - \"{args.port}:{args.port}\"",
              "    volumes:", "      - ./results:/app/results"]
    for i in range(total):
        lines += [f"  node{i}:",
                  "    build:", "      context: ..", "      dockerfile: docker/Dockerfile",
                  "    environment:", "      ROLE: node", f"      NODE_ID: \"{i}\"",
                  *(["      MODE: matrix"] if args.matrix else []),
                  f"      CONTROLLER_URL: http://controller:{args.port}",
                  "    depends_on:", "      - controller"]
    return "\n".join(lines) + "\n", total, n_byz, n_syb


def main():
    d = load_defaults()
    p = argparse.ArgumentParser()
    p.add_argument("--n-honest", type=int, default=d["n_honest"][0])
    p.add_argument("--beta", type=float, default=d["beta"][0])
    p.add_argument("--rounds", type=int, default=d["num_rounds"])
    p.add_argument("--warmup", type=int, default=d["warmup"])
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--peer-set-size", type=int, default=d["peer_set_size"])
    p.add_argument("--strategy", default=d["overlay"][0])
    p.add_argument("--aggregation", default=d["aggregation"][0])
    p.add_argument("--profile", default=d["byzantine_profile"][0])
    p.add_argument("--coordinated-value", type=float, default=d["coordinated_value"])
    p.add_argument("--pow-bits", type=int, default=d["pow_difficulty_bits"])
    p.add_argument("--num-buckets", type=int, default=d["num_buckets"])
    p.add_argument("--timeout-rounds", type=int, default=d["timeout_rounds"])
    p.add_argument("--trim-alpha", type=float, default=d["trim_alpha"])
    p.add_argument("--flooding", type=int, default=d["flooding"])
    p.add_argument("--churn-period", type=int, default=d["churn_period"])
    p.add_argument("--unresponsive-p", type=float, default=d["unresponsive_p"])
    p.add_argument("--selective-p", type=float, default=d["selective_p"])
    p.add_argument("--matrix", default=None)
    p.add_argument("--matrix-out", default="results/distributed_matrix.csv")
    p.add_argument("--port", type=int, default=d["docker_port"])
    p.add_argument("--out", default=d["docker_compose_out"])
    a = p.parse_args()
    text, total, n_byz, n_syb = generate(a)
    with open(a.out, "w") as f:
        f.write(text)
    if a.matrix:
        from experiments.config import load_matrix
        print(f"wrote {a.out}: matrix mode, {len(load_matrix(a.matrix))} konfiguracija, "
              f"{total} node containers")
        print(f"config: {a.matrix} -> {a.matrix_out}")
    else:
        print(f"wrote {a.out}: {a.n_honest} honest + {n_byz} byzantine + {n_syb} sybil "
              f"= {total} node containers")
        print(f"scenario: strategy={a.strategy} aggregation={a.aggregation} "
              f"beta={a.beta} profile={a.profile}")


if __name__ == "__main__":
    main()
