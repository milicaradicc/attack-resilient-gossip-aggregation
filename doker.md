# Docker верзија — потпуно објашњење

> Писано према актуелном коду: `entrypoint.py`, `gen_compose.py`,
> `controller_service.py`, `matrix_service.py`, `node_service.py`.
>
> Циљ: да после овога можеш да објасниш сваки ред.

---

# 0. Шта чему служи — преглед пре детаља

```
gen_compose.py         piše docker-compose.yml, pokreće se PRE svega
entrypoint.py          bira ko je kontejner (16 linija)
controller_service.py  stanje JEDNE konfiguracije: svet, barijera, metrike
matrix_service.py      koordinator: drži 540 takvih stanja, HTTP server
node_service.py        život jednog čvora
```

Уочи одмах једну ствар: **`controller_service.py` више није сервис.** У њему
живи класа `ControllerState`, коју матрична служба користи. Име је остатак од
раније, кад је постојао режим за један сценарио.

---

# 1. Пре подизања: `gen_compose.py`

Покреће се **на твом рачунару**, не у контејнеру:

```powershell
python -m docker.gen_compose --matrix configs/main.json
```

## Колико контејнера

```python
specs = load_matrix(args.matrix)
total = max(s.n_honest + sum(s.malicious_counts()) for s in specs)
```

`load_matrix` разбија конфигурацију на појединачне задатке. За `main.json` то је
540 објеката типа `RunSpec`.

Затим се тражи **највећа** конфигурација. Зашто највећа: контејнери се подижу
**једном** и остају кроз све конфигурације. Значи мора их бити довољно за
најобимнију; у мањима ће вишак мировати.

За `main.json` то је 20 честитих + 9 нападача = **29 контејнера за чворове**.

## Шта се уписује

```python
env = {"ROLE": "controller", "MATRIX_CONFIG": args.matrix,
       "MATRIX_OUT": args.matrix_out, "PORT": args.port}
```

Координатор добија четири променљиве. Нема ниједног параметра експеримента —
они су у конфигурационом фајлу, који координатор сам чита.

```python
for i in range(total):
    lines += [f"  node{i}:",
              "    environment:", "      ROLE: node", f"      NODE_ID: \"{i}\"",
              f"      CONTROLLER_URL: http://controller:{args.port}"]
```

Чвор добија **две** ствари: свој редни број и адресу координатора. Ништа више.

`http://controller:8000` ради зато што Docker Compose прави мрежу у којој је
име сервиса уједно и име домаћина.

## Резултат

Фајл од неколико стотина редова, где се двадесет девет ставки разликује само у
једном броју.

---

# 2. Подизање: `entrypoint.py`

`Dockerfile` је пет редова:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
ENTRYPOINT ["python", "-m", "docker.entrypoint"]
```

**Сви контејнери добијају исту слику.** Не постоји посебна слика за координатора
и посебна за чвор.

```python
ROLE = os.environ.get("ROLE")

if ROLE == "controller":
    from docker.matrix_service import main
else:
    from docker.node_service import main

main()
```

Шеснаест редова који одлучују ко је ко. Приметићеш да се увоз дешава **унутар**
гране — контејнер за чвор никад ни не учита матричну службу.

---

# 3. Координатор се подиже

```python
def main():
    config_path = os.environ.get("MATRIX_CONFIG", "configs/smoke.json")
    config_name = os.path.splitext(os.path.basename(config_path))[0]
    out = os.environ.get("MATRIX_OUT", f"results/docker/{config_name}.csv")
    summary = out.replace(".csv", "_summary.csv")
    json_path = out.replace(".csv", ".json")
```

Излазне путање изводе се из имена конфигурације: `configs/main.json` даје
`results/docker/main.csv`, `main_summary.csv` и `main.json`.

```python
    matrix = MatrixState(config_path)
    server = serve(matrix, "0.0.0.0", port)
```

`0.0.0.0` значи „слушај на свим мрежним адресама". У контејнеру је то нужно —
`127.0.0.1` би био доступан само изнутра.

```python
    def watch():
        while not matrix.done():
            time.sleep(0.2)
        matrix.write(out, summary, json_path)

    threading.Thread(target=watch, daemon=True).start()
    server.serve_forever()
```

Две нити: главна служи HTTP захтеве заувек, посебна прати завршетак и на крају
уписује фајлове.

`daemon=True` значи да та нит не спречава гашење процеса.

---

# 4. `MatrixState` — шта држи координатор

```python
def __init__(self, config_path, verbose=True):
    self.specs = load_matrix(config_path)      # 540 zadataka
    self.states = {}                            # PRAZAN
    self.summaries = {}
    self.round_rows = {}
    self.node_rows = {}
    self.trace_rows = {}
    self.lock = threading.Lock()
    self.max_nodes = max(s.n_honest + sum(s.malicious_counts()) for s in self.specs)
    self.extra = varying_fields(self.specs)
    self.config_fields = CONFIG_FIELDS + self.extra
```

**`self.states` је празан.** Ниједан свет се не склапа при подизању.

`varying_fields` гледа који се параметри напада **мењају** кроз матрицу:

```python
def varying_fields(specs):
    return [k for k in SWEEPABLE if len({getattr(sp, k) for sp in specs}) > 1]
```

Ако аблација свипује `flooding`, он постаје додатна колона у излазу. Без тога
редови се не би могли разликовати — сви би имали исти опис конфигурације.

## Лењо стварање

```python
def state_for(self, job: int) -> ControllerState:
    with self.lock:
        st = self.states.get(job)
        if st is None:
            st = _spec_state(self.specs[job])
            self.states[job] = st
        return st
```

Први ко затражи посао, тај га и склопи. Остали затекну готово.

**Зашто под катанцем.** Двадесет девет чворова креће истовремено. Без катанца би
више њих видело `None` и направило више светова за исти посао — а сваки има своју
баријеру, па би чекали једни друге заувек.

**Зашто лењо.** 540 светова одједном значи 540 пута решавање proof-of-work за
све идентитете, а ради само један посао истовремено.

## Генератор случајности

```python
def _spec_state(spec):
    return ControllerState(
        spec, rng=make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation))
```

Ово је фина ствар. `ControllerState` подразумевано користи `make_rng(seed,
"attack")`, али се овде **преписује**.

Разлог: понуде кандидата троше случајност. Ако генератор није исти као онај који
користи тестна инфраструктура, редослед понуда се разилази и два начина
извршавања дају различите бројеве.

---

# 5. `ControllerState` — стање једне конфигурације

## Склапање света

```python
world = build_world(spec)
```

**Најважнији ред целе Docker верзије.** Иста функција коју зове и тестна
инфраструктура.

У њој се дешава све: чворови добијају вредности, гради се топологија, уписују
почетни дневници, деле се скупови, решава се proof-of-work за свих 29
идентитета, рачуна се циљна вредност.

## Разлагање чворова

```python
self.n = len(nodes)
self.assignments = {i: {"x_local": n.x_local, "peers": list(n.peers)}
                    for i, n in nodes.items()}
```

Координатор из правих `Node` објеката извуче **само оно што чвор треба да зна о
себи** — своју вредност и почетне суседе.

Праве објекте не задржава. Они ће живети у контејнерима.

## Бројеви учесника

```python
self.n_total = self.n + len(world.byzantine) + len(world.sybil)
```

`self.n` је 20 (само честити), `self.n_total` је 29 (сви).

**Та разлика је важна.** Баријера за вредности чека `n_total`, јер и нападачи
објављују. Баријера за извештаје чека `n`, јер нападачи не извештавају.

## Замене за метрике

```python
class _Stub:
    __slots__ = ("peers", "estimate")

self.stubs = {i: _Stub(a["peers"], a["x_local"]) for i, a in self.assignments.items()}
```

Метрике очекују објекте са пољима `peers` и `estimate`. Пошто правих чворова
нема, координатор држи лаке замене и пуни их из извештаја.

`__slots__` штеди меморију — има их двадесет по конфигурацији.

## Нулта рунда

```python
self.recorded = {0}
self.metrics.record(0, self.stubs, self.scenario, RoundCounters())
```

Почетно стање бележи се одмах, са празним бројачима. Без тога `complete()`
никад не би био тачан, јер тражи `num_rounds + 1` забележених рунди.

---

# 6. Чвор се подиже

```python
def main():
    base = os.environ["CONTROLLER_URL"]
    node_id = int(os.environ["NODE_ID"])
    run_matrix_node(base, node_id)
```

## HTTP помоћнице

```python
def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, ConnectionError, OSError):
        return 503, None
```

Две врсте грешака се различито третирају.

**`HTTPError`** значи да је сервер одговорио, али кодом грешке — рецимо 425, што
значи „прерано". Тај код нас занима.

**Остале** значе да сервер уопште није одговорио, можда се још подиже. Враћа се
503, што спољна петља тумачи као „покушај поново".

## Блокирајуће верзије — овде се чека

```python
def _block_get(url, poll=0.05):
    while True:
        status, body = _get(url)
        if status == 200:
            return body
        time.sleep(0.05)
```

**Ово је целокупан механизам чекања.** Чвор не пита „је ли време" — понавља
захтев док не добије потврдан одговор.

Педесет милисекунди између покушаја: довољно да не загуши координатора, довољно
кратко да се не губи време.

## Петља по пословима

```python
def run_matrix_node(base, node_id):
    info = _block_get(f"{base}/jobs")
    for job in range(info["n_jobs"]):
        cfg = _block_get(f"{base}/job/{job}")
        if node_id >= cfg["participants"]:
            continue
        if node_id in set(cfg["byzantine"]) | set(cfg["sybil"]):
            run_malicious(base, node_id, cfg, job)
        else:
            run_honest(base, node_id, cfg, job)
```

Први захтев враћа `{"n_jobs": 540, "max_nodes": 29}`.

`participants` је број учесника тог посла. При конфигурацији са десет честитих и
четири нападача, чворови 14 и навише **прескачу** — немају шта да раде.

**Улога се одређује по послу**, не при подизању. Исти контејнер може бити честит
у једној конфигурацији а нападачки у другој, јер број нападача зависи од β.

---

# 7. Чвор склапа своје алате

```python
def _build(cfg):
    params = IdentityParams(**cfg["id_params"])
    registry = IdentityRegistry()
    for k, v in cfg["registry"].items():
        registry.register(int(k), v)
    scenario = Scenario(set(cfg["honest"]), set(cfg["byzantine"]),
                        set(cfg["sybil"]), AttackParams(**cfg["attack"]))
    return params, registry, scenario
```

`**cfg["id_params"]` распакује речник у именоване аргументе. Отуда имена у
`config_payload` морају **тачно** одговарати пољима структуре — кад се додаје нов
параметар, мора на оба места.

`int(k)` јер JSON кључеве чува као текст.

Чвор добија **цео** регистар, не само за своје суседе. Мора моћи да провери
доказ било ког кандидата.

## Своје доделе

```python
apath = f"{base}/assignment/{job}/{node_id}"
_, assign = _get(apath)
node = Node.create(node_id, assign["x_local"])
node.peers = list(assign["peers"])
for p in node.peers:
    node.observations[p] = Observation(first_seen_round=0, last_seen_round=0)
```

Почетни дневници се праве **локално**, не преносе. Пошто су сви са временом
нула, довољно је знати ко су суседи.

---

# 8. Једна рунда — девет корака

## Корак 1: припрема

```python
scenario.before_round({node_id: node}, r)
```

Чвор ово ради **сам над собом** — прослеђује речник са једним чвором. Churn мења
само његов дневник, па нема шта да се координише.

**Нема мрежног позива.**

## Корак 2: пријава суседа

```python
_block_post(f"{base}/peers", _tag({"node_id": node_id, "round": r,
                                   "peers": node.peers}, job))
```

```python
def _tag(payload, job):
    payload["job"] = job
    return payload
```

Сваки захтев носи ознаку конфигурације, јер координатор држи 540 засебних стања.

Координатор само упише:

```python
with st.lock:
    st.peers_in.setdefault(data["round"], {})[data["node_id"]] = data["peers"]
self._send(200, {"ok": True})
```

**Одмах враћа 200.** Ту се не чека.

Катанац је нужан јер је сервер вишенитан — двадесет чворова може писати
истовремено.

## Корак 3: преузимање кандидата — ПРВА БАРИЈЕРА

```python
opath = f"{base}/offers/{job}/{node_id}/{r}"
offers = _block_get(opath)["offers"]
```

Координатор:

```python
with st.lock:
    st.maybe_build_offers(r)
    ready = (r, i) in st.offers
    offers = st.offers.get((r, i))
self._send(200 if ready else 425, {"offers": offers} if ready else {"ready": False})
```

А `maybe_build_offers` ништа не ради док сви не пријаве суседе:

```python
def maybe_build_offers(self, r):
    if r in self.offers_done or len(self.peers_in.get(r, {})) < self.n:
        return
    for i in range(self.n):
        view = _OfferView(i, self.peers_in[r][i])
        self.offers[(r, i)] = self.scenario.offer_candidates(view, r, self.rng)
    self.offers_done.add(r)
```

**Ту чвор стоји.** Добија 425, чека, пита поново.

### Зашто координатор прави понуде

Оне троше заједнички генератор случајности, и то у петљи **по редном броју
чвора**. Да их сваки чвор правио сам, редослед потрошње зависио би од тога који
је контејнер први стигао — а то није поновљиво.

### Шта је `_OfferView`

```python
class _OfferView:
    __slots__ = ("node_id", "peers")
```

`offer_candidates` очекује нешто са `node_id` и `peers`, а координатор нема праве
чворове. Ово је најмања ствар која задовољава тај облик.

## Корак 4: пријем — локално

```python
round_ops.request_peers(node, offers, r, transport=transport)
offered, rejected, reasons = round_ops.admit(node, strategy, r,
                                             trace=trace, transport=transport)
```

**Нема мрежног позива.** Чвор има стратегију, регистар и свој дневник — довољно
за одлуку.

`request_peers` претвара листу бројева у поруке: један захтев плус по једна
понуда за сваког кандидата. `admit` их онда вади из сандучета.

```python
transport = Transport()
```

Прави се **свеж сваке рунде**, па бројачи мере саобраћај те рунде а не збир од
почетка.

```python
trace = EventTrace() if cfg.get("trace_events") else None
```

Ако бележење није тражено, остаје `None` и функције преко њега прескачу.

## Корак 5: емитовање

```python
own = node.estimate
_block_post(f"{base}/broadcast", _tag(
    {"node_id": node_id, "round": r,
     "value": _sendable(scenario.broadcast_value(node_id, own, r))}, job))
```

`own` се узима **пре** објављивања. То је замрзавање: чвор ће касније агрегирати
над том вредношћу, не над оном коју у међувремену израчуна.

```python
def _sendable(value):
    return None if value is NO_MESSAGE else value
```

Ово решава напад задржавања. Кад је порука задржана, нападач нема шта да пошаље
— али **мора нешто**, иначе баријера застаје. Шаље празну вредност: броји се за
баријеру, суседима се не испоручује.

## Корак 6: преузимање вредности — ДРУГА БАРИЈЕРА

```python
vals = _block_post(f"{base}/values", _tag(
    {"node_id": node_id, "round": r, "peers": node.peers}, job))["values"]
```

Координатор:

```python
ready = len(st.broadcasts.get(r, {})) == st.n_total
b = st.broadcasts.get(r, {})
out = ({str(p): b[p] for p in data["peers"]
        if p in b and b[p] is not None} if ready else None)
```

**Три ствари у три реда:**

`n_total`, не `n` — чека се свих 29, укључујући нападаче.

`for p in data["peers"]` — чвор добија **искључиво** вредности идентитета које је
сам навео. Ту се види да заједнички пресек не нарушава локални поглед:
ограничење је у протоколу, не у дисциплини.

`b[p] is not None` — задржане поруке се прескачу.

`str(p)` јер JSON не подржава бројевне кључеве.

## Корак 7: провера доступности — локално

```python
responders, timeouts = round_ops.heartbeat(
    node, list(node.peers), scenario, r, None, timeout_rounds,
    trace=trace, transport=transport)
```

`list(node.peers)` је копија, јер функција мења ту листу при избацивању.

`None` уместо генератора — случајност напада изведена је из seed-а, не из
локалног генератора.

## Корак 8: испорука и агрегација — локално

```python
emitted = {int(k): v for k, v in vals.items()}
round_ops.deliver(node, responders, emitted, r, transport=transport)
incoming = transport.receive(node_id, messages.AGGREGATE)
received = [m.payload for m in incoming]
node.estimate = aggregation.aggregate(own, received)
```

Ово изгледа заобилазно и вреди објаснити.

Вредности **већ јесу** код чвора — стигле су HTTP-ом у `vals`. Могао би директно
да агрегира.

Али се провлаче кроз транспорт јер `deliver` прави **праве поруке** са
пошиљаоцем и одредиштем, које улазе у мерење саобраћаја. Да агрегира директно из
`vals`, порука не би било и бројеви о саобраћају не би постојали.

## Корак 9: извештај — ТРЕЋА БАРИЈЕРА

```python
_block_post(f"{base}/report", _tag({
    "node_id": node_id, "round": r, "peers": node.peers,
    "estimate": node.estimate, "offered": offered, "rejected": rejected,
    "data_msgs": transport.data, "control_msgs": transport.control,
    "rej_invalid_pow": reasons["invalid_pow"], ...,
    "timeouts": timeouts,
    "trace": trace.csv_rows() if trace is not None else None}, job))
```

Ова баријера није по чекању него по последици — чвор одмах добије 200 и иде у
следећу рунду. Али координатор не бележи док не стигну сви.

---

# 9. Нападачки чвор

```python
def run_malicious(base, node_id, cfg, job):
    _, _, scenario = _build(cfg)
    for r in range(1, cfg["num_rounds"] + 1):
        _block_post(f"{base}/broadcast", _tag(
            {"node_id": node_id, "round": r,
             "value": _sendable(scenario.broadcast_value(node_id, 0.0, r))}, job))
```

**Осам редова** наспрам шездесет код честитог.

Нема суседе, не прима кандидате, не агрегира, не извештава. Само објављује.

`0.0` је заглавље — нема сопствену процену, а функција тражи неки аргумент.
Игнорише га и врати лаж по профилу.

**Зашто уопште учествује:** координатор чека `n_total` објава. Да нападач не
шаље, честити би заувек стајали на кораку 6.

---

# 10. Бележење метрика

```python
def maybe_record(self, r):
    if r in self.recorded or len(self.reports.get(r, {})) < self.n:
        return
```

Чека се `self.n` (двадесет честитих), не `n_total` — нападачи не извештавају.

## Пуњење замена

```python
for i in range(self.n):
    self.stubs[i].peers = rep[i]["peers"]
    self.stubs[i].estimate = rep[i]["estimate"]
```

## Сабирање бројача

```python
agg = lambda key: sum(rep[i][key] for i in range(self.n))
counters = RoundCounters(data_msgs=agg("data_msgs"),
                         control_msgs=agg("control_msgs"), ...)
```

Сваки чвор шаље своје бројаче, координатор их сабира.

## Подела посла око догађаја

Ово је фино решено — неке догађаје зна само чвор, неке само координатор.

**Координатор бележи системске:**

```python
if r == self.scenario.params.activate_round:
    self.trace.attack_activated(r, len(self.scenario.malicious_ids))
cp = self.scenario.params.churn_period
if cp > 0 and r % cp == 0:
    self.trace.churn_reset(r, len(self.scenario.malicious_ids))
if self.scenario.active(r):
    sent = self.broadcasts.get(r, {})
    for m in sorted(self.scenario.malicious_ids):
        if m in sent and sent[m] is not None:
            self.trace.malicious_broadcast(r, m, sent[m], ...)
```

Да их бележи сваки чвор, активација напада појавила би се двадесет пута.

**Чворови шаљу своје:**

```python
for i in range(self.n):
    for row in (rep[i].get("trace") or []):
        self.trace.events.append(_row_to_event(row))
```

Редослед је по редном броју чвора. Извештаји стижу произвољним редоследом, али
се уписују уређено — што је нужно за детерминизам.

```python
def _row_to_event(row):
    from metrics.event_trace import TraceEvent
    return TraceEvent(row[0], row[1], row[2],
                      None if row[3] == "" else row[3],
                      row[4], None if row[5] == "" else row[5])
```

Чвор шаље догађаје као редове (јер JSON не зна за твоје класе), координатор их
враћа у објекте.

---

# 11. Завршетак посла

```python
def complete(self):
    return len(self.recorded) >= self.num_rounds + 1
```

`+1` због нулте рунде.

```python
elif parts[0] == "report":
    with st.lock:
        st.reports.setdefault(data["round"], {})[data["node_id"]] = data
        st.maybe_record(data["round"])
        finished = st.complete()
    if finished:
        matrix.finalize(job)
    self._send(200, {"ok": True})
```

Уочи распоред катанаца: `st.lock` се **отпушта** пре `matrix.finalize`, који
узима `matrix.lock`. То је намерно — узимање два катанца у обрнутом редоследу на
два места води у међусобно блокирање.

## Преузимање власништва

```python
def finalize(self, job):
    with self.lock:
        st = self.states.get(job)
        if st is None or not st.complete():
            return
        self.states[job] = None
```

**Ово решава стварну трку.** Двадесет чворова шаље последњи извештај готово
истовремено, и сваки види да је посао готов. Без заштите би се резултати
обрадили двадесет пута.

Постављањем на `None` **под катанцем**, само први пролази. Остали затекну `None`
и одустану.

Тиме се и ослобађа меморија: свет тог посла више није потребан.

## Извлачење резултата

```python
prefix = ([spec.n_honest, spec.beta, spec.overlay, spec.aggregation,
           spec.byzantine_profile, spec.seed]
          + [getattr(spec, k) for k in self.extra])
summary = summarize(spec, st.metrics)
self.summaries[job] = (prefix, summary)
self.round_rows[job] = (prefix, st.metrics.to_csv_rows())
```

`prefix` су прве колоне сваког реда — опис конфигурације. `self.extra` су
свиповани параметри.

---

# 12. Крај свега

```python
def done(self):
    return len(self.summaries) >= len(self.specs)
```

```python
def write(self, out_path, summary_path, json_path):
    ...
    for j in sorted(self.round_rows):
```

**`sorted` је важно.** Послови се завршавају произвољним редоследом, али редови
у фајлу морају бити уређени по броју посла — иначе се излаз не би поклопио са
оним из тестне инфраструктуре.

Настају фајлови:

```
results/docker/main.csv            po rundi
results/docker/main_summary.csv    po pokretanju
results/docker/main.json           oba u JSON obliku
results/docker/main_nodes.csv      po čvoru, ako je traženo
results/docker/main_trace.csv      događaji, ako je traženo
```

---

# 13. Три баријере — сажето

```
1. /offers    čeka  n        (svi honest prijave susede)
2. /values    čeka  n_total  (svi objave vrednost, i napadači)
3. /report    čeka  n        (svi honest izveste)
```

Између њих чвор ради **локално**, без мреже: pријем, провера доступности,
агрегација.

---

# 14. Шта координатор ради а шта чвор

| | координатор | чвор |
|---|---|---|
| склапање света | ✓ | |
| подела вредности и суседа | ✓ | |
| стварање понуда | ✓ | |
| одлука о пријему | | ✓ |
| емитовање вредности | | ✓ |
| провера доступности | | ✓ |
| агрегација | | ✓ |
| системски догађаји | ✓ | |
| догађаји о пријему | | ✓ |
| рачунање метрика | ✓ | |
| упис резултата | ✓ | |

**Све одлуке о понашању доноси чвор.** Координатор склапа почетно стање, држи
баријеру и мери — не учествује у алгоритму.

---

# 15. Ако те неко пита зашто координатор постоји

Он **није део система који се мери**. Његова улога је синхрона баријера, коју
спецификација прописује у 5.1.4, и прикупљање мерења.

Не зна шта је права вредност, не одлучује ко коме улази у комшилук, не учествује
у агрегацији. Да га уклониш, алгоритам би радио исто — само не би било гаранције
да су сви у истој рунди, па резултат не би био поновљив.

Аналогија: судија на такмичењу даје знак за старт и мери време. То не значи да
такмичари зависе од њега — он не трчи.