from __future__ import annotations

from typing import Dict, List, Tuple

from attacks.scenario import FLOOD_BASE
from identity.observation import Observation

# Zajednicka per-cvor logika jedne gossip runde.
# Iste funkcije koristi in-process Engine (podaci iz memorije) i distribuirani
# node_service (podaci preko HTTP-a), pa admission/heartbeat pravila postoje
# samo na jednom mestu i ne mogu da se raziju izmedju dve putanje.

REASON_KEYS = ("invalid_pow", "too_young", "low_score", "bucket_full", "self_or_duplicate")


def empty_reasons() -> Dict[str, int]:
    return {k: 0 for k in REASON_KEYS}


def observe(node, other: int, round_now: int, exchanged: bool) -> None:
    obs = node.observations.get(other)
    # ako peer nije vidjen ranije dodaj observation
    if obs is None:
        node.observations[other] = Observation(
            first_seen_round=round_now, last_seen_round=round_now,
            successful_exchanges=1 if exchanged else 0)
    # ako jeste ziv je i osvezava se
    else:
        obs.last_seen_round = round_now
        if exchanged:
            obs.successful_exchanges += 1
            obs.missed_heartbeats = 0


def admit(node, offered: List[int], sampling, round_now: int,
          trace=None) -> Tuple[int, int, Dict[str, int]]:
    # discovery + admission + eviction za JEDAN cvor
    # 'offered' su vec pribavljeni kandidati (Engine ih racuna, node ih dobija preko HTTP-a)
    reasons = empty_reasons()
    if trace is not None:
        flooded = sum(1 for c in offered if c >= FLOOD_BASE)
        if flooded:
            trace.flooding(round_now, node.node_id, flooded)
    for candidate in offered:
        # zabelezi u dnevnik (vidjanje, ne razmena) -> time mu starost pocinje da tece
        observe(node, candidate, round_now, exchanged=False)
        # ako je kandidat vec komsija skip
        if candidate in node.peers:
            continue
        # admission !!!!!!!!!!!! -> proverava PoW/starost/skor/bucket
        if sampling.accept_peer(node, candidate, round_now):
            # strategija odlucuje koga (i da li) izbaciti:
            # eclipse vraca najslabijeg iz istog bucketa kad je bucket pun,
            # ostale strategije globalno najslabijeg tek kad je ceo peer set pun
            victim = sampling.evict_peer(node, round_now, candidate)
            if victim is not None:
                node.peers.remove(victim)
                if trace is not None:
                    trace.evict(round_now, node.node_id, victim, "replaced_by", candidate)
            elif len(node.peers) >= sampling.max_peers:
                if trace is not None:
                    trace.reject(round_now, node.node_id, candidate, "peer_set_full")
                continue
            node.peers.append(candidate)
            if trace is not None:
                trace.accept(round_now, node.node_id, candidate)
        else:
            # povecaj brojace
            why = sampling.reason(node, candidate, round_now) or "self_or_duplicate"
            reasons[why] = reasons.get(why, 0) + 1
            if trace is not None:
                trace.reject(round_now, node.node_id, candidate, why)
    return len(offered), sum(reasons.values()), reasons


def heartbeat(node, peers: List[int], scenario, round_now: int, rng,
              timeout_rounds: int, trace=None) -> Tuple[List[int], int]:
    # ko odgovara ostaje u razmeni, ko cuti skuplja propustene otkucaje
    responders = []
    for p in peers:
        if scenario.responds(p, round_now, rng):
            observe(node, p, round_now, exchanged=True)
            responders.append(p)
        else:
            obs = node.observations.get(p)
            if obs is not None:
                obs.missed_heartbeats += 1
                obs.missed_total += 1
    # timeout eviction: peer koji predugo cuti se izbacuje iz peer set-a
    timeouts = 0
    if timeout_rounds > 0:
        for p in list(node.peers):
            obs = node.observations.get(p)
            if obs is not None and obs.missed_heartbeats > timeout_rounds:
                node.peers.remove(p)
                obs.timeout_count += 1
                timeouts += 1
                if trace is not None:
                    trace.evict(round_now, node.node_id, p, "timeout", None)
                if p in responders:
                    responders.remove(p)
    return responders, timeouts


def broadcast_snapshot(nodes: Dict[int, object], scenario, round_now: int,
                       trace=None) -> Dict[int, float]:
    # snapshot svih cvorova i malicijusa (koristi ga samo in-process putanja;
    # u distribuiranoj verziji istu ulogu ima barijera na controlleru)
    out = {}
    for hid, node in nodes.items():
        out[hid] = scenario.broadcast_value(hid, node.estimate, round_now)
    for m in scenario.malicious_ids:
        # vrati placeholder svakako se ne koristi ta vrednost
        out[m] = scenario.broadcast_value(m, 0.0, round_now)
        if trace is not None and scenario.active(round_now):
            trace.malicious_broadcast(round_now, m, out[m], scenario.params.byzantine_profile)
    return out