from __future__ import annotations

import argparse


def counts(n_honest, beta, byzantine_fraction=0.34):
    n_mal = round(n_honest * beta / (1.0 - beta)) if beta > 0 else 0
    n_byz = round(n_mal * byzantine_fraction)
    return n_byz, n_mal - n_byz


def generate(args):
    n_byz, n_syb = counts(args.n_honest, args.beta)
    total = args.n_honest + n_byz + n_syb
    env = {
        "ROLE": "controller", "N_HONEST": args.n_honest, "BETA": args.beta,
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
                  f"      CONTROLLER_URL: http://controller:{args.port}",
                  "    depends_on:", "      - controller"]
    return "\n".join(lines) + "\n", total, n_byz, n_syb


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n-honest", type=int, default=15)
    p.add_argument("--beta", type=float, default=0.3)
    p.add_argument("--rounds", type=int, default=50)
    p.add_argument("--warmup", type=int, default=10)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--peer-set-size", type=int, default=7)
    p.add_argument("--strategy", default="eclipse_resistant")
    p.add_argument("--aggregation", default="trimmed_mean")
    p.add_argument("--profile", default="coordinated")
    p.add_argument("--coordinated-value", type=float, default=1000.0)
    p.add_argument("--pow-bits", type=int, default=12)
    p.add_argument("--num-buckets", type=int, default=8)
    p.add_argument("--timeout-rounds", type=int, default=3)
    p.add_argument("--trim-alpha", type=float, default=0.2)
    p.add_argument("--flooding", type=int, default=0)
    p.add_argument("--churn-period", type=int, default=0)
    p.add_argument("--unresponsive-p", type=float, default=0.0)
    p.add_argument("--selective-p", type=float, default=1.0)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--out", default="docker/docker-compose.yml")
    a = p.parse_args()
    text, total, n_byz, n_syb = generate(a)
    with open(a.out, "w") as f:
        f.write(text)
    print(f"wrote {a.out}: {a.n_honest} honest + {n_byz} byzantine + {n_syb} sybil "
          f"= {total} node containers")
    print(f"scenario: strategy={a.strategy} aggregation={a.aggregation} "
          f"beta={a.beta} profile={a.profile}")


if __name__ == "__main__":
    main()
