# Docker Compose deployment — pun sistem sa napadima

Jedan kontejner po cvoru + controller. Sada radi CEO sistem distribuirano:
honest cvorovi rade discovery, admission (PoW/age/score/bucket), eviction,
heartbeat i agregaciju; napadacki kontejneri emituju pokvarene vrednosti po
svom profilu. Controller drzi sinhronu barijeru, centralno generise ponudjene
kandidate (deljeni seed), i racuna sve metrike.

Dokazano (tests/test_distributed.py): distribuirani rezultat je bit-identican
in-process rezultatu i za benigni i za napadacki scenario, jer barijera cuva
sinhroni tick-barrier model.

## Dva rezima

1. JEDAN SCENARIO (demonstracija): jedan kontejner po cvoru, jedna konfiguracija.
2. MATRICA (puna evaluacija): controller unutar kontejnera prolazi kroz SVE
   konfiguracije iz configa i izvozi kompletan summary CSV/JSON. Cvorovi ostaju
   podignuti kroz sve konfiguracije; u svakoj ucestvuju samo oni koji su
   potrebni (ostali miruju), jer se broj cvorova menja po konfiguraciji.

## Pokretanje

```bash
# generisi compose za zeljeni scenario (honest + napadacki kontejneri)
python -m docker.gen_compose --n-honest 15 --beta 0.3 \
    --strategy eclipse_resistant --aggregation trimmed_mean --profile coordinated

docker compose -f docker/docker-compose.yml up --build
```

Broj kontejnera = n_honest + (byzantine + sybil izvedeni iz beta). Controller u
logu ispisuje napredak po rundi (err, sybil penetracija, timeouts) i na kraju
upisuje results/distributed.csv.

### Matrica u kontejnerima

```bash
python -m docker.gen_compose --matrix configs/main.json     # 540 konfiguracija
docker compose -f docker/docker-compose.yml up --build
```

Broj kontejnera = najveci broj cvorova preko svih konfiguracija. Controller
ispisuje napredak po konfiguraciji i na kraju upisuje
results/distributed_matrix_summary.csv (+ .json), plus dump u log.
Dokazano (tests/test_distributed_matrix.py): rezultati matrice iz kontejnera su
bit-identicni in-process matrici.

## Parametri (gen_compose)

--strategy random|sybil_resistant|eclipse_resistant
--aggregation mean|median|trimmed_mean
--profile coordinated|extreme|random|low_biased|stale
--beta udeo zlonamernih | --warmup benigne runde pre napada
--flooding N | --churn-period N | --unresponsive-p p | --selective-p p

## Protokol runde (mirror Engine-a)

1. honest cvor prijavi peer set; controller centralno generise ponudjene
   kandidate (scenario.offer_candidates, deljeni rng) -> barijera
2. cvor lokalno primeni admission/eviction (svoja strategija)
3. svi (honest + napadaci) emituju vrednost -> barijera
4. cvor povuce vrednosti peer-ova, primeni heartbeat/timeout, agregira
5. cvor prijavi novo stanje; controller zabelezi metrike runde
