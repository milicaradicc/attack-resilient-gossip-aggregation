# Gossip Overlay — otporna distribuirana agregacija

Gossip overlay sistem za distribuiranu agregaciju koji zadrzava tacnost procene
u prisustvu kombinovanih napada na tri sloja: identitet (Sybil), strukturu veza
(Eclipse, peer poisoning, flooding, churn) i same vrednosti (Byzantine).

Svaki cvor poseduje lokalnu vrednost i ogranicen peer set. Kroz gossip razmene
sa komsijama svi honest cvorovi treba da procene globalnu srednju vrednost
`x* = mean(x_i)`. Cilj sistema je da za udeo zlonamernih `beta <= 0.30` odrzi
relativnu gresku `err_rel <= 0.05` uz ogranicenu Sybil penetraciju i stabilnu
overlay strukturu.

---

## 1. Arhitektura

Sistem je organizovan kao **biblioteka + dva pokretaca**. Biblioteka sadrzi svu
logiku i ne zna nista o tome kako se pokrece. Iznad nje stoje dva nezavisna
pokretaca koji istu logiku izvrsavaju na dva nacina.

```
              BIBLIOTEKA (logika sistema)
   core, identity, sampling, aggregation, attacks, metrics
                         |
          +--------------+--------------+
          |                             |
    experiments/                    docker/
   (in-process, brzo)        (kontejner po cvoru, distribuirano)
```

Nijedan pokretac ne sadrzi logiku — oni je samo hrane podacima. In-process je
hrani iz memorije, distribuirani preko HTTP-a. Zato oba daju **bit-identicne**
rezultate, sto je pokriveno testovima koji porede obe putanje.

### Slojevi biblioteke

| Sloj | Odgovornost |
|---|---|
| `core/` | model i motor: cvor, overlay topologija, deterministicki rng, sklapanje sveta, motor runde, zajednicka per-cvor logika |
| `identity/` | sloj identiteta: proof-of-work, bucket mapiranje, identity scoring, observation log |
| `sampling/` | tri zamenljive peer sampling strategije iza istog interfejsa |
| `aggregation/` | tri zamenljive agregacione funkcije |
| `attacks/` | katalog napada kao parametrizovani profili |
| `metrics/` | merenje: greska, penetracija, diversity, overhead, razlozi odbijanja |

Zavisnosti idu strogo u jednom smeru — `core` ne zna ni za koga, a napadi i
metrike sede iznad. Strategije i agregacije su iza protokola, pa se menjaju bez
diranja ostatka sistema. To je ono sto omogucava eksperiment: menja se jedna
komponenta, sve ostalo ostaje isto.

### Jedna gossip runda

1. **churn** — ako je aktivan, resetuje starost napadackih identiteta
2. **discovery + admission** — scenario nudi kandidate, strategija odlucuje ko
   ulazi u peer set (PoW / starost / skor / bucket) i koga izbacuje
3. **broadcast** — snimak svih emitovanih vrednosti (honest prave, napadaci lazne)
4. **heartbeat** — ko ne odgovara skuplja propustene otkucaje i posle
   `timeout_rounds` biva izbacen
5. **agregacija** — nova procena iz sopstvene vrednosti i vrednosti onih koji su
   odgovorili
6. **metrike** — belezenje stanja runde

Vrednosti se zamrznu na pocetku runde i tek onda citaju, pa rezultat ne zavisi
od redosleda obrade (sinhroni tick-barrier model).

### Deljena per-cvor logika

`core/round_ops.py` sadrzi korake runde koji se izvrsavaju nad jednim cvorom
(`observe`, `admit`, `heartbeat`). Funkcije primaju vec pribavljene podatke, pa
ih `core/engine.py` poziva sa podacima iz memorije a `docker/node_service.py` sa
podacima iz mreze. Admission i heartbeat pravila zato postoje samo na jednom
mestu i ne mogu da se raziju izmedju dve putanje.

### Deterministicka reproduktivnost

Sva slucajnost se izvodi iz jednog eksperimentalnog seed-a formulom
`seed = SHA256(exp_seed || component_name)`, sa zasebnim generatorom po
podsistemu (pocetne vrednosti, topologija, peer selection, Byzantine vrednosti,
heartbeat). Nigde se ne koristi globalni generator, niti ugradjeni `hash()` (koji je
nasumican po procesu), pa je isti trace zagarantovan i izmedju pokretanja. Isti eksperiment uvek daje
identican trag — i in-process i u kontejnerima.

---

## 2. Pokretanje

Jezgro nema zavisnosti (Python 3.10+). Analiza koristi matplotlib.

```bash
pip install -r requirements.txt
```

### Eksperimenti in-process (brzo, ~2 min za 540)

```bash
# puna matrica: 3 (N) x 4 (beta) x 3 (overlay) x 3 (agregacija) x 5 (seed) = 540
python -m experiments.matrix --config configs/main.json

# ablacije: sweep Byzantine profila (36 pokretanja)
python -m experiments.matrix --config configs/ablation.json

# dopunski overlay napadi (flooding, churn, selective forwarding)
python -m experiments.matrix --config configs/flooding.json
python -m experiments.matrix --config configs/churn.json
python -m experiments.matrix --config configs/selective.json

# tabele i grafikoni
python -m analysis.report --beta 0.3                  # iz Docker rezultata
python -m analysis.report --source inprocess --beta 0.3   # iz in-process rezultata
```

Izlaz: `results/*.csv` (per-round + run-level summary), `results/*.json`,
`results/<izvor>/tables.md` (14 tabela) i `figures/*.png` (12 grafikona).

### Eksperimenti u Docker okruzenju

```bash
# SVE KONFIGURACIJE redom, pa izvestaj iz Docker rezultata.
# Prvo pokretanje trazi --build; kasnija ga ne trebaju ako se kod nije menjao.
# Trajanje: main je 1-3 sata, ostale po nekoliko minuta.
for cfg in main ablation eclipse flooding churn selective delay; do
    python -m docker.gen_compose --matrix configs/$cfg.json
    docker compose -f docker/docker-compose.yml up --build
    docker compose -f docker/docker-compose.yml down --remove-orphans
done
python -m analysis.report --beta 0.3

# PUNA MATRICA u kontejnerima (broj kontejnera = max cvorova preko svih konfiguracija)
python -m docker.gen_compose --matrix configs/main.json
docker compose -f docker/docker-compose.yml up --build

# JEDAN SCENARIO (demonstracija distribuiranosti)
python -m docker.gen_compose --n-honest 15 --beta 0.3 \
    --strategy eclipse_resistant --aggregation trimmed_mean
docker compose -f docker/docker-compose.yml up --build

# zaustavljanje
docker compose -f docker/docker-compose.yml down
```

Ista stvar u PowerShell-u (Windows):

```powershell
foreach ($cfg in "main","ablation","eclipse","flooding","churn","selective","delay") {
    python -m docker.gen_compose --matrix "configs/$cfg.json"
    docker compose -f docker/docker-compose.yml up --build
    docker compose -f docker/docker-compose.yml down --remove-orphans
}
python -m analysis.report --beta 0.3
```

Controller ispisuje napredak po konfiguraciji i na kraju upisuje rezultate u
`results/docker/<ime_configa>.csv` (+ `_summary.csv` i `.json`), u istom obliku
kao in-process putanja koja pise u `results/inprocess/`.

### Testovi

```bash
python -m pytest tests/ -v
```

20 test fajlova (137 testova), ukljucujuci dva koja porede distribuiranu i in-process putanju.

---

## 3. Konfiguracija

Svi parametri sistema su u **jednom** fajlu: `configs/defaults.json`. Pojedinacni
configi navode samo ono sto menjaju i nasledjuju ostalo; ono sto je izricito
navedeno u configu pobedjuje default. Isti izvor koristi i in-process matrica i
generator Docker okruzenja, pa ne postoje dve istine o parametrima.

```
configs/defaults.json   svi parametri (mreza, identitet, agregacija, napad, evaluacija)
configs/main.json       glavna matrica (540)
configs/ablation.json   sweep Byzantine profila (45)
configs/smoke.json      brza provera (36)
configs/tiny.json       minimalna provera (8, koristi je test)
configs/eclipse.json    ciljani Eclipse napad (27 pokretanja)
configs/flooding.json   sweep intenziteta flooding napada (36)
configs/churn.json      sweep churn perioda (36)
configs/selective.json  sweep selective forwarding i unresponsive (81)
configs/delay.json      sweep kasnjenja poruka (72)
```

Glavni parametri: `n_honest {10,15,20}`, `beta {0, 0.1, 0.2, 0.3}`,
`peer_set_size 7`, `num_rounds 50`, `warmup 10`, `conv_window_start 20`,
`seeds [1..5]`, `trim_alpha 0.2`, `pow_difficulty_bits 12`, `num_buckets 8`,
`max_per_bucket 2`, `timeout_rounds 3`.

---

## 4. Slojevi napada i odbrane

**Agregacione funkcije:** `mean`, `median`, `trimmed_mean` (parametrizovan
trimming faktor; `alpha = 0.2` odbacuje po jednu ekstremnu vrednost sa svake
strane pri `K = 7`).

**Peer sampling strategije:**

| Strategija | Admission | Eviction |
|---|---|---|
| `random` | prima svakog (baseline bez zastite) | prvi iz peer set-a |
| `sybil_resistant` | validan PoW + minimalna starost + skor iznad praga | najnizi skor |
| `eclipse_resistant` | isto + bucket ogranicenje | najslabiji iz istog bucketa; kad je bucket pun, kandidat sa visim skorom zamenjuje slabijeg (4.5.3) |

**Napadi:** Sybil (masovni identiteti), Eclipse (izolacija cvora; parametar
`eclipse_targets` prebacuje napad iz "sirokog" u ciljani, gde napadac sve
identitete koncentrise na N zrtava), peer
poisoning (guranje napadackih identiteta u discovery), flooding (neregistrovani
kandidati koji opterecuju admission), churn (periodicno resetovanje starosti),
selective forwarding / unresponsive (cutanje), i Byzantine profili vrednosti:
`coordinated` (glavni), `extreme`, `random`, `low_biased`, `stale`.

Control i data saobracaj su razdvojeni na nivou poruka (`core/messages.py`):
svaka poruka nosi tip, rundu, izvor, odrediste i payload. Agregaciona vrednost
putuje kao zasebna poruka od suseda ka cvoru; vrednosti se pritom zamrzavaju na
pocetku runde, pa isporuka ne zavisi od redosleda obrade (tick barrier). pa se overhead zastite meri
odvojeno od gossip razmene. Control: peer exchange, admission, peer reject,
heartbeat. Data: agregacione vrednosti.

**Metrike:** `err_rel`, `spread`, Sybil penetration, Eclipse rate, peer
diversity (Shannon), bucket occupancy, control/data overhead, rejected ratio sa
razlozima (`invalid_pow` / `too_young` / `low_score` / `bucket_full`), timeouts.
Run-level: vreme konvergencije, stabilnost procene u konvergencijskom prozoru.

---

## 5. Struktura projekta

```
core/         node, overlay, rng, setup, engine, round_ops, config, messages
identity/     pow, buckets, scoring, observation, registry
aggregation/  base, mean, median, trimmed_mean
sampling/     base, random_strategy, sybil_resistant, eclipse_resistant
attacks/      base (zajednicki interfejs) + moduli: byzantine, poisoning,
              eclipse, flooding, churn, delay, selective; scenario ih koordinira
metrics/      experiment_metrics (per-round, per-node, run-level), event_trace (5.1.8)
experiments/  matrix (pokretanje eksperimentalne matrice)
docker/       controller_service, node_service, matrix_service,
              entrypoint, gen_compose, Dockerfile
analysis/     loader, report (tabele + grafikoni)
configs/      defaults + main / ablation / smoke / tiny
results/      docker/ i inprocess/ — isti oblik izlaza za obe putanje (generisano)
figures/      PNG (generisano)
tests/        20 test fajlova + helpers (pomocni pokretaci)
```

---

## 6. Ogranicenja

Overlay topologija je regularna i bucket-svesna: svaki cvor ima tacno K suseda,
cime gossip usrednjavanje konvergira tacno ka aritmetickoj sredini, a pocetni
peer set-ovi postuju `max_per_bucket` vec u prvoj rundi. Za neke kombinacije
(N=10, K=7, 8 bucketa) potpuno postovanje nije moguce: bucket sa tri clana
zahteva sedam iskljucenja, a kapacitet je sest, pa jedan cvor zadrzava
prekoracenje.
k-regularan graf postoji samo kada je N*K paran broj, pa pri N=15 i K=7 jedan
cvor nuzno ima K-1 suseda i preostaje odstupanje reda 1e-2.

Model je sinhron (tick-barrier), bez asinhrone mreze i realnog rutiranja.
Bucket diverzifikacija je eksperimentalna aproksimacija realne IP/ASN
raznovrsnosti. Delay i selective forwarding su modelovani na sloju vrednosti, ne
na mreznom sloju. Partitioning napad nije implementiran jer zahteva viseskocno
rutiranje koje sinhroni single-hop model nema. Zapis dogadjaja (5.1.8) ukljucuje se sa `trace_events` i daje `*_trace.csv`:
admission odluke sa razlogom, promene peer set-a (izbacivanja i zamene),
napadacke aktivnosti (aktivacija, emitovane vrednosti po profilu, churn reset,
broj flooding kandidata) i agregacione vrednosti po rundi. Metrike po cvoru (4.9) daju
`*_nodes.csv`. Oba zapisa nad punom matricom rastu brzo, pa se mogu iskljuciti.
`refresh_peers` je no-op (discovery se izvrsava svake runde u motoru), a
`choose_gossip_target` postoji radi poklapanja sa specifikacijom ali motor
koristi `select_gossip_peers` (fanout = |P|), jer robusna agregacija zahteva
skup vrednosti.