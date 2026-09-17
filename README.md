# Gossip Overlay - otporna distribuirana agregacija

Gossip overlay sistem za distribuiranu agregaciju koji zadržava tačnost procene u prisustvu kombinovanih napada na tri sloja: identitet (Sybil), strukturu veza (Eclipse, peer poisoning, flooding, churn) i same vrednosti (Byzantine).

Svaki čvor poseduje lokalnu vrednost i ograničen peer set. Kroz gossip razmene sa komšijama svi honest čvorovi treba da procene globalnu srednju vrednost $x^* = \text{mean}(x_i)$. Cilj sistema je da za udeo zlonamernih $\beta \le 0.30$ održi relativnu grešku $\text{err\_rel} \le 0.05$ uz ograničenu Sybil penetraciju i stabilnu overlay strukturu.

## Brzi početak

### Preduslovi

* Python 3.10 ili noviji

* Docker i Docker Compose (za distribuirano izvršavanje)

### Instalacija

```
git clone <adresa-repozitorijuma>
cd attack-resilient-gossip-aggregation
pip install -r requirements.txt
```

> \[!NOTE\]
> Jezgro sistema nema spoljnih zavisnosti. `matplotlib` se koristi samo pri iscrtavanju grafikona, a `pytest` pri pokretanju testova.

### Provera ispravnosti

Brza provera rada sistema (traje nekoliko sekundi):

```
python -m pytest tests/ -q
```

### Najmanji eksperiment

Pokretanje minimalnog eksperimenta bez kontejnera:

```
python -m in_process.matrix --config configs/smoke.json
python -m analysis.report --source inprocess --beta 0.3
```

Rezultati se upisuju u `results/inprocess/`, tabele u `results/inprocess/tables.md`, a grafikoni u `figures/`.

## 2. Pokretanje i eksperimenti

### In-process eksperimenti (brzo, \~2 min za 540 scenarija)

```
# Puna matrica: 3 (N) x 4 (beta) x 3 (overlay) x 3 (agregacija) x 5 (seed) = 540
python -m in_process.matrix --config configs/main.json

# Dopunski eksperimenti
python -m in_process.matrix --config configs/ablation.json    # Byzantine profili
python -m in_process.matrix --config configs/eclipse.json    # Eclipse pri višem udelu
python -m in_process.matrix --config configs/flooding.json   # Peer flooding
python -m in_process.matrix --config configs/churn.json      # Churn
python -m in_process.matrix --config configs/selective.json  # Selective forwarding
python -m in_process.matrix --config configs/delay.json      # Kašnjenje poruka
python -m in_process.matrix --config configs/admission.json  # Mehanizmi pristupa

# Generisanje tabela i grafikona
python -m analysis.report --beta 0.3                     # Iz Docker rezultata
python -m analysis.report --source inprocess --beta 0.3  # Iz in-process rezultata
```

Izlazi obuhvataju: `results/*.csv` (per-round i run-level summary), `results/*.json`, `results/<izvor>/tables.md` (14 tabela) i `figures/*.png` (12 grafikona).

### Eksperimenti u Docker okruženju

#### Automatsko pokretanje svih konfiguracija (Bash / Linux / macOS)

```
for cfg in main ablation eclipse flooding churn selective delay admission; do
    python -m docker.gen_compose --matrix configs/$cfg.json
    docker compose -f docker/docker-compose.yml up --build
    docker compose -f docker/docker-compose.yml down --remove-orphans
done
python -m analysis.report --beta 0.3
```

#### PowerShell (Windows)

```
foreach ($cfg in "main","ablation","eclipse","flooding","churn","selective","delay","admission") {
    python -m docker.gen_compose --matrix "configs/$cfg.json"
    docker compose -f docker/docker-compose.yml up --build
    docker compose -f docker/docker-compose.yml down --remove-orphans
}
python -m analysis.report --beta 0.3
```

> \[!TIP\]
> Prvo pokretanje zahteva `--build`; kasnija pokretanja ga ne trebaju ukoliko kod nije menjan. Trajanje `main` matrice je 1–3 sata, dok ostale traju po nekoliko minuta.

### Testovi

Pokretanje kompletnog test suita (21 test fajl, 158 testova):

```
python -m pytest tests/ -v
```

Testovi potvrđuju da distribuirana i in-process putanja daju identične rezultate.

## 3. Konfiguracija

Svi parametri sistema nalaze se u **jednom** centralnom fajlu: `configs/defaults.json`. Pojedinačni konfiguracioni fajlovi definišu samo izmene u odnosu na podrazumevane vrednosti.

| Konfiguracioni fajl | Opis | 
 | ----- | ----- | 
| `configs/defaults.json` | Svi parametri (mreža, identitet, agregacija, napad, evaluacija) | 
| `configs/main.json` | Glavna eksperimentalna matrica (540) | 
| `configs/ablation.json` | Sweep Byzantine profila (45) | 
| `configs/smoke.json` | Brza provera (36) | 
| `configs/tiny.json` | Minimalna provera (8, koristi se u testovima) | 
| `configs/flooding.json` | Sweep intenziteta flooding napada (36) | 
| `configs/churn.json` | Sweep dužine odsustva pri churn napadu (45) | 
| `configs/selective.json` | Sweep selective forwarding i unresponsive (81) | 
| `configs/delay.json` | Sweep kašnjenja poruka (72) | 
| `configs/admission.json` | `age_min x score_threshold`, doprinos mehanizama pristupa (36) | 

**Glavni parametri:** $n_{\text{honest}} \in \{10, 15, 20\}$, $\beta \in \{0, 0.1, 0.2, 0.3\}$, `peer_set_size = 7`, `num_rounds = 50`, `warmup = 10`, `conv_window_start = 20`, `seeds = [1..5]`, `trim_alpha = 0.2`, `pow_difficulty_bits = 12`, `num_buckets = 8`, `max_per_bucket = 2`, `timeout_rounds = 3`.

## 4. Struktura projekta

```
core/         node, overlay, rng, setup, engine, round_ops, config, messages
identity/     pow, buckets, scoring, observation, registry
aggregation/  base, mean, median, trimmed_mean
sampling/     base, random_strategy, sybil_resistant, eclipse_resistant
attacks/      base (zajednički interfejs) + moduli: byzantine, poisoning,
              eclipse, flooding, churn, delay, selective; scenario ih koordinira
metrics/      experiment_metrics (per-round, per-node, run-level), event_trace
in_process/   matrix (pokretanje eksperimentalne matrice)
docker/       controller_service, node_service, matrix_service,
              entrypoint, gen_compose, Dockerfile
analysis/     loader, report (tabele + grafikoni)
configs/      defaults + main / ablation / smoke / tiny
results/      docker/ i inprocess/ — isti oblik izlaza za obe putanje
figures/      PNG (generisano)
tests/        20 test fajlova + helpers
```

## Licenca

Projekat je licenciran pod MIT licencom. Pun tekst se nalazi u fajlu [LICENSE](LICENSE).

## Autor

**Milica Radić**, Fakultet tehničkih nauka, Novi Sad.
