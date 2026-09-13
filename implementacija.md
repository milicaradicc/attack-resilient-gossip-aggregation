# Поглавље 5 — Имплементација

> Нацрт за прераду. Исечци кода су скраћени на оно што носи значење; у раду их
> вреди још скратити или пренети у прилог.
>
> Места означена са **[провери]** описана су по сећању на актуелно стање кода —
> упореди са својим фајловима пре уношења.

---

## 5.1. Технолошки избори и структура пројекта

Систем је реализован у програмском језику Python, верзија 3.11. Језгро система
не користи ниједну спољну библиотеку — сви механизми, укључујући хеширање,
мрежну комуникацију и рад са форматима записа, ослањају се на стандардну
библиотеку.

Разлог за такав избор је двострук. Прво, систем се покреће унутар контејнера,
где свака додатна зависност повећава величину слике и време градње. Друго,
одсуство зависности уклања могућност да резултати зависе од верзије неке
библиотеке, што би угрозило репродуктивност.

Једина спољна библиотека, `matplotlib`, користи се искључиво при исцртавању
графикона и не учествује у извршавању експеримената.

### 5.1.1. Организација пакета

Изворни код подељен је у пакете који одговарају слојевима описаним у поглављу 4:

```
core/          čvor, topologija, tok runde, poruke, transport, konfiguracija
identity/      proof-of-work, dnevnik, skor, bucket raspodela, registar
sampling/      tri strategije izbora suseda
aggregation/   tri agregacione funkcije
attacks/       moduli napada i scenario koji ih koordinira
metrics/       merenje po rundi i po čvoru, zapis događaja
docker/        distribuirano izvršavanje
in_process/    izvršavanje u jednom procesu
analysis/      učitavanje rezultata, tabele i grafikoni
configs/       opisi eksperimenata
tests/         automatizovani testovi
```

Подела почива на једном правилу: пакети који описују модел не смеју знати како
ће бити покренути. Због тога `core`, `identity`, `sampling`, `aggregation`,
`attacks` и `metrics` не увозе ништа из `docker` нити из `in_process`, док оба
покретача увозе исте модуле модела.

### 5.1.2. Два начина извршавања

Систем се може покренути на два начина.

**Дистрибуирано извршавање** подиже један контејнер по учеснику, уз засебан
контејнер за координацију. То је основни начин рада и предмет највећег дела овог
поглавља.

**Извршавање у једном процесу** покреће исту матрицу конфигурација без подизања
контејнера. Служи двема сврхама: брзом добијању резултата током развоја, будући
да пуна матрица од 540 конфигурација траје неколико минута уместо неколико
сати, и као референца при провери исправности дистрибуиране путање.

Оба начина ослањају се на исте модуле модела, па поређење њихових резултата не
представља поређење две имплементације него проверу да ли се нека од путања
разишла. Тај поступак описан је у одељку 5.9.

---

## 5.2. Језгро

### 5.2.1. Представљање чвора

Чвор је реализован као структура података без сопственог понашања:

```python
@dataclass
class Node:
    node_id: int
    x_local: float
    estimate: float = field(default=0.0)
    peers: List[int] = field(default_factory=list)
    observations: Dict[int, Observation] = field(default_factory=dict)

    @classmethod
    def create(cls, node_id: int, x_local: float) -> "Node":
        return cls(node_id=node_id, x_local=x_local, estimate=x_local)
```

Фабричка метода поставља почетну процену на измерену вредност, чиме чвор креће
од онога што сам види.

Чвор не поседује методе које извршавају кораке рунде. Разлог је постојање два
начина извршавања: када би петља припадала чвору, иста логика морала би
постојати у два примерка. Уместо тога, кораке над чвором извршавају функције
описане у одељку 5.2.6.

Две ствари које спецификација наводи међу стањем чвора намерно се чувају другде.
**Доказ о утрошеном рачунарском ресурсу** налази се у заједничком регистру, јер
представља јаван податак који сваки чвор мора моћи да провери за било који
идентитет. **Метрике** се прикупљају у слоју мерења, како прикупљање не би
утицало на понашање система.

### 5.2.2. Извођење случајности

Сви извори случајности изводе се из једне вредности, експерименталног seed-а:

```python
def make_rng(seed: int, *labels: str) -> random.Random:
    material = "|".join(labels).encode() + seed.to_bytes(8, "big")
    digest = hashlib.sha256(material).digest()
    return random.Random(int.from_bytes(digest, "big"))
```

За сваки подсистем изводи се засебан генератор:

```python
val_rng = make_rng(seed, "initial_metrics")
top_rng = make_rng(seed, "overlay_topology")
```

Одвојени генератори уведени су како промена у једном делу система не би померила
понашање осталих. Када би сви подсистеми делили један генератор, промена броја
чворова померила би и распоред почетних вредности и структуру топологије и
понашање напада, чиме поређење две конфигурације не би имало смисла.

Уграђена функција `hash()` намерно се не користи. За текстуалне вредности она је
насумично засољена по процесу, што значи да исти улаз даје различит резултат при
сваком покретању интерпретера. Током развоја је управо тај механизам изазвао
ситуацију у којој исти експеримент даје различите резултате у три узастопна
покретања.

### 5.2.3. Градња топологије

Почетна топологија мора истовремено задовољити три услова: сваки чвор има једнак
број суседа, граф је повезан, и peer set-ови поштују ограничење разноврсности.
Гради се у три фазе. **[провери]**

**Кружна основа.** Полази се од детерминистичког распореда у коме сваки чвор има
тачно `k` суседа:

```python
half = k // 2
for i in range(n):
    for d in range(1, half + 1):
        j = (i + d) % n
        adj[i].add(j)
        adj[j].add(i)
```

Сваки чвор повезује се са `half` суседа лево и десно. При непарном `k` фали још
један, па се при парном `n` свако повезује са наспрамним чвором:

```python
if k % 2 == 1 and n % 2 == 0:
    for i in range(n // 2):
        j = i + n // 2
        adj[i].add(j)
        adj[j].add(i)
```

Када су и `n` и `k` непарни, регуларан граф не постоји, будући да збир степена
свих чворова мора бити паран. Тада један чвор нужно остаје са `k−1` суседа.

**Мешање.** Кружна основа је детерминистичка, па се меша заменама парова веза
које не мењају степене:

```python
(a, b) = rng.choice(edges)
(c, d) = rng.choice(edges)
adj[a].discard(b); adj[b].discard(a)
adj[c].discard(d); adj[d].discard(c)
adj[a].add(c); adj[c].add(a)
adj[b].add(d); adj[d].add(b)
```

Чвор `a` губи суседа `b` а добија `c` — број суседа му остаје исти. Исто важи за
сва четири чвора. Поступак се понавља неколико стотина пута.

**Поправка разноврсности.** Након мешања проверава се да ли неки чвор има више
суседа из истог bucket-а него што ограничење допушта, па се таква прекорачења
уклањају циљаним заменама истог облика. Поступак стаје када прекорачења нестану
или када престане да доноси напредак, будући да за поједине комбинације броја
чворова и величине peer set-а потпуно поштовање ограничења није остварљиво.

### 5.2.4. Постављање света

Функција `build_world` спаја све слојеве у почетно стање и представља једино
место на коме се то дешава:

```python
def build_world(spec) -> World:
    cfg = RunConfig(n_honest=spec.n_honest, peer_set_size=spec.peer_set_size, ...)
    nodes = build_nodes(cfg)
    seed_observations(nodes)

    honest = set(nodes.keys())
    n_byzantine, n_sybil = spec.malicious_counts()
    b0 = spec.n_honest
    byzantine = set(range(b0, b0 + n_byzantine))
    sybil = set(range(b0 + n_byzantine, b0 + n_byzantine + n_sybil))

    registry = register_all(honest | byzantine | sybil, id_params)
    x_star = mean(n.x_local for n in nodes.values())

    if n_byzantine + n_sybil == 0:
        scenario = Scenario.benign(honest)
    else:
        scenario = Scenario(honest, byzantine, sybil, AttackParams(...))

    return World(cfg, nodes, honest, byzantine, sybil, registry,
                 id_params, scenario, x_star)
```

Скупови учесника формирају се као дисјунктни опсези по конструкцији: сваки
почиње тамо где претходни престаје.

Број злонамерних учесника изводи се из задатог удела у укупној мрежи:

```python
def malicious_counts(n_honest, beta, byzantine_fraction):
    if beta <= 0.0:
        return 0, 0
    n_mal = round(n_honest * beta / (1.0 - beta))
    n_byzantine = round(n_mal * byzantine_fraction)
    return n_byzantine, n_mal - n_byzantine
```

Израз `β/(1−β)` произлази из решавања дефиниције `β = n_mal / (n_honest + n_mal)`
по непознатом броју злонамерних, будући да је познат само број честитих чворова.

Почетни дневници стварају се пре прве рунде:

```python
for node in nodes.values():
    for peer in node.peers:
        node.observations[peer] = Observation(first_seen_round=0, last_seen_round=0)
```

Без тога би почетни суседи изгледали као потпуно нови идентитети, па би их
механизам контроле пријема одбио већ у првој рунди.

Циљна вредност рачуна се искључиво над честитим чворовима, чиме злонамерни
учесници не улазе у дефиницију онога што систем треба да достигне.

### 5.2.5. Поруке и транспорт

Свака размена представљена је поруком:

```python
@dataclass(frozen=True)
class Message:
    kind: str        # control ili data
    type: str
    round: int
    source: int
    target: int = None
    payload: object = None
```

Постоји шест типова, подељених у две класе:

| Тип | Класа | Настаје |
|---|---|---|
| `peer_exchange` | контролна | при предлагању кандидата |
| `admission` | контролна | при прихватању кандидата |
| `peer_reject` | контролна | при одбијању, са разлогом у садржају |
| `peer_evict` | контролна | при уклањању суседа |
| `heartbeat` | контролна | при провери доступности |
| `aggregate` | агрегациона | при преносу вредности |

Транспортни слој одржава сандуче по учеснику:

```python
class Transport:
    def __init__(self):
        self._mailboxes = defaultdict(list)
        self._by_kind = {CONTROL: 0, DATA: 0}
        self._by_type = defaultdict(int)

    def send(self, message):
        if message.target is not None:
            self._mailboxes[message.target].append(message)
        self._by_kind[message.kind] += 1
        self._by_type[message.type] += 1

    def receive(self, node_id, msg_type=None):
        mailbox = self._mailboxes.get(node_id)
        if not mailbox:
            return []
        if msg_type is None:
            self._mailboxes[node_id] = []
            return mailbox
        taken = [m for m in mailbox if m.type == msg_type]
        self._mailboxes[node_id] = [m for m in mailbox if m.type != msg_type]
        return taken
```

Преузимање по типу омогућава да свака фаза рунде узме само своје поруке, док
остале остају за наредну.

Радње протокола изложене су као именоване методе, чиме се из позива чита шта се
шаље:

```python
    def offer(self, round_now, candidate, to_node):
        self.send(messages.control(messages.PEER_EXCHANGE, round_now,
                                   candidate, target=to_node))

    def reject(self, round_now, node_id, candidate, reason):
        self.send(messages.control(messages.PEER_REJECT, round_now,
                                   node_id, target=candidate, payload=reason))
```

Порука о предлагању кандидата има као извор **сам кандидат**, а не чвор који
предлаже. Тиме је моделована саморекламација идентитета, што не захтева да
злонамерни учесници поседују сопствени peer set.

Поруке које прималац не преузме и даље улазе у бројање. Пример су одбијенице
упућене нападачким идентитетима, који своје сандуче не празне. У стварном
систему такве поруке јесу послате и јесу оптеретиле мрежу, па је њихово бројање
исправно.

### 5.2.6. Заједничке операције рунде

Модул `round_ops` садржи операције које се извршавају над појединачним чвором, а
користе их оба начина извршавања.

**Уписивање у дневник** разликује виђање кандидата од стварне размене:

```python
def observe(node, other, round_now, exchanged):
    obs = node.observations.get(other)
    if obs is None:
        node.observations[other] = Observation(
            first_seen_round=round_now, last_seen_round=round_now,
            successful_exchanges=1 if exchanged else 0)
    else:
        obs.last_seen_round = round_now
        if exchanged:
            obs.successful_exchanges += 1
            obs.missed_heartbeats = 0
```

Први случај покреће бројање старости; други увећава број успешних размена и
поништава бројач узастопних изостанака.

**Контрола пријема** обрађује понуђене кандидате:

```python
def admit(node, offered, sampling, round_now, trace=None, transport=None):
    reasons = empty_reasons()
    for candidate in offered:
        if transport is not None:
            transport.offer(round_now, candidate, node.node_id)
        observe(node, candidate, round_now, exchanged=False)
        if candidate in node.peers:
            continue
        if sampling.accept_peer(node, candidate, round_now):
            victim = sampling.evict_peer(node, round_now, candidate)
            if victim is not None:
                node.peers.remove(victim)
                if transport is not None:
                    transport.evict(round_now, node.node_id, victim, "replaced_by")
            elif len(node.peers) >= sampling.max_peers:
                continue
            node.peers.append(candidate)
            if transport is not None:
                transport.accept(round_now, node.node_id, candidate)
        else:
            why = sampling.reason(node, candidate, round_now) or "self_or_duplicate"
            reasons[why] = reasons.get(why, 0) + 1
            if transport is not None:
                transport.reject(round_now, node.node_id, candidate, why)
    return len(offered), sum(reasons.values()), reasons
```

Уочава се да функција не доноси ниједну одлуку — она води ток, а правила даје
стратегија кроз три позива: `accept_peer`, `evict_peer` и `reason`.

Кандидат се бележи у дневник **пре** провере, чиме му старост почиње да тече и
када буде одбијен. То је основа механизма одлагања пријема.

**Провера доступности** уклања суседе који не одговарају:

```python
def heartbeat(node, peers, scenario, round_now, rng, timeout_rounds,
              trace=None, transport=None):
    responders = []
    for p in peers:
        if transport is not None:
            transport.probe(round_now, node.node_id, p)
        if scenario.responds(p, round_now, rng):
            observe(node, p, round_now, exchanged=True)
            responders.append(p)
        else:
            obs = node.observations.get(p)
            if obs is not None:
                obs.missed_heartbeats += 1
                obs.missed_total += 1
    timeouts = 0
    if timeout_rounds > 0:
        for p in list(node.peers):
            obs = node.observations.get(p)
            if obs is not None and obs.missed_heartbeats > timeout_rounds:
                node.peers.remove(p)
                obs.timeout_count += 1
                timeouts += 1
                if transport is not None:
                    transport.evict(round_now, node.node_id, p, "timeout")
                if p in responders:
                    responders.remove(p)
    return responders, timeouts
```

Два бројача имају различиту сврху. `missed_heartbeats` броји **узастопне**
изостанке и поништава се чим се сусед јави; из њега се одлучује о уклањању.
`missed_total` броји укупно кроз цео живот идентитета и не поништава се; из њега
се рачуна умањење оцене.

Последњи услов у петљи уклањања спречава да избачени сусед учествује у
агрегацији те рунде, чак и ако је раније у истој петљи одговорио.

**Утврђивање вредности** склапа пресек стања свих учесника:

```python
def emitted_values(nodes, scenario, round_now, trace=None):
    out = {}
    for hid, node in nodes.items():
        out[hid] = scenario.broadcast_value(hid, node.estimate, round_now)
    for m in sorted(scenario.malicious_ids):
        value = scenario.broadcast_value(m, 0.0, round_now)
        if value is NO_MESSAGE:
            continue
        out[m] = value
    return out
```

Сортирање злонамерних идентитета обезбеђује исти редослед при сваком покретању,
будући да скупови у Python-у немају уређење.

Вредност `NO_MESSAGE` означава учесника који у тој рунди не емитује ништа, што
настаје при нападу задржавања порука.

**Испорука** ствара поруке од суседа који су одговорили:

```python
def deliver(node, responders, emitted, round_now, transport=None):
    senders = [p for p in responders if p in emitted]
    if transport is not None:
        for p in senders:
            transport.send_value(round_now, p, node.node_id, emitted[p])
    return senders
```

Услов `p in emitted` искључује лажне идентитете уведене нападом преплављивања,
који немају емитовану вредност.

---

## 5.3. Слој идентитета

### 5.3.1. Proof-of-work

Доказ се састоји од вредности која, заједно са ознаком идентитета, даје хеш са
задатим бројем водећих нула:

```python
def solve_pow(identity: str, difficulty_bits: int) -> int:
    nonce = 0
    while not check_pow(identity, nonce, difficulty_bits):
        nonce += 1
    return nonce


def check_pow(identity: str, nonce: int, difficulty_bits: int) -> bool:
    digest = hashlib.sha256(f"{identity}:{nonce}".encode()).digest()
    value = int.from_bytes(digest, "big")
    return value >> (256 - difficulty_bits) == 0
```

Провера померањем бита проверава да ли првих `difficulty_bits` бита износи нулу,
што одговара очекиваном броју покушаја од `2^difficulty_bits`.

Пошто се доказ везује за саму ознаку идентитета, не може се пренети на други
идентитет нити поново употребити.

### 5.3.2. Дневник посматрања

```python
@dataclass
class Observation:
    first_seen_round: int
    last_seen_round: int
    successful_exchanges: int = 0
    missed_heartbeats: int = 0
    missed_total: int = 0
    timeout_count: int = 0
```

Дневник је локалан за сваки чвор. Исти идентитет може имати различиту старост
код различитих чворова, зависно од тога када га је који први пут видео.
Последица је да пријем код једног чвора не олакшава пријем код осталих:
злонамеран идентитет мора да сазрева код сваког чвора понаособ.

### 5.3.3. Оцена идентитета

```python
def identity_score(round_now, first_seen_round, successful_exchanges,
                   pow_valid, age_max, exchange_max, missed_total=0):
    s_age = score_age(round_now, first_seen_round, age_max)
    s_exchange = score_exchange(successful_exchanges, exchange_max)
    s_pow = 1.0 if pow_valid else 0.0
    base = (s_age + s_exchange + s_pow) / 3.0
    return base * score_reliability(missed_total, exchange_max)
```

Три компоненте улазе равноправно, а резултат се умањује сразмерно броју
изостанака:

```python
def score_reliability(missed_total, exchange_max):
    return max(0.0, 1.0 - missed_total / exchange_max) if exchange_max else 1.0
```

Механизам ствара зависност која отежава напад: подизање оцене захтева успешне
размене, а оне захтевају претходни улазак у peer set.

### 5.3.4. Расподела по bucket-има

```python
def bucket_of(identity: str, num_buckets: int) -> int:
    digest = hashlib.sha256(identity.encode()).digest()
    return int.from_bytes(digest, "big") % num_buckets
```

Припадност се не чува нити додељује — рачуна се када затреба. Пошто произлази из
хеша саме ознаке, идентитет свој bucket не бира нити може да га промени.

### 5.3.5. Регистар

```python
class IdentityRegistry:
    def __init__(self):
        self.nonces: Dict[int, int] = {}

    def register(self, identity: int, nonce: int) -> None:
        self.nonces[identity] = nonce

    def valid(self, identity: int, difficulty_bits: int) -> bool:
        nonce = self.nonces.get(identity)
        return nonce is not None and check_pow(str(identity), nonce, difficulty_bits)
```

Регистар представља јаван именик. У дистрибуираном режиму преноси се сваком
чвору у целости, будући да сваки мора моћи да провери било који идентитет, а не
само своје суседе.

---

## 5.4. Стратегије избора суседа

Све стратегије задовољавају исти интерфејс:

```python
class SamplingStrategy:
    def accept_peer(self, node, candidate, round_now) -> bool: ...
    def evict_peer(self, node, round_now, candidate) -> Optional[int]: ...
    def reason(self, node, candidate, round_now) -> Optional[str]: ...
```

Метода `reason` не утиче на понашање система, али омогућава да се свако одбијање
припише тачно једном механизму.

### 5.4.1. Референтна стратегија

```python
class RandomStrategy(SamplingStrategy):
    def accept_peer(self, node, candidate, round_now):
        return candidate != node.node_id and candidate not in node.peers

    def evict_peer(self, node, round_now, candidate):
        if len(node.peers) < self.max_peers:
            return None
        return node.peers[0]
```

Уклања првог у листи, без икаквог критеријума.

### 5.4.2. Sybil-отпорна стратегија

```python
    def reason(self, node, candidate, round_now):
        if candidate == node.node_id or candidate in node.peers:
            return None
        if not self.registry.valid(candidate, self.params.pow_difficulty_bits):
            return "invalid_pow"
        obs = node.observations.get(candidate)
        age = round_now - obs.first_seen_round if obs else 0
        if age < self.params.age_min:
            return "too_young"
        if self.score(node, candidate, round_now) < self.params.score_threshold:
            return "low_score"
        return None
```

Услови се проверавају редом, а кандидат бива одбијен на првом који не задовољи.
Редослед прати цену провере: доказ се проверава једним хеширањем, старост
читањем дневника, а оцена рачунањем над више вредности.

```python
    def evict_peer(self, node, round_now, candidate):
        if len(node.peers) < self.max_peers:
            return None
        return min(node.peers, key=lambda p: self.score(node, p, round_now))
```

Уклања се сусед са најнижом оценом, чиме нов кандидат улази само ако је бољи од
најслабијег постојећег.

### 5.4.3. Eclipse-отпорна стратегија

Наслеђује претходну и додаје проверу разноврсности:

```python
    def reason(self, node, candidate, round_now):
        base = super().reason(node, candidate, round_now)
        if base is not None:
            return base
        target = self.bucket(candidate)
        members = self._bucket_peers(node, target)
        if len(members) < self.params.max_per_bucket:
            return None
        weakest = min(members, key=lambda p: self.score(node, p, round_now))
        if self.score(node, candidate, round_now) > self.score(node, weakest, round_now):
            return None
        return "bucket_full"
```

Уклањање се такође мења: уместо најслабијег суседа у целом peer set-у, уклања се
најслабији из истог bucket-а као кандидат. Место се тиме ослобађа тамо где је
кандидату потребно.

---

## 5.5. Агрегационе функције

Све функције деле исти облик:

```python
class AggregationStrategy:
    def aggregate(self, own: float, received: List[float]) -> float: ...
```

```python
class Mean(AggregationStrategy):
    def aggregate(self, own, received):
        values = [own, *received]
        return sum(values) / len(values)


class Median(AggregationStrategy):
    def aggregate(self, own, received):
        return median([own, *received])


class TrimmedMean(AggregationStrategy):
    def __init__(self, alpha: float = 0.2):
        self.alpha = alpha

    def aggregate(self, own, received):
        values = sorted([own, *received])
        n = len(values)
        k = int(n * self.alpha)
        kept = values[k:n - k] or values
        return sum(kept) / len(kept)
```

Сопствена вредност улази у прорачун равноправно и може бити одбачена као
одступање, будући да представља резултат претходне рунде а не непосредно мерење.

Израз `or values` штити од случаја у коме би одсецање уклонило све вредности,
што се дешава при малом броју примљених вредности.

---

## 5.6. Модули напада

### 5.6.1. Заједнички интерфејс

```python
class BaseAttack:
    name = "base"

    def enabled(self, ctx) -> bool:
        return True

    def before_round(self, ctx, nodes, round_now) -> None:
        return None

    def offer_candidates(self, ctx, node, round_now, rng, offers) -> List[int]:
        return offers

    def broadcast_value(self, ctx, identity, value, round_now) -> Optional[float]:
        return None

    def responds(self, ctx, identity, round_now) -> Optional[bool]:
        return None
```

Подразумевана понашања враћају `None`, што значи да се модул не меша у ту фазу.
Сценарио пита модуле редом и узима први одговор различит од `None`:

```python
def broadcast_value(self, identity, honest_value, round_now):
    if not self.active(round_now) or identity not in self.malicious_ids:
        return honest_value
    ctx = self.ctx
    for module in self.active_modules():
        value = module.broadcast_value(ctx, identity, honest_value, round_now)
        if value is not None:
            return value
    return honest_value
```

### 5.6.2. Откривање и убацивање кандидата

Предлагање кандидата ради непрекидно, и када напада нема:

```python
def offer_candidates(self, node, round_now, rng):
    ctx = self.ctx
    offers = self._discovery(node, rng)
    if not self.active(round_now):
        return offers
    for module in self.active_modules():
        offers = module.offer_candidates(ctx, node, round_now, rng, offers)
    rng.shuffle(offers)
    return offers
```

Мешање на крају уведено је зато што сваки пријем истискује једног постојећег
суседа, па кандидат примљен последњи остаје у peer set-у. Без мешања би редослед
у понуди давао систематску предност идентитетима који се додају касније.

**Peer poisoning** се надовезује на редовне предлоге:

```python
class PeerPoisoningAttack(BaseAttack):
    def offer_candidates(self, ctx, node, round_now, rng, offers):
        malicious = [m for m in sorted(ctx.malicious_ids) if m not in node.peers]
        return offers + malicious
```

**Eclipse** не уводи нове идентитете него сужава понуду изабраним жртвама:

```python
class EclipseAttack(BaseAttack):
    def enabled(self, ctx):
        return ctx.params.eclipse_targets > 0

    def offer_candidates(self, ctx, node, round_now, rng, offers):
        if node.node_id not in ctx.targets():
            return offers
        return [o for o in offers if o in ctx.malicious_ids]
```

Жртви се уклањају честити кандидати, чиме њен peer set може бити попуњен
искључиво нападачким идентитетима, док остали чворови остају под ширим нападом.

### 5.6.3. Манипулација вредностима

```python
class ByzantineAttack(BaseAttack):
    def broadcast_value(self, ctx, identity, value, round_now):
        if identity not in ctx.malicious_ids:
            return None
        p = ctx.params
        prof = p.byzantine_profile
        if prof == "extreme":
            return p.x_star + p.extreme_offset
        if prof == "random":
            r = module_rng(ctx, identity, round_now, "byzantine")
            return r.uniform(p.random_low, p.random_high)
        if prof == "low_biased":
            return p.x_star + p.low_bias
        return p.coordinated_value
```

Функција `module_rng` изводи генератор из експерименталног seed-а, идентитета и
редног броја рунде:

```python
def module_rng(ctx, identity, round_now, label):
    return make_rng(ctx.params.experiment_seed, label, str(identity), str(round_now))
```

Тиме понашање напада остаје поновљиво, а истовремено различито за сваког
нападача и сваку рунду.

### 5.6.4. Задржавање порука

```python
class DelayAttack(BaseAttack):
    def __init__(self):
        self.queue: Dict[int, Dict[int, float]] = {}
        self._profil = ByzantineAttack()

    def broadcast_value(self, ctx, identity, value, round_now):
        if ctx.params.delay_rounds <= 0 or identity not in ctx.malicious_ids:
            return None
        due = self.queue.get(round_now, {})
        held = due.pop(identity, None)
        if not due:
            self.queue.pop(round_now, None)
        delivery = round_now + ctx.params.delay_rounds
        sada = self._profil.broadcast_value(ctx, identity, value, round_now)
        self.queue.setdefault(delivery, {})[identity] = sada
        return held if held is not None else NO_MESSAGE
```

Модул задржава вредност коју би нападач послао и испоручује је после задатог
броја рунди. Док је порука задржана, учесник не емитује ништа.

Пошто модул чува стање, сценарио прави нове примерке модула при сваком
стварању, чиме се редови порука не преносе између експеримената:

```python
def default_modules() -> tuple:
    return (ChurnAttack(), PeerPoisoningAttack(), EclipseAttack(),
            PeerFloodingAttack(), DelayAttack(),
            SelectiveForwardingAttack(), ByzantineAttack())
```

Редослед модула је фиксан ради детерминизма.

---

## 5.7. Мерење

### 5.7.1. Три нивоа

Мерење се бележи на три нивоа детаља.

**По покретању** — један ред који сажима цео експеримент: финална грешка, време
конвергенције, време опоравка, стабилност, overhead, пенетрација и структура
одбијања.

**По рунди** — један ред за сваку рунду, из ког настају графикони промене кроз
време.

**По чвору** — један ред за сваки чвор у свакој рунди, из ког се види који је
чвор изолован и када. Укључује се параметром, будући да при пуној матрици ствара
неколико стотина хиљада редова.

### 5.7.2. Раздвајање саобраћаја

```python
def control_overhead(self, n_honest):
    vals = [r.control_msgs for r in self.rows if r.round >= 1]
    return mean(vals) / n_honest if vals else 0.0
```

Просек по рунди подељен бројем чворова даје исту вредност као израз
`control_messages / (N · T)` из спецификације.

### 5.7.3. Време опоравка

Дефиниција времена конвергенције из спецификације бележи прву рунду у којој
грешка падне испод прага. У окружењу са warmup фазом та дефиниција бележи и
пролазно задовољење услова, па систем који се касније поквари изгледа као да је
конвергирао.

Уведена је допунска мера:

```python
def recovery_time(self, epsilon, since=1):
    rows = [r for r in self.rows if r.round >= since]
    if not rows or rows[-1].err_rel >= epsilon:
        return -1
    recovered = rows[-1].round
    for row in reversed(rows):
        if row.err_rel >= epsilon:
            break
        recovered = row.round
    return recovered
```

Мера тражи прву рунду од које грешка **трајно** остаје испод прага, чиме
разликује систем који се стварно опоравио од оног који је накратко био тачан.

### 5.7.4. Запис догађаја

```python
class EventTrace:
    def accept(self, round_now, node_id, peer): ...
    def reject(self, round_now, node_id, peer, reason): ...
    def evict(self, round_now, node_id, peer, reason, replaced_by): ...
    def attack_activated(self, round_now, count): ...
    def malicious_broadcast(self, round_now, node_id, value, profile): ...
```

Запис омогућава праћење појединачних одлука, што је коришћено при провери
исправности и при анализи структуре одбијања.

---

## 5.8. Дистрибуирано извршавање

### 5.8.1. Слика и улоге

Сви контејнери подижу се из исте слике:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
ENTRYPOINT ["python", "-m", "docker.entrypoint"]
```

Улога се одређује променљивом окружења:

```python
ROLE = os.environ.get("ROLE")

if ROLE == "controller":
    from docker.matrix_service import main
else:
    from docker.node_service import main

main()
```

Тиме постоје две улоге: један контејнер који координира извршавање и по један
контејнер за сваког учесника.

### 5.8.2. Генерисање описа окружења

Опис контејнера не пише се ручно него се изводи из конфигурације:

```python
def generate(args):
    specs = load_matrix(args.matrix)
    total = max(s.n_honest + sum(s.malicious_counts()) for s in specs)

    env = {"ROLE": "controller", "MATRIX_CONFIG": args.matrix,
           "MATRIX_OUT": args.matrix_out, "PORT": args.port}
    lines = ["services:", "  controller:", ...]
    for i in range(total):
        lines += [f"  node{i}:", ...,
                  "    environment:", "      ROLE: node", f"      NODE_ID: \"{i}\"",
                  f"      CONTROLLER_URL: http://controller:{args.port}"]
    return "\n".join(lines) + "\n", total, len(specs)
```

Број контејнера одређује **највећа** конфигурација у матрици, будући да се
контејнери не подижу изнова за сваку конфигурацију. У мањим конфигурацијама
чворови са вишим редним бројем не учествују.

Сваки контејнер за чвор разликује се од осталих у једној вредности — свом редном
броју.

### 5.8.3. Стање једне конфигурације

Класа `ControllerState` представља стање једног експеримента. Свет се склапа
истом функцијом као у једнопроцесном режиму:

```python
class ControllerState:
    def __init__(self, spec, verbose=False, rng=None):
        world = build_world(spec)
        self.n = len(world.nodes)
        self.assignments = {i: {"x_local": n.x_local, "peers": list(n.peers)}
                            for i, n in world.nodes.items()}
        self.n_total = self.n + len(world.byzantine) + len(world.sybil)
        self.registry = world.registry
        self.x_star = world.x_star
        self.scenario = world.scenario
        self.rng = rng if rng is not None else make_rng(spec.seed, "attack")

        self.peers_in = {}
        self.offers = {}
        self.broadcasts = {}
        self.reports = {}
        self.recorded = {0}
        self.stubs = {i: _Stub(a["peers"], a["x_local"])
                      for i, a in self.assignments.items()}
        self.metrics = ExperimentMetrics(x_star=self.x_star, ...)
        self.metrics.record(0, self.stubs, self.scenario, RoundCounters())
        self.lock = threading.Lock()
```

Праве објекте чворова координатор не задржава — из њих извлачи само оно што
сваки чвор треба да зна о себи. Прави чворови настају у контејнерима.

За мерење су потребни објекти са пољима `peers` и `estimate`, па координатор
држи лаке замене:

```python
class _Stub:
    __slots__ = ("peers", "estimate")
```

Оне се пуне из извештаја које чворови шаљу на крају сваке рунде.

### 5.8.4. Преношење конфигурације

Чвор при подизању добија све потребно једним захтевом:

```python
def config_payload(self):
    return {
        "num_rounds": self.num_rounds, "n_honest": self.n,
        "strategy": self.strategy_name, "aggregation": self.aggregation_name,
        "peer_set_size": self.cfg.peer_set_size,
        "honest": sorted(self.honest), "byzantine": sorted(self.byzantine),
        "sybil": sorted(self.sybil), "x_star": self.x_star,
        "registry": {str(k): v for k, v in self.registry.nonces.items()},
        "id_params": {...},
        "attack": {...},
    }
```

Регистар се преноси у целости, будући да сваки чвор мора моћи да провери доказ
било ког идентитета.

Чвор из тога склапа своје алате:

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

Претварање кључева у целе бројеве нужно је јер формат записа кључеве чува као
текст.

### 5.8.5. Механизам баријере

Синхрони модел остварен је тако што координатор одбија да одговори док услов
није испуњен:

```python
self._send(200 if ready else 425, {"offers": offers} if ready else {"ready": False})
```

Чвор понавља захтев док не добије потврдан одговор:

```python
def _block_get(url, poll=0.05):
    while True:
        status, body = _get(url)
        if status == 200:
            return body
        time.sleep(poll)
```

Постоје три баријере по рунди.

**Прва** одлаже предлагање кандидата док сви чворови не пријаве састав својих
peer set-ова:

```python
def maybe_build_offers(self, r):
    if r in self.offers_done or len(self.peers_in.get(r, {})) < self.n:
        return
    for i in range(self.n):
        view = _OfferView(i, self.peers_in[r][i])
        self.offers[(r, i)] = self.scenario.offer_candidates(view, r, self.rng)
    self.offers_done.add(r)
```

Кандидати се стварају **централно**, у петљи по редном броју чвора. Разлог је
потрошња случајности: када би их сваки чвор стварао сам, редослед би зависио од
тога који је контејнер први стигао до тог корака.

**Друга** одлаже преузимање вредности док сви учесници не објаве своје:

```python
ready = len(st.broadcasts.get(r, {})) == st.n_total
b = st.broadcasts.get(r, {})
out = ({str(p): b[p] for p in data["peers"]
        if p in b and b[p] is not None} if ready else None)
```

Чека се `n_total`, што укључује и злонамерне учеснике. Чвор притом добија
искључиво вредности идентитета које је сам навео, чиме је ограничење локалног
погледа остварено самим протоколом а не договором.

**Трећа** одлаже бележење метрика док сви честити чворови не пошаљу извештај:

```python
def maybe_record(self, r):
    if r in self.recorded or len(self.reports.get(r, {})) < self.n:
        return
```

### 5.8.6. Ток рунде на чвору

```python
for r in range(1, cfg["num_rounds"] + 1):
    scenario.before_round({node_id: node}, r)
    _block_post(f"{base}/peers", _tag({"node_id": node_id, "round": r,
                                       "peers": node.peers}, job))
    offers = _block_get(f"{base}/offers/{job}/{node_id}/{r}")["offers"]

    trace = EventTrace() if cfg.get("trace_events") else None
    transport = Transport()
    offered, rejected, reasons = round_ops.admit(node, offers, strategy, r,
                                                 trace=trace, transport=transport)

    own = node.estimate
    _block_post(f"{base}/broadcast", _tag(
        {"node_id": node_id, "round": r,
         "value": _sendable(scenario.broadcast_value(node_id, own, r))}, job))
    vals = _block_post(f"{base}/values", _tag(
        {"node_id": node_id, "round": r, "peers": node.peers}, job))["values"]

    responders, timeouts = round_ops.heartbeat(
        node, list(node.peers), scenario, r, None, timeout_rounds,
        trace=trace, transport=transport)

    emitted = {int(k): v for k, v in vals.items()}
    round_ops.deliver(node, responders, emitted, r, transport=transport)
    incoming = transport.receive(node_id, messages.AGGREGATE)
    received = [m.payload for m in incoming]
    node.estimate = aggregation.aggregate(own, received)

    _block_post(f"{base}/report", _tag({...}, job))
```

Уочава се да чвор позива **исте функције** као једнопроцесни режим:
`round_ops.admit`, `round_ops.heartbeat` и `round_ops.deliver`. Разлика је
искључиво у томе одакле подаци долазе.

Сопствена вредност узима се пре објављивања, чиме је остварено замрзавање
описано у одељку 4.2.

Вредности које чвор прима већ су доступне у одговору координатора, али се ипак
провлаче кроз транспортни слој. Разлог је што тек тада настају поруке са
уписаним пошиљаоцем и одредиштем, које улазе у мерење саобраћаја.

Задржана порука шаље се као празна вредност:

```python
def _sendable(value):
    return None if value is NO_MESSAGE else value
```

Учесник мора нешто да пошаље, иначе баријера не би била испуњена. Празна
вредност се броји за баријеру, али се не испоручује суседима.

### 5.8.7. Злонамеран учесник

```python
def run_malicious(base, node_id, cfg, job):
    _, _, scenario = _build(cfg)
    for r in range(1, cfg["num_rounds"] + 1):
        _block_post(f"{base}/broadcast", _tag(
            {"node_id": node_id, "round": r,
             "value": _sendable(scenario.broadcast_value(node_id, 0.0, r))}, job))
```

Злонамеран учесник не поседује суседе, не прима кандидате, не агрегира и не
извештава. Његов једини задатак је емитовање вредности.

Прослеђена нула је формални аргумент — учесник нема сопствену процену, а функција
захтева неку вредност коју потом занемарује.

### 5.8.8. Координација преко конфигурација

```python
class MatrixState:
    def state_for(self, job: int) -> ControllerState:
        with self.lock:
            st = self.states.get(job)
            if st is None:
                st = _spec_state(self.specs[job])
                self.states[job] = st
            return st
```

Стања се стварају тек по потреби, будући да при пуној матрици од 540
конфигурација само једна истовремено ради.

```python
def _spec_state(spec):
    return ControllerState(
        spec, rng=make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation))
```

Генератор се поравнава са оним који користи једнопроцесна матрица, чиме редослед
предлагања кандидата остаје исти у оба режима.

Завршетак конфигурације решен је преузимањем власништва:

```python
def finalize(self, job: int) -> None:
    with self.lock:
        st = self.states.get(job)
        if st is None or not st.complete():
            return
        self.states[job] = None
    ...
```

Више чворова може истовремено утврдити да је конфигурација завршена. Постављањем
вредности на празно под катанцем обезбеђено је да обраду изврши тачно један, чиме
се спречава вишеструко уписивање истих резултата.

Чвор пролази кроз све конфигурације редом:

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

Улога се одређује по конфигурацији, не при подизању контејнера. Исти контејнер
може бити честит учесник у једној конфигурацији а злонамеран у другој.

### 5.8.9. Бележење метрика

```python
def maybe_record(self, r):
    if r in self.recorded or len(self.reports.get(r, {})) < self.n:
        return
    rep = self.reports[r]
    for i in range(self.n):
        self.stubs[i].peers = rep[i]["peers"]
        self.stubs[i].estimate = rep[i]["estimate"]
    agg = lambda key: sum(rep[i][key] for i in range(self.n))
    counters = RoundCounters(data_msgs=agg("data_msgs"),
                             control_msgs=agg("control_msgs"), ...)
```

Бројачи се сабирају из извештаја свих чворова.

Бележење догађаја подељено је између координатора и чворова. Догађаји који се
односе на систем као целину бележе се једном, на координатору:

```python
if r == self.scenario.params.activate_round:
    self.trace.attack_activated(r, len(self.scenario.malicious_ids))
if self.scenario.active(r):
    for m in sorted(self.scenario.malicious_ids):
        if m in sent and sent[m] is not None:
            self.trace.malicious_broadcast(r, m, sent[m], ...)
```

Догађаји који настају на појединачном чвору шаљу се у извештају и уписују
уређено по редном броју чвора:

```python
for i in range(self.n):
    for row in (rep[i].get("trace") or []):
        self.trace.events.append(_row_to_event(row))
```

Уређени упис нужан је зато што извештаји стижу произвољним редоследом, а запис
догађаја мора бити исти при сваком покретању.

---

## 5.9. Провера исправности

Пошто оба начина извршавања користе исте модуле модела, поређење њихових
резултата представља проверу да ли се нека од путања разишла.

```python
def test_distributed_matrix_matches_inprocess():
    matrix = MatrixState("configs/tiny.json", verbose=False)
    # ... podizanje servera i cvorova u nitima ...
    for job, spec in enumerate(matrix.specs):
        docker_rows = matrix.round_rows[job][1]
        inprocess_rows = run_single(spec).to_csv_rows()
        assert docker_rows == inprocess_rows
```

Поређење се врши над целим низом редова, не само над коначном вредношћу, чиме
се открива и одступање које се касније поништи.

Провера је током развоја више пута открила стварна разилажења, међу којима су
најзначајнија била употреба генератора случајности зависног од окружења и
удвостручена логика контроле пријема, која је постојала у два примерка и
временом се разишла.

---

## 5.10. Конфигурација експеримената

Сви параметри система дефинисани су у једном фајлу, а поједини експерименти
наводе само одступања:

```python
def load_matrix(path: str) -> List[RunSpec]:
    cfg = load_defaults()
    cfg.update(json.load(open(path)))
    specs = []
    for nh in cfg["n_honest"]:
        for beta in cfg["beta"]:
            for overlay in cfg["overlay"]:
                for aggregation in cfg["aggregation"]:
                    for profile in cfg["byzantine_profile"]:
                        for seed in cfg["seeds"]:
                            specs.append(spec_from(...))
    return specs
```

Вредност задата као листа постаје димензија матрице. Тиме се аблациони
експерименти описују једним фајлом:

```json
{
  "n_honest": [15],
  "beta": [0.2],
  "overlay": ["random", "sybil_resistant", "eclipse_resistant"],
  "flooding": [0, 10, 25, 50],
  "seeds": [1, 2, 3]
}
```

Параметри напада који се мењају кроз матрицу додају се као колоне у излазним
записима, чиме се редови могу међусобно разликовати.

---

## Напомене за прераду

- Поглавље је писано тако да се сваки исечак може изоставити без губитка смисла
  текста. Ако је обим превелик, први кандидати за уклањање су 5.3.5, 5.5 и
  делови 5.7.
- Одељак 5.9 може прећи у поглавље о тестирању, ако оно постоји засебно.
- Места означена са **[провери]** описују топологију, чија се имплементација
  мењала током развоја.
- Слике које би овде имале смисла: дијаграм слојева (5.1), приказ градње
  топологије у три фазе (5.2.3), редослед фаза рунде са три баријере (5.8.5) и
  дијаграм размене порука између чвора и координатора (5.8.6).