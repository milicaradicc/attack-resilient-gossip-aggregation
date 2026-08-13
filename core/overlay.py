from __future__ import annotations

import random
from collections import deque
from typing import Dict, List, Set


def build_random_overlay(n: int, k: int, rng: random.Random) -> Dict[int, List[int]]:
    adj: Dict[int, Set[int]] = {i: set() for i in range(n)} # za svaki cvor prazan set komsija
    for i in range(n):
        candidates = [j for j in range(n) if j != i] # kandidati su svi ostali cvorovi sem njega samog 
        rng.shuffle(candidates) # deterministicko mesanje
        for j in candidates[:k]: # uzme k iz te liste 
            adj[i].add(j)
            adj[j].add(i)
    _ensure_connected(adj, rng)
    return {i: sorted(adj[i]) for i in range(n)} # akup nema redosled pa se sortira


def _ensure_connected(adj: Dict[int, Set[int]], rng: random.Random) -> None:
    components = _components(adj)
    while len(components) > 1:
        a = rng.choice(list(components[0]))
        b = rng.choice(list(components[1]))
        adj[a].add(b)
        adj[b].add(a)
        components = _components(adj)


def _components(adj: Dict[int, Set[int]]) -> List[Set[int]]:
    seen: Set[int] = set()
    out: List[Set[int]] = []
    for start in adj:
        if start in seen:
            continue
        comp: Set[int] = set()
        q = deque([start])
        seen.add(start)
        while q:
            u = q.popleft()
            comp.add(u)
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        out.append(comp)
    return out
