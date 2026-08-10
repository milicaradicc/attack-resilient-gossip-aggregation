# Gossip Overlay — attack-resilient distributed aggregation

Deterministički gossip overlay sistem za distribuiranu agregaciju otporan na
kombinovane Sybil, Eclipse i Byzantine napade. Razvija se in-process (jedan
Python proces); Docker Compose je transport swap za stvarnu distribuciju.

## Pokretanje

Jezgro nema zavisnosti (Python 3.10+). Analiza koristi matplotlib.

```bash
pip install -r requirements.txt

# eksperimenti -> per-round CSV + run-level summary CSV
python -m experiments.matrix --config configs/main.json     --out results/main.csv       # 540 (CSV + JSON)
python -m experiments.matrix --config configs/ablation.json --out results/ablation.csv   # profili

# tabele i grafikoni za poglavlje 7
python -m analysis.report --beta 0.3

# demonstracije slojeva (benigno + napad, tabelarno)
python -m experiments.run

# NARATIVNI DEMO (za odbranu): korak-po-korak tok sistema + poredjenje sa/bez odbrane
python -m experiments.demo

# distribuirano (Docker): jedan kontejner po cvoru + controller
python -m docker.gen_compose --n-honest 15 --beta 0.3 --strategy eclipse_resistant --aggregation trimmed_mean
docker compose -f docker/docker-compose.yml up --build

python -m pytest tests/ -v
```

## Struktura

```
core/        rng, node, overlay
identity/    pow, buckets, scoring, observation, registry
aggregation/ mean, median, trimmed_mean
sampling/    random, sybil_resistant, eclipse_resistant
attacks/     scenario (napadi kao parametrizovani profili)
metrics/     experiment_metrics (per-round + run-level summary + CSV)
experiments/ setup, scenarios, engine, config, matrix, run, demo
analysis/    loader, report (tabele + grafikoni)
docker/      controller_service, node_service, Dockerfile, gen_compose, compose
configs/     main.json (540), ablation.json, smoke.json
results/     CSV + tables.md (generisano)   figures/  PNG (generisano)
tests/       11 test fajlova
```

## Slojevi napada i odbrane

- agregacija: mean / median / trimmed_mean
- peer sampling: random (baseline) / sybil_resistant (PoW+age+score) /
  eclipse_resistant (+bucket diverzifikacija)
- napadi: Sybil, Eclipse, peer poisoning, Byzantine profili
  (coordinated/extreme/random/low_biased/stale), flooding, churn, selective
- heartbeat/timeout: cutljivi peer-ovi (churn/unresponsive napad) se izbacuju posle
  timeout_rounds propustenih odgovora (aktivira se pod unresponsive_p>0)
- metrike: err_rel, spread, Sybil penetration, Eclipse rate, peer diversity,
  convergence time, stability, control/data overhead, rejected ratio (+razlozi),
  timeouts,
  bucket occupancy. Izvoz: CSV i JSON (results/*.json).

## Ključni rezultat (beta=0.3)

Odbrana (sybil/eclipse) + trimmed_mean(alpha=0.2) drži err=0.029 < 0.05 za sve
beta<=0.30 (ispunjava kriterijum 3.10). random baseline kolabira (~9) -> odbrana
je neophodna. median je robustan ali ima ~6% floor (alternativa, manje precizan).

## Docker

Ceo sistem (napadi + odbrana) radi distribuirano; rezultat je identičan
in-process rezultatu jer mrežna barijera čuva sinhroni tick-barrier model
(dokazano u tests/test_distributed.py, i benigno i pod napadom).

## Ograničenja (poglavlje 8)

Sinhroni single-hop pull model; delay/selective su value-layer aproksimacije;
partitioning i pravi network-layer forwarding napadi su van opsega; bucket
diverzifikacija emulira ASN/IP raznovrsnost.
