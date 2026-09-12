from __future__ import annotations

import argparse
import os

from core.config import load_defaults, load_matrix


def generate(args):
    # broj kontejnera odredjuje najveca konfiguracija u matrici; u manjima
    # cvorovi sa visim rednim brojem nemaju sta da rade i preskacu posao
    specs = load_matrix(args.matrix)
    total = max(s.n_honest + sum(s.malicious_counts()) for s in specs)

    env = {
        "ROLE": "controller",
        "MATRIX_CONFIG": args.matrix,
        "MATRIX_OUT": args.matrix_out,
        "PORT": args.port,
    }
    lines = ["services:", "  controller:",
             "    build:", "      context: ..", "      dockerfile: docker/Dockerfile",
             "    environment:"]
    for k, v in env.items():
        lines.append(f"      {k}: \"{v}\"")
    lines += ["    ports:", f"      - \"{args.port}:{args.port}\"",
              "    volumes:", "      - ../results:/app/results"]
    for i in range(total):
        lines += [f"  node{i}:",
                  "    build:", "      context: ..", "      dockerfile: docker/Dockerfile",
                  "    environment:", "      ROLE: node", f"      NODE_ID: \"{i}\"",
                  f"      CONTROLLER_URL: http://controller:{args.port}",
                  "    depends_on:", "      - controller"]
    return "\n".join(lines) + "\n", total, len(specs)


def main():
    d = load_defaults()
    p = argparse.ArgumentParser()
    p.add_argument("--matrix", required=True,
                   help="konfiguracija matrice, npr. configs/main.json")
    p.add_argument("--matrix-out", default=None,
                   help="izlazni CSV; podrazumevano results/docker/<naziv>.csv")
    p.add_argument("--port", type=int, default=d["docker_port"])
    p.add_argument("--out", default=d["docker_compose_out"])
    a = p.parse_args()
    if a.matrix_out is None:
        naziv = os.path.splitext(os.path.basename(a.matrix))[0]
        a.matrix_out = f"results/docker/{naziv}.csv"
    text, total, n_specs = generate(a)
    with open(a.out, "w") as f:
        f.write(text)
    print(f"wrote {a.out}: {n_specs} konfiguracija, {total} node containers")
    print(f"config: {a.matrix} -> {a.matrix_out}")


if __name__ == "__main__":
    main()