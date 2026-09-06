from __future__ import annotations

import math
import random
from collections import Counter, deque
from typing import Dict, List, Set, Tuple

from identity.buckets import bucket_of


def build_random_overlay(n: int, k: int, rng: random.Random,
                         num_buckets: int = 0, max_per_bucket: int = 0) -> Dict[int, List[int]]:
    # regularna topologija: svaki cvor ima tacno k suseda.
    # razlog: gossip usrednjavanje konvergira ka stepenski ponderisanom proseku,
    # pa nejednaki stepeni pomeraju konsenzus u odnosu na x* i kada nema napada.
    # napomena: k-regularan graf postoji samo ako je n*k paran; kada nije
    # (npr. n=15, k=7), jedan cvor dobija k-1 suseda
    if n <= 1:
        return {i: [] for i in range(n)}
    if k >= n:
        return {i: sorted(j for j in range(n) if j != i) for i in range(n)}

    adj = _regular_graph(n, k, rng)
    _connect_preserving_degrees(adj, rng)
    if num_buckets > 0 and max_per_bucket > 0:
        # 4.5.3: pocetni peer set-ovi treba da postuju bucket ogranicenje vec u
        # prvoj rundi; inace bi cvorovi startovali sa prekoracenjem koje admission
        # provera ne vidi (ona gleda samo nove kandidate)
        _reduce_bucket_violations(adj, rng, num_buckets, max_per_bucket)
    return {i: sorted(adj[i]) for i in range(n)}


def _violations(adj: Dict[int, Set[int]], num_buckets: int, limit: int) -> int:
    # ukupno prekoracenje: koliko peer-ova preko dozvoljenog po bucketu
    total = 0
    for node, peers in adj.items():
        counts = Counter(bucket_of(str(p), num_buckets) for p in peers)
        total += sum(max(0, c - limit) for c in counts.values())
    return total


def _reduce_bucket_violations(adj: Dict[int, Set[int]], rng: random.Random,
                              num_buckets: int, limit: int,
                              attempts: int = 5000, patience: int = 300) -> None:
    # Ciljana popravka: nadje se cvor koji ima previse peer-ova iz istog bucketa,
    # pa se jedna njegova veza zameni sa vezom drugog para tako da prekoracenje
    # opadne. Zamena para veza cuva stepene, pa graf ostaje regularan.
    bucket = lambda i: bucket_of(str(i), num_buckets)
    # kod nekih kombinacija (n, k, broj bucketa) potpuno postovanje ogranicenja
    # nije moguce — tada se staje cim popravke prestanu da donose napredak
    best = None
    stale = 0
    for _ in range(attempts):
        over = _overfull(adj, bucket, limit)
        if not over:
            return
        if best is None or len(over) < best:
            best, stale = len(over), 0
        else:
            stale += 1
            if stale >= patience:
                return
        node, target = rng.choice(over)
        # peer iz prepunog bucketa koji ce biti zamenjen
        b = rng.choice([p for p in adj[node] if bucket(p) == target])
        # kandidat: cvor koji nije sused, iz bucketa koji kod nas nije popunjen
        counts = Counter(bucket(p) for p in adj[node])
        pool = [c for c in adj
                if c != node and c not in adj[node]
                and counts.get(bucket(c), 0) < limit]
        if not pool:
            continue
        c = rng.choice(sorted(pool))
        # da bi stepeni ostali isti, c mora da otpusti jednog svog suseda d,
        # koji zatim preuzima vezu ka b
        options = [d for d in adj[c] if d not in (node, b) and d not in adj[b]]
        if not options:
            continue
        d = rng.choice(sorted(options))
        adj[node].discard(b); adj[b].discard(node)
        adj[c].discard(d); adj[d].discard(c)
        adj[node].add(c); adj[c].add(node)
        adj[b].add(d); adj[d].add(b)
        if len(_components(adj)) > 1:
            adj[node].discard(c); adj[c].discard(node)
            adj[b].discard(d); adj[d].discard(b)
            adj[node].add(b); adj[b].add(node)
            adj[c].add(d); adj[d].add(c)


def _overfull(adj: Dict[int, Set[int]], bucket, limit: int) -> List[Tuple[int, int]]:
    # parovi (cvor, bucket) u kojima je ogranicenje prekoraceno
    out = []
    for node, peers in adj.items():
        for target, count in Counter(bucket(p) for p in peers).items():
            if count > limit:
                out.append((node, target))
    return sorted(out)


def _regular_graph(n: int, k: int, rng: random.Random) -> Dict[int, Set[int]]:
    # polazi se od determinsticke kruzne (circulant) osnove u kojoj svaki cvor
    # ima tacno k suseda, a zatim se struktura nasumicno promesa zamenama parova
    # veza koje ne menjaju stepene — tako se dobija slucajan k-regularan graf
    adj: Dict[int, Set[int]] = {i: set() for i in range(n)}
    half = k // 2
    for i in range(n):
        for d in range(1, half + 1):
            j = (i + d) % n
            adj[i].add(j)
            adj[j].add(i)
    if k % 2 == 1:
        if n % 2 == 0:
            for i in range(n // 2):
                j = i + n // 2
                adj[i].add(j)
                adj[j].add(i)
        else:
            # n i k su oba neparni -> k-regularan graf ne postoji (n*k je neparan),
            # pa jedan cvor nuzno ostaje sa k-1 suseda. Preostali cvorovi se uparuju
            # duz rastojanja koje kruzna osnova nije zauzela, da se ne ponovi veza
            step = half + 1
            while step < n and math.gcd(step, n) != 1:
                step += 1
            cycle = [(step * t) % n for t in range(n)]
            for a, b in zip(cycle[0:n - 1:2], cycle[1:n - 1:2]):
                adj[a].add(b)
                adj[b].add(a)
    _shuffle_preserving_degrees(adj, rng)
    return adj


def _shuffle_preserving_degrees(adj: Dict[int, Set[int]], rng: random.Random,
                                rounds: int = 20) -> None:
    # zamena dva para veza: (a,b) i (c,d) -> (a,c) i (b,d); stepeni ostaju isti
    n_edges = sum(len(v) for v in adj.values()) // 2
    for _ in range(rounds * n_edges):
        edges = _edges(adj)
        (a, b) = rng.choice(edges)
        (c, d) = rng.choice(edges)
        if len({a, b, c, d}) < 4:
            continue
        if c in adj[a] or d in adj[b]:
            continue
        adj[a].discard(b); adj[b].discard(a)
        adj[c].discard(d); adj[d].discard(c)
        adj[a].add(c); adj[c].add(a)
        adj[b].add(d); adj[d].add(b)


def _edges(adj: Dict[int, Set[int]]) -> List[Tuple[int, int]]:
    return [(a, b) for a in adj for b in adj[a] if a < b]


def _connect_preserving_degrees(adj: Dict[int, Set[int]], rng: random.Random) -> None:
    # spajanje komponenti zamenom parova veza: (a,b) i (c,d) se uklone,
    # a dodaju se (a,c) i (b,d) — stepeni ostaju isti, komponente se spajaju
    components = _components(adj)
    while len(components) > 1:
        first, second = components[0], components[1]
        e1 = [e for e in _edges(adj) if e[0] in first]
        e2 = [e for e in _edges(adj) if e[0] in second]
        if not e1 or not e2:
            return
        a, b = rng.choice(sorted(e1))
        c, d = rng.choice(sorted(e2))
        if c in adj[a] or d in adj[b]:
            components = _components(adj)
            continue
        adj[a].discard(b)
        adj[b].discard(a)
        adj[c].discard(d)
        adj[d].discard(c)
        adj[a].add(c)
        adj[c].add(a)
        adj[b].add(d)
        adj[d].add(b)
        components = _components(adj)


def _components(adj: Dict[int, Set[int]]) -> List[Set[int]]:
    seen: Set[int] = set()
    out: List[Set[int]] = []
    for start in sorted(adj):
        if start in seen:
            continue
        comp: Set[int] = set()
        q = deque([start])
        seen.add(start)
        while q:
            u = q.popleft()
            comp.add(u)
            for v in sorted(adj[u]):
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        out.append(comp)
    return out