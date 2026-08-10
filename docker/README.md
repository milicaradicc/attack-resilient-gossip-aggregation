# Docker Compose deployment — pun sistem sa napadima

Jedan kontejner po cvoru + controller. Sada radi CEO sistem distribuirano:
honest cvorovi rade discovery, admission (PoW/age/score/bucket), eviction,
heartbeat i agregaciju; napadacki kontejneri emituju pokvarene vrednosti po
svom profilu. Controller drzi sinhronu barijeru, centralno generise ponudjene
kandidate (deljeni seed), i racuna sve metrike.

Dokazano (tests/test_distributed.py): distribuirani rezultat je bit-identican
in-process rezultatu i za benigni i za napadacki scenario, jer barijera cuva
sinhroni tick-barrier model.

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

## Napomena

Puna eksperimentalna matrica (540) se i dalje izvrsava in-process radi brzine i
reproduktivnosti; Docker daje identicne brojeve i sluzi kao dokaz da sistem
radi kao stvarno distribuiran.
